import '../../../core/widgets/theme_toggle_button.dart';
import '../../../core/widgets/server_settings_dialog.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../../stylist/presentation/stylist_screen.dart' show describeApiError;
import '../../../core/theme/app_theme.dart';
import '../data/auth_repository.dart';
import '../../onboarding/presentation/quiz_screen.dart';
import '../../home/presentation/home_shell_screen.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _emailController = TextEditingController(
      text: kDebugMode ? 'curator@aura-wardrobe.app' : '');

  /// Developer sign-in (no password) exists only for debug builds against a development server.
  /// Real sign-in (e.g. Firebase) replaces it before release.
  static const bool _devLoginAvailable =
      kDebugMode || bool.fromEnvironment('ALURA_DEV_LOGIN');
  final _authRepo = AuthRepository();
  bool _isLoading = false;
  String? _errorMessage;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  Future<void> _handleDevLogin() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final user =
          await _authRepo.signInWithDevToken(_emailController.text.trim());
      if (!mounted) return;

      if (user.hasCompletedQuiz) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => HomeShellScreen(user: user)),
        );
      } else {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => QuizScreen(user: user)),
        );
      }
    } catch (e) {
      setState(() {
        _errorMessage = describeApiError(e);
      });
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return DecoratedBox(
      decoration: AuraColors.pageBackground,
      child: Scaffold(
        backgroundColor: Colors.transparent,
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          elevation: 0,
          actions: [
            const ThemeToggleButton(),
            IconButton(
              tooltip: 'Server',
              icon: Icon(Icons.dns_outlined, color: AuraColors.textSecondary),
              onPressed: () async {
                if (await showServerSettingsDialog(context) &&
                    context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                        content: Text('Connected to server'),
                        backgroundColor: AuraColors.success),
                  );
                }
              },
            ),
          ],
        ),
        body: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding:
                  const EdgeInsets.symmetric(horizontal: 28.0, vertical: 24.0),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Brand Header
                  const SizedBox(height: 20),
                  Center(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 6),
                      decoration: BoxDecoration(
                        border: Border.all(
                            color: AuraColors.champagne.withOpacity(0.5)),
                        borderRadius: BorderRadius.circular(20),
                        color: AuraColors.champagne.withOpacity(0.08),
                      ),
                      child: Text(
                        'AI STYLIST & WARDROBE',
                        style: theme.textTheme.labelMedium?.copyWith(
                          color: AuraColors.champagneLight,
                          letterSpacing: 2.0,
                          fontWeight: FontWeight.w600,
                          fontSize: 11,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'A L U R A',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.displayLarge?.copyWith(
                      letterSpacing: 6.0,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Your digital wardrobe, curated by intelligence.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      color: AuraColors.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 44),

                  // Error Notification
                  if (_errorMessage != null) ...[
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AuraColors.error.withOpacity(0.12),
                        border: Border.all(
                            color: AuraColors.error.withOpacity(0.4)),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        _errorMessage!,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: AuraColors.error,
                        ),
                      ),
                    ),
                    const SizedBox(height: 20),
                  ],

                  if (_devLoginAvailable) ...[
                    TextField(
                      controller: _emailController,
                      keyboardType: TextInputType.emailAddress,
                      autocorrect: false,
                      textInputAction: TextInputAction.go,
                      onSubmitted: (_) => _isLoading ? null : _handleDevLogin(),
                      style: TextStyle(color: AuraColors.textPrimary),
                      decoration: InputDecoration(
                        labelText: 'Email',
                        prefixIcon: Icon(Icons.email_outlined,
                            color: AuraColors.textTertiary),
                      ),
                    ),
                    const SizedBox(height: 20),
                    ElevatedButton(
                      onPressed: _isLoading ? null : _handleDevLogin,
                      child: _isLoading
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white),
                            )
                          : const Text('Continue with developer sign-in'),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Development build: no password needed. Real sign-in is added before release.',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium?.copyWith(fontSize: 11),
                    ),
                  ] else
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(
                        color: AuraColors.surface,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: AuraColors.border),
                      ),
                      child: Column(
                        children: [
                          Icon(Icons.hourglass_top_rounded,
                              color: AuraColors.accentIris),
                          const SizedBox(height: 10),
                          Text('Sign-in is coming soon',
                              style: theme.textTheme.titleMedium),
                          const SizedBox(height: 6),
                          Text(
                            "Alura accounts aren't open yet. Check back shortly!",
                            textAlign: TextAlign.center,
                            style: theme.textTheme.bodyMedium,
                          ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 28),

                  // Privacy assurance
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.lock,
                          size: 14, color: AuraColors.textTertiary),
                      const SizedBox(width: 6),
                      Text(
                        'Your photos stay private. Delete your data anytime.',
                        style:
                            theme.textTheme.bodyMedium?.copyWith(fontSize: 11),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
