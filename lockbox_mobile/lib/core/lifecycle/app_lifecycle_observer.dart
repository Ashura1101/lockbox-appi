import 'package:flutter/material.dart';

/// Observa el ciclo de vida de la app y dispara un auto-lock de la bóveda
/// cuando el usuario regresa después de haber estado en background más de
/// [_lockThreshold].
///
/// Esto evita falsos positivos de bloqueo cuando `local_auth` u otro plugin
/// nativo (pickers, share) abren una Activity por encima de Flutter durante
/// unos pocos segundos (estado `inactive`/`paused` breve).
class LockboxLifecycleObserver extends WidgetsBindingObserver {
  /// Callback que se ejecuta para bloquear la bóveda.
  final VoidCallback onLock;

  /// Instante en que la app pasó a segundo plano.
  DateTime? _pausedAt;

  /// Tiempo mínimo en background para disparar el auto-lock.
  static const _lockThreshold = Duration(seconds: 15);

  LockboxLifecycleObserver({required this.onLock});

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.inactive:
        // `inactive` se dispara también al abrir prompts nativos (biometría,
        // pickers). Se registra el instante pero NO se bloquea de inmediato
        // para no interrumpir esos flujos.
        _pausedAt ??= DateTime.now();
        break;

      case AppLifecycleState.resumed:
        if (_pausedAt != null &&
            DateTime.now().difference(_pausedAt!) > _lockThreshold) {
          onLock(); // Vuelve a pedir PIN/huella.
        }
        _pausedAt = null;
        break;

      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
        // `hidden` (Android 13+) y `detached` no requieren acción aquí.
        break;
    }
  }
}
