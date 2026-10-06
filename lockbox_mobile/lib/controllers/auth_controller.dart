import 'dart:async';

import 'package:bcrypt/bcrypt.dart';
import 'package:flutter/foundation.dart';

import '../models/credential.dart';
import '../repositories/vault_repository.dart';
import '../services/api_service.dart';
import '../services/biometric_service.dart';
import '../services/secure_storage_service.dart';
import '../services/token_storage_service.dart';

/// Estado global de autenticación y bóveda gestionado con Provider.
class AuthController extends ChangeNotifier {
  final ApiService api;
  final TokenStorageService tokenStorage;
  final BiometricService biometric;
  final VaultRepository vault;

  AuthController({
    required this.api,
    required this.tokenStorage,
    required this.biometric,
    required this.vault,
  });

  bool _isLoading = false;
  bool _isLocked = false;
  int _failedUnlockAttempts = 0;
  String? _username;
  List<Credential> _credentials = [];

  static const int maxFailedAttempts = 5;

  bool get isLoading => _isLoading;
  String? get username => _username;
  List<Credential> get credentials => _credentials;
  bool get isAuthenticated => _username != null;
  bool get isLocked => _isLocked;
  int get failedUnlockAttempts => _failedUnlockAttempts;
  int get remainingUnlockAttempts =>
      (maxFailedAttempts - _failedUnlockAttempts).clamp(0, maxFailedAttempts);

  /// Retorna si el hardware soporta y tiene biometría configurada.
  Future<bool> isBiometricAvailable() => biometric.isBiometricAvailable();

  /// Bloquea la bóveda manualmente o por auto-lock del lifecycle observer.
  ///
  /// No hace nada si no hay sesión activa (`isAuthenticated == false`),
  /// ya que bloquear sin sesión no tiene sentido y podría mostrar la
  /// pantalla de biometría sin tokens disponibles para restaurar.
  void lock() {
    if (!isAuthenticated) return;
    _isLocked = true;
    notifyListeners();
  }

  /// Restaura la sesión guardada (tokens + usuario) al abrir la app.
  /// Si la biometría está habilitada, deja la bóveda bloqueada hasta
  /// que el usuario se autentique con huella/Face ID o contraseña maestra.
  Future<void> restoreSession() async {
    final storedUser = await tokenStorage.username;
    final storedAccess = await tokenStorage.accessToken;
    final storedRefresh = await tokenStorage.refreshToken;

    if (storedUser != null && storedAccess != null) {
      api.setTokens(accessToken: storedAccess, refreshToken: storedRefresh);
      _username = storedUser;

      // Migración perezosa (lazy): si existe la contraseña en texto plano en Keystore
      // pero aún no se ha generado el hash bcrypt (usuarios previos a la actualización),
      // calculamos y persistimos el hash de inmediato para no dejarlos bloqueados.
      final storedHash = await tokenStorage.masterPasswordHash;
      if (storedHash == null) {
        final storedPassword = await tokenStorage.masterPassword;
        if (storedPassword != null && storedPassword.isNotEmpty) {
          final newHash = BCrypt.hashpw(
            storedPassword,
            BCrypt.gensalt(logRounds: 10),
          );
          await tokenStorage.saveMasterPasswordHash(newHash);
        }
      }

      // Se bloquea la bóveda siempre que la biometría esté habilitada en
      // preferencias, sin importar si el sensor biométrico está listo o no.
      // Si la biometría no está disponible, el usuario usará el fallback
      // de contraseña maestra en lugar de abrir el vault sin autenticación.
      final biometricEnabled = await tokenStorage.isBiometricEnabled();
      _isLocked = biometricEnabled;
      notifyListeners();
    }
  }

  /// Autentica con biometría si está habilitada. Retorna true si continúa.
  Future<bool> authenticateWithBiometrics() async {
    if (!await tokenStorage.isBiometricEnabled()) return true;
    if (!await biometric.isBiometricAvailable()) return false;
    try {
      return await biometric.authenticate();
    } catch (_) {
      return false;
    }
  }

