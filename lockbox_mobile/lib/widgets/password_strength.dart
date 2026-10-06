import 'package:flutter/material.dart';

/// Resultado del análisis de fortaleza de una contraseña.
class PasswordStrength {
  final double value;
  final String label;
  final Color color;

  const PasswordStrength(this.value, this.label, this.color);
}

/// Evalúa la fortaleza de [password] por longitud, mayúsculas, minúsculas,
/// números y símbolos, devolviendo un valor 0..1 junto a etiqueta y color.
PasswordStrength evaluatePasswordStrength(String password) {
  if (password.isEmpty) {
    return const PasswordStrength(0, 'Sin contraseña', Colors.grey);
  }

  var score = 0;
  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (RegExp(r'[A-Z]').hasMatch(password)) score++;
  if (RegExp(r'[a-z]').hasMatch(password)) score++;
  if (RegExp(r'[0-9]').hasMatch(password)) score++;
  if (RegExp(r'[^A-Za-z0-9]').hasMatch(password)) score++;

  if (score <= 2) return const PasswordStrength(0.33, 'Débil', Colors.red);
  if (score <= 4) return const PasswordStrength(0.66, 'Media', Colors.amber);
  return const PasswordStrength(1.0, 'Fuerte', Colors.green);
}

/// Barra de progreso de color que refleja la fortaleza de la contraseña.
class PasswordStrengthIndicator extends StatelessWidget {
  final String password;

  const PasswordStrengthIndicator({super.key, required this.password});

  @override
  Widget build(BuildContext context) {
    final strength = evaluatePasswordStrength(password);
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LinearProgressIndicator(
            value: strength.value,
            minHeight: 6,
            backgroundColor: Colors.white12,
            valueColor: AlwaysStoppedAnimation<Color>(strength.color),
          ),
          const SizedBox(height: 4),
          Text(
            strength.label,
            style: TextStyle(color: strength.color, fontSize: 12),
          ),
        ],
      ),
    );
  }
}