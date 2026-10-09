/// Entidad que representa una credencial guardada en la bóveda.
class Credential {
  final String id;
  final String sitioWeb;
  final String loginUser;
  final String password;
  final String? categoria;

  const Credential({
    required this.id,
    required this.sitioWeb,
    required this.loginUser,
    required this.password,
    this.categoria,
  });

  factory Credential.fromJson(Map<String, dynamic> json) {
    return Credential(
      id: json['id'] as String? ?? '',
      sitioWeb: json['sitio_web'] as String? ?? '',
      loginUser: json['login_user'] as String? ?? '',
      password: json['password'] as String? ?? '',
      categoria: json['categoria'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'sitio_web': sitioWeb,
      'login_user': loginUser,
      'password': password,
      'categoria': categoria,
    };
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Credential &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          sitioWeb == other.sitioWeb &&
          loginUser == other.loginUser &&
          password == other.password &&
          categoria == other.categoria;

  @override
  int get hashCode => Object.hash(id, sitioWeb, loginUser, password, categoria);
}