  /// Desbloquea la bóveda solicitando autenticación biométrica.
  /// Retorna true si el usuario se autenticó correctamente.
  Future<bool> unlock() async {
    final ok = await authenticateWithBiometrics();
    if (ok) {
      // Solo se desbloquea la bóveda si hay un token JWT guardado
      // localmente; en caso contrario se cierra la sesión.
      if (!await SecureStorageService.hasToken()) {
        await _clearLocalSession();
        return false;
      }
      _failedUnlockAttempts = 0;
      _isLocked = false;
      notifyListeners();
    }
    return ok;
  }

  /// Desbloquea la bóveda verificando la contraseña maestra localmente
  /// contra el hash bcrypt guardado en SecureStorage (fallback de biometría).
  ///
  /// Incluye:
  /// - Migración lazy si el hash no existe aún.
  /// - Delay progresivo tras 3 o más fallos consecutivos.
  /// - Cierre forzado de sesión (`logout`) tras 5 intentos fallidos consecutivos.
  Future<bool> unlockWithMasterPassword(String password) async {
    if (_failedUnlockAttempts >= maxFailedAttempts) {
      await logout();
      return false;
    }

    // Delay progresivo tras 3 intentos fallidos (ej. intento 3: 2s, intento 4: 4s)
    if (_failedUnlockAttempts >= 3) {
      final delaySeconds = (_failedUnlockAttempts - 2) * 2;
      await Future.delayed(Duration(seconds: delaySeconds));
    }

    final hash = await tokenStorage.masterPasswordHash;
    bool isValid = false;

    if (hash != null) {
      isValid = BCrypt.checkpw(password, hash);
    } else {
      // Fallback de retrocompatibilidad si la sesión se guardó antes de implementar bcrypt:
      // compara contra el texto plano guardado y migra al hash bcrypt de inmediato.
      final storedPassword = await tokenStorage.masterPassword;
      isValid = storedPassword != null && storedPassword == password;
      if (isValid) {
        final newHash = BCrypt.hashpw(password, BCrypt.gensalt(logRounds: 10));
        await tokenStorage.saveMasterPasswordHash(newHash);
      }
    }

    if (isValid) {
      _failedUnlockAttempts = 0;
      if (!await SecureStorageService.hasToken()) {
        await _clearLocalSession();
        return false;
      }
      _isLocked = false;
      notifyListeners();
      return true;
    }

    // Registrar fallo
    _failedUnlockAttempts++;
    notifyListeners();

    // Forzar cierre de sesión si se alcanza el límite máximo de fallos
    if (_failedUnlockAttempts >= maxFailedAttempts) {
      await logout();
    }

    return false;
  }

  /// Acceso rápido desde la pantalla de login: autentica con biometría y, si
  /// existe una sesión guardada, la restaura y desbloquea la bóveda.
  Future<bool> quickBiometricAccess() async {
    final ok = await biometric.authenticate();
    if (!ok) return false;

    // Requiere una sesión JWT guardada para entrar directo al Dashboard.
    if (!await SecureStorageService.hasToken()) return false;

    await restoreSession();
    if (_username == null) return false;

    _isLocked = false;
    notifyListeners();
    return true;
  }

