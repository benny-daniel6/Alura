import 'package:dio/dio.dart';
import '../../../core/constants/api_constants.dart';
import '../../../core/network/api_client.dart';
import 'package:google_sign_in/google_sign_in.dart';

class UserModel {
  final String id;
  final String email;
  final String? displayName;
  final String? avatarUrl;
  final String role;
  final int itemsCount;
  final int tryonCredits;
  final bool isPublic;
  final bool hasCompletedQuiz;
  final bool isGuest;

  UserModel({
    required this.id,
    required this.email,
    this.displayName,
    this.avatarUrl,
    required this.role,
    required this.itemsCount,
    required this.tryonCredits,
    required this.isPublic,
    required this.hasCompletedQuiz,
    this.isGuest = false,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id'] ?? '',
      email: json['email'] ?? '',
      displayName: json['display_name'],
      avatarUrl: json['avatar_url'],
      role: json['role'] ?? 'free',
      itemsCount: json['items_count'] ?? 0,
      tryonCredits: json['tryon_credits'] ?? 3,
      isPublic: json['is_public'] ?? false,
      hasCompletedQuiz: json['has_completed_quiz'] ?? false,
      isGuest: json['is_guest'] ?? false,
    );
  }
}

class AuthRepository {
  final ApiClient _apiClient = ApiClient();

  /// Google sign-in is shown only when the build carries the Web OAuth client ID
  /// (`--dart-define=GOOGLE_SERVER_CLIENT_ID=...apps.googleusercontent.com`).
  static const String googleServerClientId =
      String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID');
  static bool get googleSignInAvailable => googleServerClientId.isNotEmpty;
  static bool _googleInitialized = false;

  Future<UserModel> _session(Response response) async {
    await _apiClient.saveToken(response.data['access_token'] as String);
    return UserModel.fromJson(response.data['user']);
  }

  Future<UserModel> register(
      {required String email,
      required String password,
      String? displayName}) async {
    return _session(await _apiClient.dio.post(ApiConstants.authRegister, data: {
      'email': email.trim(),
      'password': password,
      if (displayName != null && displayName.trim().isNotEmpty)
        'display_name': displayName.trim(),
    }));
  }

  Future<UserModel> login(
      {required String email, required String password}) async {
    return _session(await _apiClient.dio.post(ApiConstants.authLogin, data: {
      'email': email.trim(),
      'password': password,
    }));
  }

  Future<UserModel> continueAsGuest() async =>
      _session(await _apiClient.dio.post(ApiConstants.authGuest));

  /// Turns the current guest account into a full account; the wardrobe and outfits stay.
  Future<UserModel> upgradeGuest(
      {required String email,
      required String password,
      String? displayName}) async {
    return _session(await _apiClient.dio.post(ApiConstants.authUpgrade, data: {
      'email': email.trim(),
      'password': password,
      if (displayName != null && displayName.trim().isNotEmpty)
        'display_name': displayName.trim(),
    }));
  }

  /// Changes the password; other devices are signed out, this one gets a fresh session.
  Future<void> changePassword(
      {required String currentPassword, required String newPassword}) async {
    await _session(await _apiClient.dio.post(ApiConstants.authPassword, data: {
      'current_password': currentPassword,
      'new_password': newPassword,
    }));
  }

  /// Ends every session of this account, including this one.
  Future<void> signOutEverywhere() async {
    await _apiClient.dio.post(ApiConstants.authLogoutAll);
    await signOut();
  }

  /// Returns null when the user closes the Google account picker.
  Future<UserModel?> signInWithGoogle() async {
    final google = GoogleSignIn.instance;
    if (!_googleInitialized) {
      await google.initialize(serverClientId: googleServerClientId);
      _googleInitialized = true;
    }
    final GoogleSignInAccount account;
    try {
      account = await google.authenticate();
    } on GoogleSignInException catch (e) {
      if (e.code == GoogleSignInExceptionCode.canceled) return null;
      rethrow;
    }
    final idToken = account.authentication.idToken;
    if (idToken == null) throw Exception('Google did not return an ID token.');
    return _session(await _apiClient.dio
        .post(ApiConstants.authGoogle, data: {'id_token': idToken}));
  }

  /// Mock dev sign-in allowing instant testing of the complete onboarding flow
  Future<UserModel> signInWithDevToken(String email) async {
    final response = await _apiClient.dio.post(
      ApiConstants.authDevToken,
      queryParameters: {'email': email},
    );

    final token = response.data['access_token'] as String;
    await _apiClient.saveToken(token);

    // Sync user with backend
    return await syncUser(displayName: email.split('@').first);
  }

  /// Syncs authenticated Firebase token with PostgreSQL user record
  Future<UserModel> syncUser({String? displayName, String? avatarUrl}) async {
    final response = await _apiClient.dio.post(
      ApiConstants.authSync,
      data: {
        if (displayName != null) 'display_name': displayName,
        if (avatarUrl != null) 'avatar_url': avatarUrl,
      },
    );
    return UserModel.fromJson(response.data);
  }

  /// Current profile, or null when there is no valid session (no token, or the server rejects it).
  /// Network failures are rethrown so the caller can offer a retry instead of a sign-in screen.
  Future<UserModel?> getProfile({Duration? timeout}) async {
    if ((await _apiClient.getToken()) == null) return null;
    try {
      final response = await _apiClient.dio.get(
        ApiConstants.usersMe,
        options: timeout == null
            ? null
            : Options(sendTimeout: timeout, receiveTimeout: timeout),
      );
      return UserModel.fromJson(response.data);
    } on DioException catch (e) {
      final code = e.response?.statusCode;
      if (code == 401 || code == 403 || code == 404) return null;
      rethrow;
    }
  }

  /// Privacy / GDPR compliance: wipe all data and clear session
  Future<bool> deleteMyData() async {
    try {
      final response =
          await _apiClient.dio.delete(ApiConstants.usersDeleteData);
      await _apiClient.clearToken();
      return response.data['success'] == true;
    } catch (e) {
      return false;
    }
  }

  Future<void> signOut() async {
    await _apiClient.clearToken();
    if (_googleInitialized) await GoogleSignIn.instance.signOut();
  }
}
