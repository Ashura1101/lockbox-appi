import 'package:bcrypt/bcrypt.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Bcrypt Fallback Hashing Tests', () {
    test('genera hash bcrypt y valida contraseña correcta e incorrecta', () {
      const masterPassword = 'MasterPassword_2026!';
      final hash = BCrypt.hashpw(masterPassword, BCrypt.gensalt(logRounds: 10));

      expect(hash, startsWith(r'$2a$10$'));
      expect(BCrypt.checkpw(masterPassword, hash), isTrue);
      expect(BCrypt.checkpw('WrongPassword', hash), isFalse);
    });
  });
}