  /// Inicia sesión contra la API y guarda la sesión de forma segura.
  Future<void> login({
    required String username,
    required String masterPassword,
    bool enableBiometric = false,
  }) async {
    _isLoading = true;
    notifyListeners();
    try {
      final session = await api.login(username, masterPassword);
      await SecureStorageService.saveToken(session.accessToken);

      // Calcula el hash bcrypt local para validaciones fuera de línea (fallback de pantalla de bloqueo)
      // sin eliminar el texto plano en Keystore requerido por el backend para descifrado Fernet.
      final passwordHash = BCrypt.hashpw(
        masterPassword,
        BCrypt.gensalt(logRounds: 10),
      );

      await tokenStorage.saveSession(
        session,
        masterPassword: masterPassword,
        masterPasswordHash: passwordHash,
      );
      // Solo se persiste el flag biométrico si el hardware realmente lo soporta.
      if (enableBiometric && await biometric.isBiometricAvailable()) {
        await tokenStorage.setBiometricEnabled(true);
      }
      _username = session.username;
      _isLocked = false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Cierra sesión y elimina tokens locales.
  Future<void> logout() async {
    await api.logout();
    await _clearLocalSession();
  }

  /// Limpia la sesión local: token seguro, sesión persistida y estado global.
  Future<void> _clearLocalSession() async {
    await SecureStorageService.deleteToken();
    await tokenStorage.clearSession();
    _username = null;
    _credentials = [];
    _isLocked = false;
    _failedUnlockAttempts = 0;
    notifyListeners();
  }

  /// Carga las credenciales del usuario.
  ///
  /// 1. Lee PRIMERO de SQLite local y notifica de inmediato (la UI renderiza
  ///    las claves en milisegundos, sin esperar a Render ni mostrar spinners).
  /// 2. Luego sincroniza con el servidor en segundo plano, sin bloquear nada.
  Future<void> loadCredentials() async {
    await _readLocalCredentials();
    unawaited(_syncWithServer());
  }

  Future<void> _readLocalCredentials() async {
    final items = await vault.getVaultItems();
    _credentials = items
        .map((item) => Credential(
              id: (item['remote_id'] as String?) ?? 'local-${item['id']}',
              sitioWeb: item['title'] as String? ?? '',
              loginUser: item['username'] as String? ?? '',
              password: item['encrypted_password'] as String? ?? '',
            ))
        .toList();
    notifyListeners();
  }

  /// Sincronización silenciosa con Render en segundo plano. Cualquier error de
  /// red o del servidor se ignora para no romper la experiencia offline.
  Future<void> _syncWithServer() async {
    final user = _username;
    final masterPassword = await tokenStorage.masterPassword;
    if (user == null || masterPassword == null) return;

    try {
      final serverCredentials = await api.getCredentials(
        username: user,
        masterPassword: masterPassword,
      );
      await vault.syncCredentials(
        serverCredentials.map((c) => c.toJson()).toList(),
      );
      await _readLocalCredentials();
    } catch (e) {
      debugPrint('Sync en segundo plano sin conexión o con error: $e');
    }
  }

  /// Registra un usuario y retorna su clave de recuperación.
  Future<String> register({
    required String username,
    required String masterPassword,
  }) {
    return api.register(username, masterPassword);
  }

  /// Crea una nueva credencial en el backend autoritativo (Flask) vía
  /// `ApiService.addCredential`, que usa `POST /api/credentials/add`.
  ///
  /// No se persiste nada local antes de confirmar el alta en el servidor, de
  /// modo que ante 401/409 o error de red no queda un registro huérfano en
  /// SQLite. Tras un alta exitosa se recarga la bóveda para reflejar el
  /// `remote_id` real devuelto por el servidor.
  Future<void> addCredential({
    required String sitioWeb,
    required String loginUser,
    required String password,
    String? categoria,
    bool confirmDuplicate = false,
  }) async {
    final user = _username;
    final masterPassword = await tokenStorage.masterPassword;
    if (user == null || masterPassword == null) return;

    await api.addCredential(
      username: user,
      masterPassword: masterPassword,
      sitioWeb: sitioWeb,
      loginUser: loginUser,
      password: password,
      categoria: categoria,
      confirmDuplicate: confirmDuplicate,
    );
    await loadCredentials();
  }

  /// Actualiza una credencial existente y refresca la lista local.
  Future<void> updateCredential({
    required String id,
    required String sitioWeb,
    required String loginUser,
    String? password,
    String? categoria,
    bool confirmDuplicate = false,
  }) async {
    final user = _username;
    final masterPassword = await tokenStorage.masterPassword;
    if (user == null || masterPassword == null) return;

    await api.updateCredential(
      id: id,
      username: user,
      masterPassword: masterPassword,
      sitioWeb: sitioWeb,
      loginUser: loginUser,
      password: password,
      categoria: categoria,
      confirmDuplicate: confirmDuplicate,
    );
    await loadCredentials();
  }

  /// Elimina una credencial por su id.
  Future<void> deleteCredential(String id) async {
    final user = _username;
    final masterPassword = await tokenStorage.masterPassword;
    if (user == null || masterPassword == null) return;

    await api.deleteCredential(
      id: id,
      username: user,
      masterPassword: masterPassword,
    );
    await loadCredentials();
  }
}