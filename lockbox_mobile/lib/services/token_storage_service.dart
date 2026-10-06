import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/auth_session.dart';

/// Almacena de forma segura los tokens JWT, la contraseña maestra y la
/// preferencia de biometría en el Keychain (iOS) / Keystore (Android).
class TokenStorageService {
  static const _accessTokenKey = 'lockbox_access_token';
  static const _refreshTokenKey = 'lockbox_refresh_token';
  static const _usernameKey = 'lockbox_username';
  static const _masterPasswordKey = 'lockbox_master_password';
  static const _masterPasswordHashKey = 'lockbox_master_password_hash';
  static const _biometricEnabledKey = 'lockbox_biometric_enabled';

  static const _storage = FlutterSecureStorage();

  Future<void> saveSession(
    AuthSession session, {
    String? masterPassword,
    String? masterPasswordHash,
  }) async {
    await _storage.write(key: _accessTokenKey, value: session.accessToken);
    await _storage.write(key: _refreshTokenKey, value: session.refreshToken);
    await _storage.write(key: _usernameKey, value: session.username);
    if (masterPassword != null) {
      await _storage.write(key: _masterPasswordKey, value: masterPassword);
    }
    if (masterPasswordHash != null) {
      await _storage.write(key: _masterPasswordHashKey, value: masterPasswordHash);
    }
  }

  Future<void> saveTokens(String accessToken, String refreshToken) async {
    await _storage.write(key: _accessTokenKey, value: accessToken);
    await _storage.write(key: _refreshTokenKey, value: refreshToken);
  }

  Future<void> saveMasterPasswordHash(String hash) async {
    await _storage.write(key: _masterPasswordHashKey, value: hash);
  }

  Future<String?> get accessToken => _storage.read(key: _accessTokenKey);
  Future<String?> get refreshToken => _storage.read(key: _refreshTokenKey);
  Future<String?> get username => _storage.read(key: _usernameKey);
  Future<String?> get masterPassword => _storage.read(key: _masterPasswordKey);
  Future<String?> get masterPasswordHash => _storage.read(key: _masterPasswordHashKey);

  Future<bool> isBiometricEnabled() async {
    final value = await _storage.read(key: _biometricEnabledKey);
    return value == 'true';
  }

  Future<void> setBiometricEnabled(bool enabled) async {
    await _storage.write(key: _biometricEnabledKey, value: enabled.toString());
  }

  Future<void> clearSession() async {
    await _storage.delete(key: _accessTokenKey);
    await _storage.delete(key: _refreshTokenKey);
    await _storage.delete(key: _usernameKey);
    await _storage.delete(key: _masterPasswordKey);
    await _storage.delete(key: _masterPasswordHashKey);
  }
}