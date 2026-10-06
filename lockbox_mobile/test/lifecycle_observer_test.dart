import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lockbox_mobile/core/lifecycle/app_lifecycle_observer.dart';

void main() {
  test('no bloquea si la app regresa antes del umbral de 15 segundos', () {
    int lockCalls = 0;
    final observer = LockboxLifecycleObserver(onLock: () => lockCalls++);

    // Simular que va a background (por ejemplo, prompt biométrico de local_auth)
    observer.didChangeAppLifecycleState(AppLifecycleState.inactive);
    observer.didChangeAppLifecycleState(AppLifecycleState.paused);

    // Regresa de inmediato
    observer.didChangeAppLifecycleState(AppLifecycleState.resumed);

    expect(lockCalls, equals(0));
  });
}
