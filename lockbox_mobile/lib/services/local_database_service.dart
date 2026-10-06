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
      version: 1,
      onCreate: _createDB,
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
        updated_at TEXT NOT NULL,
        is_synced INTEGER NOT NULL DEFAULT 0
      )
    ''');
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
        'updated_at': now,
        'is_synced': 1,
      });
    }
  }
}