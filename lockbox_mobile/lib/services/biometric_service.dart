import 'package:flutter/foundation.dart';
import 'package:local_auth/local_auth.dart';

/// Gestiona la autenticación biométrica (huella dactilar / Face ID).
class BiometricService {
  final LocalAuthentication _auth = LocalAuthentication();

  /// Indica si el dispositivo soporta biometría.
  ///
  /// En Web la biometría no está soportada y las llamadas a `local_auth`
  /// pueden lanzar excepciones; por eso se validan dentro de try/catch.
  Future<bool> isBiometricAvailable() async {
    if (kIsWeb) return false;
    try {
      final canCheck = await _auth.canCheckBiometrics;
      final isSupported = await _auth.isDeviceSupported();
      return canCheck && isSupported;
    } catch (_) {
      return false;
    }
  }

  /// Retorna los tipos de biometría disponibles (huella, facial, etc.).
  Future<List<BiometricType>> getAvailableBiometrics() async {
    if (kIsWeb) return const [];
    try {
      return await _auth.getAvailableBiometrics();
    } catch (_) {
      return const [];
    }
  }

  /// Solicita autenticación biométrica al usuario.
  ///
  /// Retorna `false` si la biometría no está disponible o si el intento
  /// falla o lanza una excepción, sin propagar el error a la interfaz.
  Future<bool> authenticate({
    String reason = 'Desbloquea Lockbox con tu huella o rostro',
  }) async {
    if (!await isBiometricAvailable()) return false;
    try {
      final authenticated = await _auth.authenticate(
        localizedReason: reason,
        options: const AuthenticationOptions(
          biometricOnly: true,
          stickyAuth: true,
        ),
      );
      return authenticated;
    } catch (_) {
      return false;
    }
  }
}