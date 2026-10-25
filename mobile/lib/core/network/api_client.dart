import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../constants/api_constants.dart';

class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;

  late final Dio dio;
  static const String tokenKey = 'aura_auth_token';

  /// Set by the app root: navigates to the sign-in screen when the server rejects the session.
  static void Function()? onUnauthorized;

  ApiClient._internal() {
    dio = Dio(
      BaseOptions(
        baseUrl: ApiConstants.baseUrl,
        connectTimeout: const Duration(seconds: 6),
        receiveTimeout: const Duration(seconds: 20),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
      ),
    );

    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          // The server can be changed at runtime in Server settings
          options.baseUrl = ApiConstants.baseUrl;
          final token = await getToken();
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          return handler.next(options);
        },
        onError: (DioException error, handler) async {
          // A rejected session (expired or revoked token) sends the user back to sign-in
          final path = error.requestOptions.path;
          final isSessionCheck =
              path.endsWith(ApiConstants.usersMe) || path.contains('/auth/');
          if (error.response?.statusCode == 401 && !isSessionCheck) {
            await clearToken();
            onUnauthorized?.call();
          }
          return handler.next(error);
        },
      ),
    );
  }

  static const FlutterSecureStorage _secure = FlutterSecureStorage();
  String? _cachedToken;

  Future<void> saveToken(String token) async {
    _cachedToken = token;
    await _secure.write(key: tokenKey, value: token);
  }

  Future<String?> getToken() async {
    if (_cachedToken != null) return _cachedToken;
    _cachedToken = await _secure.read(key: tokenKey);
    if (_cachedToken == null) {
      // Builds before 1.0.0 kept the token in plain preferences: move it into secure storage
      final prefs = await SharedPreferences.getInstance();
      final legacy = prefs.getString(tokenKey);
      if (legacy != null) {
        await saveToken(legacy);
        await prefs.remove(tokenKey);
      }
    }
    return _cachedToken;
  }

  Future<void> clearToken() async {
    _cachedToken = null;
    await _secure.delete(key: tokenKey);
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(tokenKey);
  }
}
