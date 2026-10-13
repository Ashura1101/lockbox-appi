import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/auth_controller.dart';
import '../core/error_messages.dart';
import '../models/credential.dart';
import '../services/api_service.dart';
import '../widgets/password_strength.dart';
import 'password_generator_dialog.dart';

/// Formulario para crear o editar una credencial cifrada.
///
/// Si se pasa [credential], el formulario precarga sus datos y al guardar
/// ejecuta una actualización en la API; en caso contrario crea una nueva.
class AddCredentialScreen extends StatefulWidget {
  final Credential? credential;

  const AddCredentialScreen({super.key, this.credential});

  bool get isEditing => credential != null;

  @override
  State<AddCredentialScreen> createState() => _AddCredentialScreenState();
}

class _AddCredentialScreenState extends State<AddCredentialScreen> {
  static const List<String> _categorias = [
    'Trabajo',
    'Redes Sociales',
    'Bancos',
    'Juegos',
    'Otros',
  ];

  final _siteController = TextEditingController();
  final _userController = TextEditingController();
  final _passwordController = TextEditingController();
  late String _categoria;
  bool _isLoading = false;
  bool _obscure = true;
  bool _didConfirmDuplicate = false;
  String? _error;

  bool get _isEditing => widget.credential != null;

  @override
  void initState() {
    super.initState();
    _passwordController.addListener(_onPasswordChanged);
    final cred = widget.credential;
    final credCat = cred?.categoria?.trim().toLowerCase();
    _categoria = _categorias.firstWhere(
      (c) => c.toLowerCase() == credCat,
      orElse: () => 'Otros',
    );
    if (cred != null) {
      _siteController.text = cred.sitioWeb;
      _userController.text = cred.loginUser;
      _passwordController.text = cred.password;
    }
  }

  void _onPasswordChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _passwordController.removeListener(_onPasswordChanged);
    _siteController.dispose();
    _userController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  /// Abre el generador avanzado y, si el usuario acepta, inyecta la clave.
  Future<void> _openGenerator() async {
    final password = await showPasswordGeneratorDialog(context);
    if (password == null || !mounted) return;
    setState(() {
      _passwordController.text = password;
      _obscure = false;
    });
  }

  Future<void> _submit() async {
    final auth = context.read<AuthController>();
    final site = _siteController.text.trim();
    final user = _userController.text.trim();
    final password = _passwordController.text;

    setState(() => _error = null);

    if (site.isEmpty || user.isEmpty) {
      setState(() => _error = 'Completa todos los campos.');
      return;
    }

    // En creación, la contraseña es obligatoria. En edición, solo se envía
    // cuando difiera del valor original precargado (si no cambió, el payload
    // de update no incluye el campo `password`).
    if (!_isEditing && password.isEmpty) {
      setState(() => _error = 'Completa todos los campos.');
      return;
    }

    final String? passwordCambiada = _isEditing
        ? (password != widget.credential!.password ? password : null)
        : password;

    Future<void> guardar({bool confirmDuplicate = false}) async {
      if (_isEditing) {
        await auth.updateCredential(
          id: widget.credential!.id,
          sitioWeb: site,
          loginUser: user,
          password: passwordCambiada,
          categoria: _categoria,
          confirmDuplicate: confirmDuplicate,
        );
      } else {
        await auth.addCredential(
          sitioWeb: site,
          loginUser: user,
          password: password,
          categoria: _categoria,
          confirmDuplicate: confirmDuplicate,
        );
      }
    }

    setState(() => _isLoading = true);
    try {
      await guardar();
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (e is DuplicatePasswordException && !_didConfirmDuplicate) {
        if (!mounted) return;
        final confirmar = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Contraseña repetida'),
            content: Text('${e.message} ¿Guardar de todas formas?'),
            actions: [
              TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
              FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Guardar igual')),
            ],
          ),
        );
        _didConfirmDuplicate = confirmar == true;
        if (confirmar == true && mounted) {
          try {
            await guardar(confirmDuplicate: true);
            if (mounted) Navigator.of(context).pop();
          } catch (e2) {
            setState(() => _error = mensajeDeError(e2, accion: _isEditing ? 'guardar los cambios' : 'guardar la credencial'));
          }
        }
        return;
      }
      setState(() => _error = mensajeDeError(e, accion: _isEditing ? 'guardar los cambios' : 'guardar la credencial'));
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isEditing ? 'Editar Credencial' : 'Nueva credencial')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: _siteController,
                  decoration: const InputDecoration(
                    labelText: 'Sitio web / aplicación',
                    hintText: 'ej. github.com',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _userController,
                  decoration: const InputDecoration(
                    labelText: 'Usuario / correo',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                  value: _categoria,
                  decoration: const InputDecoration(
                    labelText: 'Categoría',
                    border: OutlineInputBorder(),
                  ),
                  items: _categorias
                      .map((cat) => DropdownMenuItem(
                            value: cat,
                            child: Text(cat),
                          ))
                      .toList(),
                  onChanged: (value) {
                    if (value != null) setState(() => _categoria = value);
                  },
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _passwordController,
                  obscureText: _obscure,
                  decoration: InputDecoration(
                    labelText: 'Contraseña',
                    border: const OutlineInputBorder(),
                    suffixIcon: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          tooltip: 'Generar contraseña segura',
                          icon: const Icon(Icons.auto_awesome, color: Color(0xFF6C5CE7)),
                          onPressed: _openGenerator,
                        ),
                        IconButton(
                          icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                          onPressed: () => setState(() => _obscure = !_obscure),
                        ),
                      ],
                    ),
                  ),
                ),
                PasswordStrengthIndicator(password: _passwordController.text),
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
                        : Text(_isEditing ? 'Guardar Cambios' : 'Guardar credencial'),
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