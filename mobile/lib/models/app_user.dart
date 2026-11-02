class AppUser {
  final String username;
  final String role; // 'owner' or 'developer'
  final String token;

  AppUser({
    required this.username,
    required this.role,
    required this.token,
  });

  bool get isOwner => role.toLowerCase() == 'owner';
  bool get isDeveloper => role.toLowerCase() == 'developer';

  factory AppUser.fromJson(Map<String, dynamic> json) {
    return AppUser(
      username: json['username'] ?? json['sub'] ?? 'User',
      role: json['role'] ?? 'developer',
      token: json['access_token'] ?? json['token'] ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'username': username,
      'role': role,
      'access_token': token,
    };
  }
}
