import 'package:http/http.dart' as http;
import 'dart:convert';

import '../models/auth_session.dart';
import '../models/category.dart';
import '../models/credential.dart';

/// Cliente HTTP que consume el backend de Lockbox desplegado en Render.
/// Inyecta automáticamente el token JWT y rota el refresh token ante un 401.
class ApiService {
  static const String _baseUrl = 'https://lockbox-appi.onrender.com/api';

  final http.Client _client;
  String? _accessToken;
  String? _refreshToken;

  /// Callback que se invoca cuando el refresh token expira y se requiere
  /// que el usuario vuelva a iniciar sesión.
  final Future<void> Function()? onSessionExpired;
  final Future<void> Function(String accessToken, String refreshToken)? onTokensRefreshed;

  ApiService({http.Client? client, this.onSessionExpired, this.onTokensRefreshed})
      : _client = client ?? http.Client();

  // ---------------------------------------------------------------
  // Tokens
  // ---------------------------------------------------------------
  void setTokens({String? accessToken, String? refreshToken}) {
    if (accessToken != null) _accessToken = accessToken;
    if (refreshToken != null) _refreshToken = refreshToken;
  }

  void clearTokens() {
    _accessToken = null;
    _refreshToken = null;
  }

  // ---------------------------------------------------------------
  // Helpers HTTP
  // ---------------------------------------------------------------
  Map<String, String> get _jsonHeaders => {
        'Content-Type': 'application/json',
        if (_accessToken != null) 'Authorization': 'Bearer $_accessToken',
      };

  Future<Map<String, dynamic>> _decode(http.Response response) async {
    final body = response.body.isEmpty ? {} : json.decode(response.body);
    if (body is Map<String, dynamic>) return body;
    return {'data': body};
  }

  /// Ejecuta una petición. Si recibe 401 intenta renovar el access token
  /// con el refresh token y reintenta una única vez.
  Future<http.Response> _send(Future<http.Response> Function() request) async {
    final response = await request();
    if (response.statusCode == 401 && _refreshToken != null) {
      final renewed = await _tryRefreshToken();
      if (renewed) {
        return request();
      }
    }
    return response;
  }

