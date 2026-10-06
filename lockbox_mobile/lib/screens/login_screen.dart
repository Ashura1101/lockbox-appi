import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/auth_controller.dart';
import 'register_screen.dart';

/// Pantalla de inicio de sesión con soporte opcional de inicio biométrico.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _enableBiometric = false;
  bool _biometricAvailable = false;
  bool _biometricBusy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final available = await context.read<AuthController>().biometric.isBiometricAvailable();
      if (mounted) setState(() => _biometricAvailable = available);
    });
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final auth = context.read<AuthController>();
    setState(() => _error = null);

    try {
      // La autenticación contra el backend (usuario + contraseña maestra) es
      // siempre el método principal; la biometría solo se habilita como acceso
      // rápido futuro si el hardware la soporta.
      await auth.login(
        username: _usernameController.text.trim(),
        masterPassword: _passwordController.text,
        enableBiometric: _enableBiometric && _biometricAvailable,
      );
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  Future<void> _quickBiometricLogin() async {
    final auth = context.read<AuthController>();
    setState(() {
      _biometricBusy = true;
      _error = null;
    });

    final ok = await auth.quickBiometricAccess();

    if (!mounted) return;
    setState(() => _biometricBusy = false);
    if (!ok) {
      setState(
        () => _error = 'No se pudo autenticar o no hay una sesión guardada.',
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();

    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.lock, size: 64, color: Color(0xFF6366F1)),
                const SizedBox(height: 12),
                Text('LOCKBOX', style: Theme.of(context).textTheme.headlineMedium),
                const SizedBox(height: 32),
                TextField(
                  controller: _usernameController,
                  decoration: const InputDecoration(
                    labelText: 'Nombre de usuario',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _passwordController,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: 'Contraseña maestra',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                if (_biometricAvailable) ...[
                  CheckboxListTile(
                    value: _enableBiometric,
                    onChanged: (v) => setState(() => _enableBiometric = v ?? false),
                    title: const Text('Usar biometría en próximos accesos'),
                    controlAffinity: ListTileControlAffinity.leading,
                  ),
                  const SizedBox(height: 8),
                ],
                if (_error != null) ...[
                  Text(_error!, style: const TextStyle(color: Colors.red)),
                  const SizedBox(height: 12),
                ],
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: auth.isLoading ? null : _submit,
                    child: auth.isLoading
                        ? const CircularProgressIndicator()
                        : const Text('Iniciar sesión'),
                  ),
                ),
                const SizedBox(height: 12),
                if (_biometricAvailable) ...[
                  IconButton(
                    tooltip: 'Entrar con biometría',
                    iconSize: 48,
                    onPressed: _biometricBusy ? null : _quickBiometricLogin,
                    icon: _biometricBusy
                        ? const SizedBox(
                            width: 32,
                            height: 32,
                            child: CircularProgressIndicator(strokeWidth: 3),
                          )
                        : const Icon(Icons.fingerprint),
                  ),
                  const SizedBox(height: 4),
                ],
                TextButton(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const RegisterScreen()),
                    );
                  },
                  child: const Text('¿No tienes cuenta? Regístrate'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}