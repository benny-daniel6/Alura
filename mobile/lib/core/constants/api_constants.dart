import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

class ApiConstants {
  /// Build-time default, e.g. `--dart-define=API_BASE_URL=http://192.168.1.20:8000/api/v1`.
  static const String _overrideBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const String _serverPrefsKey = 'aura_server_base_url';

  /// Server chosen in the app's Server settings; wins over the build-time default.
  static String? _runtimeBaseUrl;

  static String get baseUrl {
    if (_runtimeBaseUrl != null) return _runtimeBaseUrl!;
    if (_overrideBaseUrl.isNotEmpty) return _overrideBaseUrl;
    if (Platform.isAndroid) {
      return 'http://10.0.2.2:8000/api/v1'; // Android emulator -> host machine
    }
    return 'http://127.0.0.1:8000/api/v1';
  }

  /// Loads the saved server address; call once before the first request.
  static Future<void> loadSavedServer() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_serverPrefsKey);
    if (saved != null && saved.isNotEmpty) _runtimeBaseUrl = saved;
  }

  /// Turns user input like `192.168.1.20`, `192.168.1.20:8000` or `https://api.example.com`
  /// into a full API base URL. Returns null if it is not a usable address.
  static String? normalizeServerInput(String input) {
    var text = input.trim();
    if (text.isEmpty) return null;
    if (!text.contains('://')) text = 'http://$text';
    final uri = Uri.tryParse(text);
    if (uri == null ||
        uri.host.isEmpty ||
        !(uri.scheme == 'http' || uri.scheme == 'https')) return null;
    final port = uri.hasPort ? uri.port : (uri.scheme == 'http' ? 8000 : 443);
    final path = uri.path.isEmpty || uri.path == '/'
        ? '/api/v1'
        : uri.path.replaceAll(RegExp(r'/+$'), '');
    return Uri(scheme: uri.scheme, host: uri.host, port: port, path: path)
        .toString();
  }

  static Future<void> saveServer(String baseUrl) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_serverPrefsKey, baseUrl);
    _runtimeBaseUrl = baseUrl;
  }

  static Future<void> resetServer() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_serverPrefsKey);
    _runtimeBaseUrl = null;
  }

  /// Server origin (scheme + host + port) used to resolve relative media paths.
  static String get origin => Uri.parse(baseUrl).origin;

  /// Stable image-cache key: the URL without its query, so signed links (which change) reuse the cache.
  static String mediaCacheKey(String url) => url.split('?').first;

  /// Development storage returns relative `/static/...` paths; S3 returns absolute URLs.
  static String? mediaUrl(String? path) {
    if (path == null || path.isEmpty) return null;
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    return '$origin${path.startsWith('/') ? '' : '/'}$path';
  }

  // Endpoints
  static const String authSync = '/auth/sync';
  static const String authDevToken = '/auth/dev-token';
  static const String authRegister = '/auth/register';
  static const String authLogin = '/auth/login';
  static const String authGuest = '/auth/guest';
  static const String authUpgrade = '/auth/upgrade';
  static const String authGoogle = '/auth/google';
  static const String authPassword = '/auth/password';
  static const String authLogoutAll = '/auth/logout-all';
  static const String usersMe = '/users/me';
  static const String usersPreferences = '/users/me/preferences';
  static const String usersDeleteData = '/users/me/delete-data';
  static const String wardrobeItems = '/wardrobe/items';
  static const String wardrobeUpload = '/wardrobe/items/upload';
  static const String wardrobeWear = '/wardrobe/items/wear';
  static const String stylistSuggest = '/stylist/suggest';
  static const String stylistWeather = '/stylist/weather';
  static const String stylistLookbook = '/stylist/lookbook';
  static const String outfits = '/outfits';
}
