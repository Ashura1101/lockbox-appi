import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';

class LocalDatabaseService {
  static final LocalDatabaseService instance = LocalDatabaseService._init();
  static Database? _database;

  LocalDatabaseService._init();

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDB('lockbox_offline.db');
    return _database!;
  }

  Future<Database> _initDB(String filePath) async {
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, filePath);

    return await openDatabase(
      path,
      version: 2,
      onCreate: _createDB,
      onUpgrade: _onUpgrade,
    );
  }

  Future<void> _createDB(Database db, int version) async {
    await db.execute('''
      CREATE TABLE vault_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        remote_id TEXT,
        title TEXT NOT NULL,
        username TEXT NOT NULL,
        encrypted_password TEXT NOT NULL,
        categoria TEXT,
        updated_at TEXT NOT NULL,
        is_synced INTEGER NOT NULL DEFAULT 0
      )
    ''');
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    if (oldVersion < 2) {
      await db.execute('ALTER TABLE vault_items ADD COLUMN categoria TEXT');
    }
  }

  Future<int> insertVaultItem(Map<String, dynamic> item) async {
    final db = await instance.database;
    return await db.insert('vault_items', item);
  }

  Future<List<Map<String, dynamic>>> getVaultItems() async {
    final db = await instance.database;
    return await db.query('vault_items', orderBy: 'updated_at DESC');
  }

  Future<int> updateSyncStatus(int id, String remoteId, int isSynced) async {
    final db = await instance.database;
    return await db.update(
      'vault_items',
      {'remote_id': remoteId, 'is_synced': isSynced},
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  Future<void> upsertVaultItem({
    required String remoteId,
    required String title,
    required String username,
    required String encryptedPassword,
    String? categoria,
  }) async {
    final db = await instance.database;
    final existing = await db.query(
      'vault_items',
      where: 'remote_id = ?',
      whereArgs: [remoteId],
      limit: 1,
    );
    final now = DateTime.now().toIso8601String();

    if (existing.isNotEmpty) {
      await db.update(
        'vault_items',
        {
          'title': title,
          'username': username,
          'encrypted_password': encryptedPassword,
          'categoria': categoria,
          'updated_at': now,
          'is_synced': 1,
        },
        where: 'remote_id = ?',
        whereArgs: [remoteId],
      );
    } else {
      await db.insert('vault_items', {
        'remote_id': remoteId,
        'title': title,
        'username': username,
        'encrypted_password': encryptedPassword,
        'categoria': categoria,
        'updated_at': now,
        'is_synced': 1,
      });
    }
  }

  /// Elimina registros locales que ya fueron sincronizados previamente (`is_synced = 1`),
  /// pero cuyo `remote_id` ya no existe en el conjunto de IDs autoritativos devueltos por el servidor.
  ///
  /// NUNCA elimina registros locales pendientes de sincronización (`is_synced = 0`).
  Future<void> deleteOrphanedSyncedItems(Set<String> validRemoteIds) async {
    final db = await instance.database;
    final existingSynced = await db.query(
      'vault_items',
      columns: ['id', 'remote_id'],
      where: 'is_synced = 1 AND remote_id IS NOT NULL',
    );

    final idsToDelete = <int>[];
    for (final row in existingSynced) {
      final remoteId = row['remote_id'] as String?;
      if (remoteId != null && remoteId.isNotEmpty && !validRemoteIds.contains(remoteId)) {
        idsToDelete.add(row['id'] as int);
      }
    }

    if (idsToDelete.isNotEmpty) {
      final batch = db.batch();
      for (final id in idsToDelete) {
        batch.delete('vault_items', where: 'id = ?', whereArgs: [id]);
      }
      await batch.commit(noResult: true);
    }
  }
}