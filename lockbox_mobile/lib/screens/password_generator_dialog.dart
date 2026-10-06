import 'dart:math';

import 'package:flutter/material.dart';

import '../widgets/password_strength.dart';

/// Muestra un diálogo del generador avanzado de contraseñas y retorna la
/// clave elegida por el usuario, o `null` si cancela.
Future<String?> showPasswordGeneratorDialog(BuildContext context) {
  return showDialog<String>(
    context: context,
    builder: (_) => const PasswordGeneratorDialog(),
  );
}

/// Diálogo interactivo para generar contraseñas seguras de forma configurable.
class PasswordGeneratorDialog extends StatefulWidget {
  const PasswordGeneratorDialog({super.key});

  @override
  State<PasswordGeneratorDialog> createState() =>
      _PasswordGeneratorDialogState();
}

class _PasswordGeneratorDialogState extends State<PasswordGeneratorDialog> {
  static const String _upper = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  static const String _lower = 'abcdefghijklmnopqrstuvwxyz';
  static const String _digits = '0123456789';
  static const String _symbols = '!@#\$%^&*';

  final _random = Random.secure();
  double _length = 16;
  bool _useUpper = true;
  bool _useLower = true;
  bool _useDigits = true;
  bool _useSymbols = true;
  late String _password;

  @override
  void initState() {
    super.initState();
    _password = _generate();
  }

  String get _charset {
    final buffer = StringBuffer();
    if (_useLower) buffer.write(_lower);
    if (_useUpper) buffer.write(_upper);
    if (_useDigits) buffer.write(_digits);
    if (_useSymbols) buffer.write(_symbols);
    return buffer.toString();
  }

  String _generate() {
    final chars = _charset;
    if (chars.isEmpty) return '';
    final buffer = StringBuffer();
    for (var i = 0; i < _length.round(); i++) {
      buffer.write(chars[_random.nextInt(chars.length)]);
    }
    return buffer.toString();
  }

  void _refresh() {
    setState(() => _password = _generate());
  }

  @override
  Widget build(BuildContext context) {
    final hasSelection = _charset.isNotEmpty;

    return AlertDialog(
      title: const Text('Generador de contraseñas'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text('Longitud:'),
                const SizedBox(width: 8),
                Expanded(
                  child: Slider(
                    value: _length,
                    min: 8,
                    max: 64,
                    divisions: 56,
                    label: _length.round().toString(),
                    onChanged: (value) {
                      setState(() {
                        _length = value;
                        _password = _generate();
                      });
                    },
                  ),
                ),
                SizedBox(
                  width: 24,
                  child: Text(
                    _length.round().toString(),
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            const Divider(),
            SwitchListTile(
              title: const Text('Mayúsculas (A-Z)'),
              value: _useUpper,
              onChanged: (value) {
                setState(() => _useUpper = value);
                _refresh();
              },
            ),
            SwitchListTile(
              title: const Text('Minúsculas (a-z)'),
              value: _useLower,
              onChanged: (value) {
                setState(() => _useLower = value);
                _refresh();
              },
            ),
            SwitchListTile(
              title: const Text('Números (0-9)'),
              value: _useDigits,
              onChanged: (value) {
                setState(() => _useDigits = value);
                _refresh();
              },
            ),
            SwitchListTile(
              title: const Text('Símbolos (!@#\$%^&*)'),
              value: _useSymbols,
              onChanged: (value) {
                setState(() => _useSymbols = value);
                _refresh();
              },
            ),
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFF1E1B2E),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.white12),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: SelectableText(
                      _password.isEmpty ? 'Selecciona al menos un grupo' : _password,
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 16,
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Regenerar',
                    icon: const Icon(Icons.refresh_rounded),
                    onPressed: hasSelection ? _refresh : null,
                  ),
                ],
              ),
            ),
            PasswordStrengthIndicator(password: _password),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          onPressed: hasSelection ? () => Navigator.pop(context, _password) : null,
          child: const Text('Usar esta contraseña'),
        ),
      ],
    );
  }
}