  Future<bool> _tryRefreshToken() async {
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/auth/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'refresh_token': _refreshToken}),
      );
      if (response.statusCode == 200) {
        final body = await _decode(response);
        setTokens(
          accessToken: body['access_token'] as String?,
          refreshToken: body['refresh_token'] as String?,
        );
        if (_accessToken != null && _refreshToken != null && onTokensRefreshed != null) {
          try {
            await onTokensRefreshed!(_accessToken!, _refreshToken!);
          } catch (_) {}
        }
        return true;
      }
      clearTokens();
      return false;
    } catch (_) {
      return false;
    }
  }

  // ---------------------------------------------------------------
  // Autenticación
  // ---------------------------------------------------------------
  /// Registra un nuevo usuario. Retorna la clave de recuperación.
  Future<String> register(String username, String masterPassword) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/register'),
      headers: _jsonHeaders,
      body: json.encode({
        'username': username,
        'master_password': masterPassword,
      }),
    );
    final body = await _decode(response);
    if (response.statusCode == 201) {
      return body['recovery_key'] as String? ?? '';
    }
    throw ApiException(body['error'] ?? 'Error al registrar el usuario', response.statusCode);
  }

  /// Inicia sesión y devuelve la sesión con los tokens JWT.
  Future<AuthSession> login(String username, String masterPassword) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/login'),
      headers: _jsonHeaders,
      body: json.encode({
        'username': username,
        'master_password': masterPassword,
      }),
    );
    final body = await _decode(response);
    if (response.statusCode == 200) {
      final session = AuthSession.fromJson(body);
      setTokens(accessToken: session.accessToken, refreshToken: session.refreshToken);
      return session;
    }
    throw ApiException(body['error'] ?? 'Credenciales inválidas', response.statusCode);
  }

  /// Cierra sesión revocando los tokens en el backend.
  Future<void> logout({String? refreshToken}) async {
    final currentRefresh = refreshToken ?? _refreshToken;
    await _send(() => http.post(
          Uri.parse('$_baseUrl/auth/logout'),
          headers: _jsonHeaders,
          body: json.encode({'refresh_token': currentRefresh}),
        ));
    clearTokens();
  }

  /// Restablece la contraseña maestra usando la clave de recuperación.
  Future<void> recoverPassword({
    required String username,
    required String recoveryKey,
    required String newMasterPassword,
  }) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/recover'),
      headers: _jsonHeaders,
      body: json.encode({
        'username': username,
        'recovery_key': recoveryKey,
        'new_master_password': newMasterPassword,
      }),
    );
    final body = await _decode(response);
    if (response.statusCode != 200) {
      throw ApiException(body['error'] ?? 'No se pudo restablecer la contraseña', response.statusCode);
    }
  }

  // ---------------------------------------------------------------
  // Credenciales
  // ---------------------------------------------------------------
  /// Obtiene y descifra todas las credenciales del usuario.
  Future<List<Credential>> getCredentials({
    required String username,
    required String masterPassword,
    String? query,
  }) async {
    final payload = <String, dynamic>{
      'username': username,
      'master_password': masterPassword,
      if (query != null && query.isNotEmpty) 'query': query,
    };

    final response = await _send(() => http.post(
          Uri.parse('$_baseUrl/credentials'),
          headers: _jsonHeaders,
          body: json.encode(payload),
        ));

    final body = await _decode(response);
    if (response.statusCode == 200) {
      final list = body['credenciales'] as List? ?? [];
      return list
          .map((e) => Credential.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    throw ApiException(body['error'] ?? 'Error al obtener credenciales', response.statusCode);
  }

  /// Guarda una nueva credencial cifrada.
  Future<void> addCredential({
    required String username,
    required String masterPassword,
    required String sitioWeb,
    required String loginUser,
    required String password,
    String? categoria,
    bool confirmDuplicate = false,
  }) async {
    final response = await _send(() => http.post(
          Uri.parse('$_baseUrl/credentials/add'),
          headers: _jsonHeaders,
          body: json.encode({
            'username': username,
            'master_password': masterPassword,
            'sitio_web': sitioWeb,
            'login_user': loginUser,
            'password': password,
            if (categoria != null && categoria.isNotEmpty) 'categoria': categoria,
            if (confirmDuplicate) 'confirm_duplicate': true,
          }),
        ));

    final body = await _decode(response);
    if (response.statusCode == 409 && body['warning'] == 'duplicate_password') {
      throw DuplicatePasswordException(
        body['error'] as String? ?? 'Contraseña ya utilizada',
        body['existing_id'] as String? ?? '',
      );
    }
    if (response.statusCode != 201) {
      throw ApiException(body['error'] ?? 'Error al guardar la credencial', response.statusCode);
    }
  }

  /// Actualiza una credencial existente.
  Future<void> updateCredential({
    required String id,
    required String username,
    required String masterPassword,
    String? sitioWeb,
    String? loginUser,
    String? password,
    String? categoria,
    bool confirmDuplicate = false,
  }) async {
    final response = await _send(() => http.post(
          Uri.parse('$_baseUrl/credentials/update'),
          headers: _jsonHeaders,
          body: json.encode({
            'id': id,
            'username': username,
            'master_password': masterPassword,
            if (sitioWeb != null) 'sitio_web': sitioWeb,
            if (loginUser != null) 'login_user': loginUser,
            if (password != null) 'password': password,
            if (categoria != null && categoria.isNotEmpty) 'categoria': categoria,
            if (confirmDuplicate) 'confirm_duplicate': true,
          }),
        ));

    final body = await _decode(response);
    if (response.statusCode == 409 && body['warning'] == 'duplicate_password') {
      throw DuplicatePasswordException(
        body['error'] as String? ?? 'Contraseña ya utilizada',
        body['existing_id'] as String? ?? '',
      );
    }
    if (response.statusCode != 200) {
      throw ApiException(body['error'] ?? 'Error al actualizar la credencial', response.statusCode);
    }
  }

  /// Elimina una credencial.
  Future<void> deleteCredential({
    required String id,
    required String username,
    required String masterPassword,
  }) async {
    final response = await _send(() => http.post(
          Uri.parse('$_baseUrl/credentials/delete'),
          headers: _jsonHeaders,
          body: json.encode({
            'id': id,
            'username': username,
            'master_password': masterPassword,
          }),
        ));

    final body = await _decode(response);
    if (response.statusCode != 200) {
      throw ApiException(body['error'] ?? 'Error al eliminar la credencial', response.statusCode);
    }
  }

  // ---------------------------------------------------------------
  // Categorías
  // ---------------------------------------------------------------
  Future<List<Category>> getCategories() async {
    final response = await _send(() => http.get(
          Uri.parse('$_baseUrl/categories'),
          headers: _jsonHeaders,
        ));

    final body = await _decode(response);
    if (response.statusCode == 200) {
      final list = body['categories'] as List? ?? [];
      return list.map((e) => Category.fromJson(e as Map<String, dynamic>)).toList();
    }
    throw ApiException(body['error'] ?? 'Error al obtener categorías', response.statusCode);
  }

  void dispose() {
    _client.close();
  }
}

/// Excepción tipada para errores del backend con su código HTTP.
class ApiException implements Exception {
  final String message;
  final int statusCode;

  const ApiException(this.message, this.statusCode);

  @override
  String toString() => message;
}

/// Excepción para el caso de reutilización de contraseña (409 con warning
/// `duplicate_password`). Expone el id de la credencial existente para que la
/// UI pueda ofrecer reintentar con confirmación.
class DuplicatePasswordException extends ApiException {
  final String existingId;

  const DuplicatePasswordException(String message, this.existingId)
      : super(message, 409);
}