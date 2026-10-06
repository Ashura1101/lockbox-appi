import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../services/local_database_service.dart';

class VaultRepository {
  final LocalDatabaseService _db = LocalDatabaseService.instance;

  // Reemplaza con la URL de tu API en Render
  final String baseUrl = 'https://lockbox-appi.onrender.com/api';

  /// Obtiene los elementos del cofre directamente desde la BD local (rápido y offline)
  Future<List<Map<String, dynamic>>> getVaultItems() async {
    return await _db.getVaultItems();
  }

  /// Agrega un elemento PRIMERO en SQLite local (éxito local inmediato) y
  /// luego intenta sincronizarlo con Render en segundo plano, sin bloquear la
  /// pantalla. Los errores de red NUNCA se re-lanzan hacia la interfaz.
  Future<void> addVaultItem({
    required String title,
    required String username,
    required String encryptedPassword,
    required String token,
  }) async {
    final now = DateTime.now().toIso8601String();

    // 1. Guardar localmente de inmediato (is_synced = 0)
    final localId = await _db.insertVaultItem({
      'title': title,
      'username': username,
      'encrypted_password': encryptedPassword,
      'updated_at': now,
      'is_synced': 0,
    });

    // 2. Sincronización con Render en segundo plano (fire-and-forget).
    unawaited(_syncItemToServer(
      localId: localId,
      title: title,
      username: username,
      encryptedPassword: encryptedPassword,
      token: token,
    ));
  }

  Future<void> _syncItemToServer({
    required int localId,
    required String title,
    required String username,
    required String encryptedPassword,
    required String token,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/vault'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode({
          'title': title,
          'username': username,
          'encrypted_password': encryptedPassword,
        }),
      ).timeout(const Duration(seconds: 5));

      if (response.statusCode == 200 || response.statusCode == 201) {
        final data = jsonDecode(response.body);
        final remoteId = data['id'].toString();

        // 3. Si el servidor lo recibió, actualizar como sincronizado (is_synced = 1)
        await _db.updateSyncStatus(localId, remoteId, 1);
      }
    } on SocketException catch (e) {
      debugPrint('Modo Offline: guardado localmente, pendiente de sincronización. ($e)');
    } on TimeoutException catch (e) {
      debugPrint('Modo Offline: guardado localmente, pendiente de sincronización. ($e)');
    } on http.ClientException catch (e) {
      debugPrint('Modo Offline: guardado localmente, pendiente de sincronización. ($e)');
    } catch (e) {
      debugPrint('Modo Offline: guardado localmente, pendiente de sincronización. ($e)');
    }
  }

  /// Fusiona credenciales traídas del servidor en la BD local, evitando
  /// duplicados (upsert por remote_id) y respetando los items no sincronizados.
  Future<void> syncCredentials(List<Map<String, dynamic>> credentials) async {
    for (final cred in credentials) {
      await _db.upsertVaultItem(
        remoteId: cred['id']?.toString() ?? '',
        title: cred['sitio_web'] as String? ?? '',
        username: cred['login_user'] as String? ?? '',
        encryptedPassword: cred['password'] as String? ?? '',
      );
    }
  }
}