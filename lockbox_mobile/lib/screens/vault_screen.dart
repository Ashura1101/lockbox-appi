import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/auth_controller.dart';
import '../models/credential.dart';
import '../services/secure_clipboard_service.dart';
import 'add_credential_screen.dart';

/// Pantalla principal que muestra la bóveda de credenciales.
class VaultScreen extends StatefulWidget {
  const VaultScreen({super.key});

  @override
  State<VaultScreen> createState() => _VaultScreenState();
}

class _VaultScreenState extends State<VaultScreen> {
  static const _categorias = [
    'Todas',
    'Trabajo',
    'Redes Sociales',
    'Bancos',
    'Juegos',
    'Otros',
  ];

  final _clipboard = SecureClipboardService();
  final _searchController = TextEditingController();
  String _query = '';
  String _categoriaSeleccionada = 'Todas';
  final Set<String> _eliminando = <String>{};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AuthController>().loadCredentials();
    });
  }

  @override
  void dispose() {
    _clipboard.dispose();
    _searchController.dispose();
    super.dispose();
  }

  List<dynamic> _filtrar(List<dynamic> credenciales) {
    return credenciales.where((cred) {
      final coincideCategoria = _categoriaSeleccionada == 'Todas' ||
          (cred.categoria ?? '').trim().toLowerCase() ==
              _categoriaSeleccionada.trim().toLowerCase();
      final q = _query.trim().toLowerCase();
      final coincideTexto = q.isEmpty ||
          cred.sitioWeb.toLowerCase().contains(q) ||
          cred.loginUser.toLowerCase().contains(q);
      return coincideCategoria && coincideTexto;
    }).toList();
  }

  Future<void> _copiarPassword(Credential cred) async {
    await _clipboard.copyWithAutoClear(
      cred.password,
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

  Future<void> _eliminarCredencial(Credential cred) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Eliminar credencial'),
        content: Text('¿Seguro que deseas eliminar la credencial de "${cred.sitioWeb}"?'),
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
    if (_eliminando.contains(cred.id)) return;
    setState(() => _eliminando.add(cred.id));
    final auth = context.read<AuthController>();
    try {
      await auth.deleteCredential(cred.id);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error al eliminar: $e')),
      );
    } finally {
      if (mounted) setState(() => _eliminando.remove(cred.id));
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final filtradas = _filtrar(auth.credentials);

    return Scaffold(
      backgroundColor: const Color(0xFF121218),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text(
          'Mi Bóveda',
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 24),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout_rounded, color: Colors.redAccent),
            onPressed: () => context.read<AuthController>().logout(),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: const Color(0xFF6C5CE7),
        foregroundColor: Colors.white,
        onPressed: () {
          Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const AddCredentialScreen()),
          );
        },
        child: const Icon(Icons.add),
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16.0),
        child: Column(
          children: [
            TextField(
              controller: _searchController,
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                hintText: 'Buscar credenciales...',
                hintStyle: TextStyle(color: Colors.white.withOpacity(0.5)),
                prefixIcon: const Icon(Icons.search_rounded, color: Color(0xFF6C5CE7)),
                filled: true,
                fillColor: const Color(0xFF1E1B2E),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(16),
                  borderSide: BorderSide.none,
                ),
              ),
              onChanged: (val) => setState(() => _query = val),
            ),
            const SizedBox(height: 16),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: _categorias.map((cat) {
                  final isSelected = cat == _categoriaSeleccionada;
                  return Padding(
                    padding: const EdgeInsets.only(right: 8.0),
                    child: ChoiceChip(
                      label: Text(cat),
                      selected: isSelected,
                      selectedColor: const Color(0xFF6C5CE7),
                      backgroundColor: const Color(0xFF1E1B2E),
                      labelStyle: TextStyle(
                        color: isSelected ? Colors.white : Colors.white60,
                      ),
                      onSelected: (selected) {
                        if (selected) setState(() => _categoriaSeleccionada = cat);
                      },
                    ),
                  );
                }).toList(),
              ),
            ),
            const SizedBox(height: 16),
            Expanded(
              child: auth.credentials.isEmpty
                  ? const Center(
                      child: Text(
                        'No tienes credenciales guardadas.',
                        style: TextStyle(color: Colors.white60),
                      ),
                    )
                  : filtradas.isEmpty
                      ? const Center(
                          child: Text(
                            'Sin resultados para la búsqueda.',
                            style: TextStyle(color: Colors.white60),
                          ),
                        )
                      : RefreshIndicator(
                          onRefresh: () =>
                              context.read<AuthController>().refreshCredentials(),
                          child: ListView.builder(
                            physics: const AlwaysScrollableScrollPhysics(),
                            padding: const EdgeInsets.only(bottom: 88),
                            itemCount: filtradas.length,
                            itemBuilder: (context, index) {
                              final cred = filtradas[index];
                              return _CredentialCard(
                                cred: cred,
                                isDeleting: _eliminando.contains(cred.id),
                                onTap: () {
                                  Navigator.of(context).push(
                                    MaterialPageRoute(
                                      builder: (_) =>
                                          AddCredentialScreen(credential: cred),
                                    ),
                                  );
                                },
                                onCopy: () => _copiarPassword(cred),
                                onDelete: () => _eliminarCredencial(cred),
                              );
                            },
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CredentialCard extends StatelessWidget {
  final Credential cred;
  final VoidCallback onTap;
  final VoidCallback onCopy;
  final VoidCallback onDelete;
  final bool isDeleting;

  const _CredentialCard({
    required this.cred,
    required this.onTap,
    required this.onCopy,
    required this.onDelete,
    this.isDeleting = false,
  });

  @override
  Widget build(BuildContext context) {
    final card = Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1B2E),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white10),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: CircleAvatar(
          backgroundColor: const Color(0xFF6C5CE7).withOpacity(0.2),
          child: const Icon(Icons.lock_outline, color: Color(0xFF6C5CE7)),
        ),
        title: Text(
          cred.sitioWeb,
          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
        subtitle: Text(
          isDeleting ? 'Eliminando credencial...' : cred.loginUser,
          style: TextStyle(
            color: isDeleting ? const Color(0xFFFBBF24) : Colors.white60,
          ),
        ),
        onTap: isDeleting ? null : onTap,
        trailing: isDeleting
            ? const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    icon: const Icon(Icons.copy_rounded, color: Colors.white70),
                    onPressed: onCopy,
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline_rounded, color: Colors.redAccent),
                    onPressed: onDelete,
                  ),
                ],
              ),
      ),
    );

    if (isDeleting) {
      return Opacity(opacity: 0.55, child: card);
    }
    return card;
  }
}