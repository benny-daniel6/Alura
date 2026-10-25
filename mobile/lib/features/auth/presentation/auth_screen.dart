import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/server_settings_dialog.dart';
import '../../../core/widgets/theme_toggle_button.dart';
import '../../home/presentation/home_shell_screen.dart';
import '../../onboarding/presentation/quiz_screen.dart';
import '../../stylist/presentation/stylist_screen.dart' show describeApiError;
import '../data/auth_repository.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _authRepo = AuthRepository();
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

  /// Developer sign-in (no password) exists only for debug builds against a development server.
  static const bool _devLoginAvailable =
      kDebugMode || bool.fromEnvironment('ALURA_DEV_LOGIN');

  bool _creatingAccount = false;
  bool _obscurePassword = true;
  bool _isLoading = false;
  String? _errorMessage;

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  void _enterApp(UserModel user) {
    Navigator.of(context).pushReplacement(MaterialPageRoute(
      builder: (_) => user.hasCompletedQuiz
          ? HomeShellScreen(user: user)
          : QuizScreen(user: user),
    ));
  }

  Future<void> _run(Future<UserModel?> Function() action) async {
    FocusScope.of(context).unfocus();
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final user = await action();
      if (!mounted || user == null) return;
      _enterApp(user);
    } catch (e) {
      if (mounted) setState(() => _errorMessage = describeApiError(e));
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _submitEmail() {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    _run(() => _creatingAccount
        ? _authRepo.register(
            email: _emailController.text,
            password: _passwordController.text,
            displayName: _nameController.text,
          )
        : _authRepo.login(
            email: _emailController.text, password: _passwordController.text));
  }

  Future<void> _devLogin() async {
    final email = _emailController.text.trim().isEmpty
        ? 'curator@aura-wardrobe.app'
        : _emailController.text.trim();
    await _run(() => _authRepo.signInWithDevToken(email));
  }

  String? _validateEmail(String? v) {
    final value = v?.trim() ?? '';
    if (value.isEmpty) return 'Enter your email';
    if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(value))
      return 'Enter a valid email';
    return null;
  }

  String? _validatePassword(String? v) {
    final value = v ?? '';
    if (value.isEmpty) return 'Enter your password';
    if (_creatingAccount && value.length < 8)
      return 'Use at least 8 characters';
    return null;
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
            if (serverSettingsAvailable)
              IconButton(
                tooltip: 'Server',
                icon: Icon(Icons.dns_outlined, color: AuraColors.textSecondary),
                onPressed: () => showServerSettingsDialog(context),
              ),
          ],
        ),
        body: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 12),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'A L U R A',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.displayLarge?.copyWith(
                          letterSpacing: 6, fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Your wardrobe, styled by AI.',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 28),
                    SegmentedButton<bool>(
                      showSelectedIcon: false,
                      style: SegmentedButton.styleFrom(
                        selectedBackgroundColor:
                            AuraColors.accentIris.withOpacity(0.18),
                        selectedForegroundColor: AuraColors.textPrimary,
                        foregroundColor: AuraColors.textSecondary,
                        side: BorderSide(color: AuraColors.border),
                      ),
                      segments: const [
                        ButtonSegment(value: false, label: Text('Sign in')),
                        ButtonSegment(
                            value: true, label: Text('Create account')),
                      ],
                      selected: {_creatingAccount},
                      onSelectionChanged: (s) => setState(() {
                        _creatingAccount = s.first;
                        _errorMessage = null;
                      }),
                    ),
                    const SizedBox(height: 18),
                    if (_errorMessage != null) ...[
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: AuraColors.error.withOpacity(0.12),
                          border: Border.all(
                              color: AuraColors.error.withOpacity(0.4)),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(_errorMessage!,
                            style: theme.textTheme.bodyMedium
                                ?.copyWith(color: AuraColors.error)),
                      ),
                      const SizedBox(height: 14),
                    ],
                    if (_creatingAccount) ...[
                      TextFormField(
                        controller: _nameController,
                        textCapitalization: TextCapitalization.words,
                        textInputAction: TextInputAction.next,
                        autofillHints: const [AutofillHints.name],
                        style: TextStyle(color: AuraColors.textPrimary),
                        decoration: InputDecoration(
                          labelText: 'Name (optional)',
                          prefixIcon: Icon(Icons.person_outline,
                              color: AuraColors.textTertiary),
                        ),
                      ),
                      const SizedBox(height: 12),
                    ],
                    TextFormField(
                      controller: _emailController,
                      keyboardType: TextInputType.emailAddress,
                      autocorrect: false,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [AutofillHints.email],
                      validator: _validateEmail,
                      style: TextStyle(color: AuraColors.textPrimary),
                      decoration: InputDecoration(
                        labelText: 'Email',
                        prefixIcon: Icon(Icons.email_outlined,
                            color: AuraColors.textTertiary),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _passwordController,
                      obscureText: _obscurePassword,
                      textInputAction: TextInputAction.done,
                      autofillHints: [
                        _creatingAccount
                            ? AutofillHints.newPassword
                            : AutofillHints.password
                      ],
                      validator: _validatePassword,
                      onFieldSubmitted: (_) =>
                          _isLoading ? null : _submitEmail(),
                      style: TextStyle(color: AuraColors.textPrimary),
                      decoration: InputDecoration(
                        labelText: 'Password',
                        helperText:
                            _creatingAccount ? 'At least 8 characters' : null,
                        prefixIcon: Icon(Icons.lock_outline,
                            color: AuraColors.textTertiary),
                        suffixIcon: IconButton(
                          tooltip: _obscurePassword
                              ? 'Show password'
                              : 'Hide password',
                          icon: Icon(
                              _obscurePassword
                                  ? Icons.visibility_outlined
                                  : Icons.visibility_off_outlined,
                              color: AuraColors.textTertiary),
                          onPressed: () => setState(
                              () => _obscurePassword = !_obscurePassword),
                        ),
                      ),
                    ),
                    const SizedBox(height: 20),
                    ElevatedButton(
                      onPressed: _isLoading ? null : _submitEmail,
                      child: _isLoading
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white),
                            )
                          : Text(
                              _creatingAccount ? 'Create account' : 'Sign in'),
                    ),
                    if (AuthRepository.googleSignInAvailable) ...[
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: _isLoading
                            ? null
                            : () => _run(_authRepo.signInWithGoogle),
                        icon: Icon(Icons.g_mobiledata,
                            size: 28, color: AuraColors.accentIris),
                        label: const Text('Continue with Google'),
                      ),
                    ],
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: _isLoading
                          ? null
                          : () => _run(_authRepo.continueAsGuest),
                      child: const Text('Continue as guest'),
                    ),
                    if (_devLoginAvailable)
                      TextButton(
                        onPressed: _isLoading ? null : _devLogin,
                        child: Text('Developer sign-in (debug builds only)',
                            style: theme.textTheme.bodyMedium
                                ?.copyWith(fontSize: 12)),
                      ),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.lock,
                            size: 14, color: AuraColors.textTertiary),
                        const SizedBox(width: 6),
                        Flexible(
                          child: Text(
                            'Your photos stay private. Delete your data anytime.',
                            style: theme.textTheme.bodyMedium
                                ?.copyWith(fontSize: 11),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
