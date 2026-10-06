/// Entidad que representa una categoría de credenciales.
class Category {
  final String id;
  final String nombre;

  const Category({required this.id, required this.nombre});

  factory Category.fromJson(Map<String, dynamic> json) {
    return Category(
      id: json['id'] as String? ?? '',
      nombre: json['nombre'] as String? ?? '',
    );
  }
}