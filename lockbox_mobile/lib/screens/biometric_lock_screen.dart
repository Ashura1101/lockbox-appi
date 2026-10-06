import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/auth_controller.dart';

/// Pantalla que bloquea el acceso a la bóveda hasta que el usuario se
/// autentique con huella dactilar / Face ID o mediante su contraseña maestra (fallback).
class BiometricLockScreen extends StatefulWidget {
  const BiometricLockScreen({super.key});

  @override
  State<BiometricLockScreen> createState() => _BiometricLockScreenState();
}

class _BiometricLockScreenState extends State<BiometricLockScreen> {
  final _passwordController = TextEditingController();
  bool _authenticating = false;
  bool _biometricAvailable = true;
  bool _showPasswordFallback = false;
  bool _obscurePassword = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _initLockScreen());
  }

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _initLockScreen() async {
    final auth = context.read<AuthController>();
    final available = await auth.isBiometricAvailable();

    if (!mounted) return;

    setState(() {
      _biometricAvailable = available;
      if (!available) {
        // Si no hay biometría disponible, mostrar de inmediato el fallback
        _showPasswordFallback = true;
      }
    });

    if (available) {
      _unlockBiometric();
    }
  }

  Future<void> _unlockBiometric() async {
    setState(() {
      _authenticating = true;
      _error = null;
    });

    final auth = context.read<AuthController>();
    bool ok = false;
    try {
      ok = await auth.unlock();
    } catch (_) {
      ok = false;
    }

    if (mounted) {
      setState(() {
        _authenticating = false;
        if (!ok) {
          _error = 'Autenticación biométrica no completada.';
        }
      });
    }
  }

  Future<void> _unlockWithPassword() async {
    final password = _passwordController.text.trim();
    if (password.isEmpty) {
      setState(() {
        _error = 'Por favor ingresa tu contraseña maestra.';
      });
      return;
    }

    setState(() {
      _authenticating = true;
      _error = null;
    });

    final auth = context.read<AuthController>();
    final ok = await auth.unlockWithMasterPassword(password);

    if (mounted) {
      setState(() {
        _authenticating = false;
        if (!ok) {
          if (!auth.isAuthenticated) {
            _error = 'Demasiados intentos fallidos. Sesión cerrada por seguridad.';
          } else {
            final remaining = auth.remainingUnlockAttempts;
            final penalty = auth.failedUnlockAttempts >= 3
                ? ' (demora de seguridad aplicada)'
                : '';
            _error = 'Contraseña maestra incorrecta. Intentos restantes: $remaining$penalty.';
          }
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  _showPasswordFallback ? Icons.lock_outline : Icons.fingerprint,
                  size: 80,
                  color: const Color(0xFF6366F1),
                ),
                const SizedBox(height: 20),
                Text(
                  'Bóveda bloqueada',
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  !_biometricAvailable
                      ? 'La biometría no está disponible en este dispositivo.\nIngresa tu contraseña maestra para continuar.'
                      : _showPasswordFallback
                          ? 'Ingresa tu contraseña maestra para desbloquear tu bóveda.'
                          : 'Autentícate con tu huella o Face ID para continuar.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.grey, height: 1.4),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    decoration: BoxDecoration(
                      color: Colors.red.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.red.withOpacity(0.3)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.error_outline, color: Colors.red, size: 20),
                        const SizedBox(width: 8),
                        Flexible(
                          child: Text(
                            _error!,
                            textAlign: TextAlign.center,
                            style: const TextStyle(color: Colors.redAccent, fontSize: 13),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 28),

                if (_showPasswordFallback) ...[
                  TextField(
                    controller: _passwordController,
                    obscureText: _obscurePassword,
                    enabled: !_authenticating,
                    onSubmitted: (_) => _unlockWithPassword(),
                    decoration: InputDecoration(
                      labelText: 'Contraseña maestra',
                      prefixIcon: const Icon(Icons.password),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _obscurePassword ? Icons.visibility : Icons.visibility_off,
                        ),
                        onPressed: () {
                          setState(() {
                            _obscurePassword = !_obscurePassword;
                          });
                        },
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: _authenticating ? null : _unlockWithPassword,
                      icon: _authenticating
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : const Icon(Icons.lock_open),
                      label: const Text('Desbloquear bóveda'),
                    ),
                  ),
                ] else ...[
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: _authenticating ? null : _unlockBiometric,
                      icon: _authenticating
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : const Icon(Icons.fingerprint),
                      label: const Text('Desbloquear con biometría'),
                    ),
                  ),
                ],

                const SizedBox(height: 16),

                // Alternar entre biometría y contraseña maestra si ambas son posibles
                if (_biometricAvailable) ...[
                  TextButton.icon(
                    onPressed: _authenticating
                        ? null
                        : () {
                            setState(() {
                              _showPasswordFallback = !_showPasswordFallback;
                              _error = null;
                            });
                          },
                    icon: Icon(
                      _showPasswordFallback ? Icons.fingerprint : Icons.key,
                      size: 18,
                    ),
                    label: Text(
                      _showPasswordFallback
                          ? 'Usar autenticación biométrica'
                          : 'Usar contraseña maestra',
                    ),
                  ),
                ],

                const SizedBox(height: 12),
                TextButton(
                  onPressed: _authenticating
                      ? null
                      : () => context.read<AuthController>().logout(),
                  child: const Text(
                    'Cerrar sesión',
                    style: TextStyle(color: Colors.grey),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}