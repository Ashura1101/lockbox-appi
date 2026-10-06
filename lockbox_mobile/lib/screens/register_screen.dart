import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/auth_controller.dart';
import 'login_screen.dart';

/// Pantalla de registro de un nuevo usuario.
class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _isLoading = false;
  String? _error;
  String? _recoveryKey;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final auth = context.read<AuthController>();
    final username = _usernameController.text.trim();
    final password = _passwordController.text;
    final confirm = _confirmController.text;

    setState(() => _error = null);

    if (username.isEmpty || password.isEmpty) {
      setState(() => _error = 'Completa todos los campos.');
      return;
    }
    if (password.length < 8) {
      setState(() => _error = 'La contraseña maestra debe tener al menos 8 caracteres.');
      return;
    }
    if (password != confirm) {
      setState(() => _error = 'Las contraseñas no coinciden.');
      return;
    }

    setState(() => _isLoading = true);
    try {
      final recoveryKey = await auth.register(
        username: username,
        masterPassword: password,
      );
      setState(() => _recoveryKey = recoveryKey);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Registrarse')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: _recoveryKey != null
                ? _RecoveryKeyView(
                    recoveryKey: _recoveryKey!,
                    onContinue: () => Navigator.of(context).pushReplacement(
                      MaterialPageRoute(builder: (_) => const LoginScreen()),
                    ),
                  )
                : Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.person_add, size: 64, color: Color(0xFF6366F1)),
                      const SizedBox(height: 24),
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
                      TextField(
                        controller: _confirmController,
                        obscureText: true,
                        decoration: const InputDecoration(
                          labelText: 'Confirmar contraseña',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      if (_error != null) ...[
                        const SizedBox(height: 16),
                        Text(_error!, style: const TextStyle(color: Colors.red)),
                      ],
                      const SizedBox(height: 20),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton(
                          onPressed: _isLoading ? null : _submit,
                          child: _isLoading
                              ? const CircularProgressIndicator()
                              : const Text('Crear cuenta'),
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

class _RecoveryKeyView extends StatelessWidget {
  final String recoveryKey;
  final VoidCallback onContinue;

  const _RecoveryKeyView({required this.recoveryKey, required this.onContinue});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.check_circle, size: 64, color: Color(0xFF2ECC71)),
        const SizedBox(height: 24),
        Text('¡Cuenta creada!', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 16),
        const Text(
          'Tu Clave de Recuperación es:',
          style: TextStyle(color: Colors.grey),
        ),
        const SizedBox(height: 12),
        SelectableText(
          recoveryKey,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
            fontFamily: 'monospace',
          ),
        ),
        const SizedBox(height: 16),
        const Text(
          'Guárdala en un lugar seguro. No podrás volver a verla.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.orange),
        ),
        const SizedBox(height: 24),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            onPressed: onContinue,
            child: const Text('Ir a iniciar sesión'),
          ),
        ),
      ],
    );
  }
}