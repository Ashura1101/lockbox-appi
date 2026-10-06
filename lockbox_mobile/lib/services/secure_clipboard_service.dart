import 'dart:async';

import 'package:flutter/services.dart';

/// Copia texto al portapapeles y programa su borrado automático a los 30
/// segundos, evitando que las contraseñas queden expuestas indefinidamente.
class SecureClipboardService {
  /// Temporizador activo de la autolimpieza.
  Timer? _timer;

  /// Duración de vida del secreto en el portapapeles.
  static const Duration autoClearDelay = Duration(seconds: 30);

  /// Copia [text] al portapapeles y lo limpia automáticamente si sigue intacto.
  ///
  /// Si se proporciona [onCleared], se invoca justo después de limpiar el
  /// portapapeles (útil para notificar al usuario con un SnackBar).
  Future<void> copyWithAutoClear(String text, {void Function()? onCleared}) async {
    await Clipboard.setData(ClipboardData(text: text));

    _timer?.cancel();
    _timer = Timer(autoClearDelay, () async {
      // En Web el navegador bloquea la lectura asíncrona del portapapeles
      // dentro de un Timer, así que se fuerza el vaciado directamente.
      await Clipboard.setData(const ClipboardData(text: ''));
      onCleared?.call();
    });
  }

  /// Cancela la autolimpieza pendiente (por ejemplo, al salir de la app).
  void cancel() {
    _timer?.cancel();
    _timer = null;
  }

  void dispose() {
    cancel();
  }
}