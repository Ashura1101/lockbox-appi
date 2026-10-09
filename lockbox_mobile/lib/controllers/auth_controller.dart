import 'dart:async';
import 'dart:isolate';

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

  // ---------------------------------------------------------------
  // Single-flight sync & concurrency tracking
  // ---------------------------------------------------------------
  /// Indica si hay una sincronización con el servidor actualmente en ejecución.
  bool _syncInFlight = false;

  /// Indica si se solicitó otra sincronización mientras una ya estaba en curso.
  bool _syncPending = false;

  /// Completer para permitir que operaciones explícitas (como pull-to-refresh)
  /// esperen a que termine la sincronización activa.
  Completer<void>? _syncCompleter;

  /// Contador de versiones de mutación local. Se incrementa en cada CREATE, EDIT, DELETE.
  /// Permite detectar si una respuesta del servidor recibida corresponde a un estado previo
  /// a una mutación local más reciente para no sobrescribirla.
  int _mutationVersion = 0;

  /// Timer para debouncear el sync en segundo plano tras mutaciones optimistas.
  Timer? _syncTimer;

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
      // calculamos y persistimos el hash de inmediato en Isolate.run para no dejarlos bloqueados.
      final storedHash = await tokenStorage.masterPasswordHash;
      if (storedHash == null) {
        final storedPassword = await tokenStorage.masterPassword;
        if (storedPassword != null && storedPassword.isNotEmpty) {
          final newHash = await Isolate.run(
            () => BCrypt.hashpw(storedPassword, BCrypt.gensalt(logRounds: 10)),
          );
          await tokenStorage.saveMasterPasswordHash(newHash);
        }
      }

      // Se bloquea la bóveda siempre que la biometría está habilitada en
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
  /// - Ejecución de BCrypt en Isolate.run para mantener fluida la interfaz.
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
      isValid = await Isolate.run(() => BCrypt.checkpw(password, hash));
    } else {
      // Fallback de retrocompatibilidad si la sesión se guardó antes de implementar bcrypt:
      // compara contra el texto plano guardado y migra al hash bcrypt de inmediato.
      final storedPassword = await tokenStorage.masterPassword;
      isValid = storedPassword != null && storedPassword == password;
      if (isValid) {
        final newHash = await Isolate.run(
          () => BCrypt.hashpw(password, BCrypt.gensalt(logRounds: 10)),
        );
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
      // Se ejecuta en un isolate para no bloquear el UI thread durante el cálculo.
      final passwordHash = await Isolate.run(
        () => BCrypt.hashpw(masterPassword, BCrypt.gensalt(logRounds: 10)),
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
    _syncTimer?.cancel();
    _syncTimer = null;
    await api.logout();
    await _clearLocalSession();
  }

  /// Limpia la sesión local: token seguro, sesión persistida y estado global.
  Future<void> _clearLocalSession() async {
    _syncTimer?.cancel();
    _syncTimer = null;
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
  /// 2. Luego sincroniza con el servidor en segundo plano usando single-flight, sin bloquear la UI.
  Future<void> loadCredentials() async {
    if (_credentials.isEmpty) {
      await _readLocalCredentials();
    }
    unawaited(_requestSync());
  }

  /// Actualización explícita solicitada por el usuario (pull-to-refresh):
  /// Espera la sincronización con el servidor antes de cerrar el indicador de refresh.
  Future<void> refreshCredentials() async {
    _syncTimer?.cancel();
    _syncTimer = null;
    if (_syncInFlight) {
      _syncPending = true;
      await (_syncCompleter?.future ?? Future.value());
      if (_syncInFlight && _syncCompleter != null) {
        await _syncCompleter!.future;
      }
    } else {
      await _runSync();
    }
  }

  Future<void> _readLocalCredentials() async {
    final items = await vault.getVaultItems();
    _credentials = items
        .map((item) => Credential(
              id: (item['remote_id'] as String?) ?? 'local-${item['id']}',
              sitioWeb: item['title'] as String? ?? '',
              loginUser: item['username'] as String? ?? '',
              password: item['encrypted_password'] as String? ?? '',
              categoria: item['categoria'] as String?,
            ))
        .toList();
    notifyListeners();
  }

  // ---------------------------------------------------------------
  // Single-flight Sync
  // ---------------------------------------------------------------

  /// Solicita una sincronización con el servidor respetando single-flight.
  /// Si ya hay una en curso, la marca como pendiente y no abre una segunda paralela.
  Future<void> _requestSync() async {
    if (_syncInFlight) {
      _syncPending = true;
      return _syncCompleter?.future ?? Future.value();
    }
    return _runSync();
  }

  Future<void> _runSync() async {
    _syncInFlight = true;
    _syncPending = false;
    final completer = Completer<void>();
    _syncCompleter = completer;

    try {
      await _syncWithServer();
    } finally {
      _syncInFlight = false;
      if (!completer.isCompleted) {
        completer.complete();
      }
      _syncCompleter = null;

      if (_syncPending) {
        unawaited(_runSync());
      }
    }
  }

  /// Sincronización silenciosa con el servidor.
  /// Cualquier error de red o del servidor se ignora para no romper la experiencia offline.
  Future<void> _syncWithServer() async {
    final user = _username;
    final masterPassword = await tokenStorage.masterPassword;
    if (user == null || masterPassword == null) return;

    final startVersion = _mutationVersion;
    try {
      final serverCredentials = await api.getCredentials(
        username: user,
        masterPassword: masterPassword,
      );

      // Si ocurrió una mutación local (crear, editar, eliminar) mientras se esperaba
      // la respuesta del servidor, dicha respuesta es obsoleta. Descartamos para no
      // sobrescribir la mutación más nueva; la sincronización pendiente (_syncPending)
      // traerá el estado actualizado.
      if (_mutationVersion != startVersion) return;

      await vault.syncCredentials(
        serverCredentials.map((c) => c.toJson()).toList(),
      );

      if (_mutationVersion != startVersion) return;

      // Solo notificar si la lista cambió para no provocar reconstrucciones innecesarias
      // en la interfaz mientras el usuario escribe en el buscador.
      if (!listEquals(_credentials, serverCredentials)) {
        _credentials = serverCredentials;
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Sync en segundo plano sin conexión o con error: $e');
    }
  }

  /// Programa una sincronización en segundo plano con debounce para consolidar
  /// múltiples mutaciones rápidas en una sola petición de reconciliación.
  void _scheduleSync() {
    _syncTimer?.cancel();
    _syncTimer = Timer(const Duration(milliseconds: 1500), () {
      _syncTimer = null;
      unawaited(_requestSync());
    });
  }

  // ---------------------------------------------------------------
  // Mutaciones de Credenciales
  // ---------------------------------------------------------------

  /// Registra un usuario y retorna su clave de recuperación.
  Future<String> register({
    required String username,
    required String masterPassword,
  }) {
    return api.register(username, masterPassword);
  }

  /// Crea una nueva credencial en el backend autoritativo (Flask) vía `ApiService.addCredential`.
  ///
  /// Flujo optimizado:
  /// 1. Envía la creación al servidor y obtiene el ID real asignado (HTTP 201).
  /// 2. Crea el objeto `Credential` con el ID real (sin IDs provisionales).
  /// 3. Actualiza `_credentials` de inmediato y llama `notifyListeners()`.
  /// 4. Programa la reconciliación en segundo plano (`_scheduleSync`).
  ///
  /// La UI no espera una segunda descarga completa de todas las credenciales.
  /// Si el servidor falla (401, 409, error de red), se lanza la excepción sin tocar `_credentials`.
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

    final realId = await api.addCredential(
      username: user,
      masterPassword: masterPassword,
      sitioWeb: sitioWeb,
      loginUser: loginUser,
      password: password,
      categoria: categoria,
      confirmDuplicate: confirmDuplicate,
    );

    _mutationVersion++;
    final newCredential = Credential(
      id: realId,
      sitioWeb: sitioWeb,
      loginUser: loginUser,
      password: password,
      categoria: categoria,
    );

    _credentials = [newCredential, ..._credentials.where((c) => c.id != realId)];
    notifyListeners();
    _scheduleSync();
  }

  /// Actualiza una credencial existente.
  ///
  /// Flujo optimizado:
  /// 1. Envía los cambios al servidor (`updateCredential`).
  /// 2. Si tiene éxito, actualiza directamente el elemento correspondiente en `_credentials`.
  /// 3. Notifica a la UI inmediatamente (`notifyListeners`).
  /// 4. Programa sync en segundo plano para reconciliación en SQLite.
  ///
  /// No ejecuta `await _syncWithServer()` antes de terminar la operación visible.
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

    _mutationVersion++;
    _credentials = _credentials.map((c) {
      if (c.id == id) {
        return Credential(
          id: id,
          sitioWeb: sitioWeb,
          loginUser: loginUser,
          password: password ?? c.password,
          categoria: categoria,
        );
      }
      return c;
    }).toList();

    notifyListeners();
    _scheduleSync();
  }

  /// Elimina una credencial por su id.
  ///
  /// Flujo optimizado:
  /// 1. Envía la eliminación al servidor (`deleteCredential`).
  /// 2. Remueve inmediatamente el elemento de `_credentials`.
  /// 3. Notifica a la UI (`notifyListeners`) para que la tarjeta desaparezca sin demora.
  /// 4. Programa sync en segundo plano (`_scheduleSync`) para la reconciliación con SQLite.
  Future<void> deleteCredential(String id) async {
    final user = _username;
    final masterPassword = await tokenStorage.masterPassword;
    if (user == null || masterPassword == null) return;

    await api.deleteCredential(
      id: id,
      username: user,
      masterPassword: masterPassword,
    );

    _mutationVersion++;
    _credentials = _credentials.where((c) => c.id != id).toList();
    notifyListeners();
    _scheduleSync();
  }
}