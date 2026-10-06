import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/auth_controller.dart';
import '../models/credential.dart';
import '../services/secure_clipboard_service.dart';

/// Muestra los detalles de una credencial: permite ver/ocultar la contraseña,
/// copiarla (con autolimpieza) y eliminar la credencial.
class CredentialDetailScreen extends StatefulWidget {
  final Credential credential;

  const CredentialDetailScreen({super.key, required this.credential});

  @override
  State<CredentialDetailScreen> createState() => _CredentialDetailScreenState();
}

class _CredentialDetailScreenState extends State<CredentialDetailScreen> {
  final _clipboard = SecureClipboardService();
  bool _obscure = true;
  bool _isDeleting = false;

  @override
  void dispose() {
    _clipboard.dispose();
    super.dispose();
  }

  Future<void> _copy(String text) async {
    await _clipboard.copyWithAutoClear(
      text,
      onCleared: () {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Portapapeles limpiado por seguridad')),
        );
      },
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Copiado. Se limpiará en 30 segundos.')),
    );
  }

  Future<void> _delete() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Eliminar credencial'),
        content: Text('¿Seguro que deseas eliminar la credencial de "${widget.credential.sitioWeb}"?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Eliminar'),
          ),
        ],
      ),
    );

    if (confirm != true) return;
    if (!mounted) return;

    final auth = context.read<AuthController>();
    setState(() => _isDeleting = true);
    try {
      await auth.deleteCredential(widget.credential.id);
      if (!mounted) return;
      Navigator.of(context).pop();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error al eliminar: $e')),
      );
    } finally {
      if (mounted) setState(() => _isDeleting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cred = widget.credential;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Detalle de credencial'),
        actions: [
          IconButton(
            icon: const Icon(Icons.delete, color: Colors.red),
            onPressed: _isDeleting ? null : _delete,
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          _DetailRow(label: 'Sitio web', value: cred.sitioWeb),
          const SizedBox(height: 16),
          _DetailRow(label: 'Usuario', value: cred.loginUser, onCopy: () => _copy(cred.loginUser)),
          if (cred.categoria != null) ...[
            const SizedBox(height: 16),
            _DetailRow(label: 'Categoría', value: cred.categoria!),
          ],
          const SizedBox(height: 16),
          _DetailRow(
            label: 'Contraseña',
            value: _obscure ? '••••••••' : cred.password,
            onCopy: () => _copy(cred.password),
          ),
          const SizedBox(height: 24),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                  label: Text(_obscure ? 'Mostrar' : 'Ocultar'),
                  onPressed: () => setState(() => _obscure = !_obscure),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton.icon(
                  icon: const Icon(Icons.copy),
                  label: const Text('Copiar'),
                  onPressed: () => _copy(cred.password),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  final String label;
  final String value;
  final VoidCallback? onCopy;

  const _DetailRow({required this.label, required this.value, this.onCopy});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.grey, fontSize: 12)),
        const SizedBox(height: 4),
        Row(
          children: [
            Expanded(
              child: SelectableText(
                value,
                style: const TextStyle(fontSize: 16, fontFamily: 'monospace'),
              ),
            ),
            if (onCopy != null)
              IconButton(
                icon: const Icon(Icons.copy, size: 18),
                onPressed: onCopy,
              ),
          ],
        ),
      ],
    );
  }
}