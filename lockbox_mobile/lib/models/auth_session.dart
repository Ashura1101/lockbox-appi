/// Resultado del login: tokens JWT emitidos por el backend.
class AuthSession {
  final String accessToken;
  final String refreshToken;
  final String username;

  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.username,
  });

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      accessToken: json['access_token'] as String? ?? '',
      refreshToken: json['refresh_token'] as String? ?? '',
      username: json['username'] as String? ?? '',
    );
  }
}