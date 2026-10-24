import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/constants/api_constants.dart';
import 'core/network/api_client.dart';
import 'core/theme/app_theme.dart';
import 'core/widgets/server_settings_dialog.dart';
import 'features/auth/data/auth_repository.dart';
import 'features/auth/presentation/auth_screen.dart';
import 'features/onboarding/presentation/quiz_screen.dart';
import 'features/home/presentation/home_shell_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await ApiConstants.loadSavedServer();
  await AuraThemeController.instance.load();
  runApp(const ProviderScope(child: AuraApp()));
}

class AuraApp extends StatefulWidget {
  const AuraApp({super.key});

  @override
  State<AuraApp> createState() => _AuraAppState();
}

class _AuraAppState extends State<AuraApp> with WidgetsBindingObserver {
  final _themeController = AuraThemeController.instance;
  final _navigatorKey = GlobalKey<NavigatorState>();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _themeController.addListener(_onThemeChanged);
    ApiClient.onUnauthorized = () {
      _navigatorKey.currentState?.pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const AuthScreen()),
        (route) => false,
      );
    };
  }

  @override
  void dispose() {
    _themeController.removeListener(_onThemeChanged);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangePlatformBrightness() => _onThemeChanged();

  /// Widgets read AuraColors directly, so every element is rebuilt (keeping its state) on a theme switch.
  void _onThemeChanged() {
    setState(() {});
    void rebuild(Element el) {
      el.markNeedsBuild();
      el.visitChildren(rebuild);
    }

    (context as Element).visitChildren(rebuild);
  }

  @override
  Widget build(BuildContext context) {
    final palette = _themeController.paletteFor(
        WidgetsBinding.instance.platformDispatcher.platformBrightness);
    AuraColors.use(palette);
    SystemChrome.setSystemUIOverlayStyle(
        AuraThemeController.overlayFor(palette));
    return MaterialApp(
      title: 'Alura',
      debugShowCheckedModeBanner: false,
      theme: AuraTheme.themeFor(palette),
      navigatorKey: _navigatorKey,
      home: const AppInitializer(),
    );
  }
}

class AppInitializer extends StatefulWidget {
  const AppInitializer({super.key});

  @override
  State<AppInitializer> createState() => _AppInitializerState();
}

class _AppInitializerState extends State<AppInitializer> {
  final AuthRepository _authRepo = AuthRepository();
  bool _offline = false;

  @override
  void initState() {
    super.initState();
    _checkInitialState();
  }

  Future<void> _checkInitialState() async {
    setState(() => _offline = false);
    final UserModel? user;
    try {
      user = await _authRepo.getProfile(timeout: const Duration(seconds: 8));
    } catch (_) {
      if (mounted) setState(() => _offline = true);
      return;
    }
    if (!mounted) return;

    final Widget next = user == null
        ? const AuthScreen()
        : user.hasCompletedQuiz
            ? HomeShellScreen(user: user)
            : QuizScreen(user: user);
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        pageBuilder: (_, __, ___) => next,
        transitionsBuilder: (_, animation, __, child) =>
            FadeTransition(opacity: animation, child: child),
        transitionDuration: const Duration(milliseconds: 350),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return DecoratedBox(
      decoration: AuraColors.pageBackground,
      child: Scaffold(
        backgroundColor: Colors.transparent,
        body: SafeArea(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    'A L U R A',
                    style: TextStyle(
                      fontSize: 28,
                      letterSpacing: 4.0,
                      fontWeight: FontWeight.w700,
                      color: AuraColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 24),
                  if (!_offline)
                    SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                          color: AuraColors.accentIris, strokeWidth: 2),
                    )
                  else ...[
                    Icon(Icons.cloud_off_outlined,
                        size: 40, color: AuraColors.textTertiary),
                    const SizedBox(height: 12),
                    Text("Can't reach Alura",
                        style: theme.textTheme.titleMedium),
                    const SizedBox(height: 6),
                    Text(
                      'Check your internet connection. If you run your own Alura server, check its address.',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 20),
                    ElevatedButton.icon(
                      onPressed: _checkInitialState,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Try again'),
                    ),
                    TextButton.icon(
                      onPressed: () async {
                        if (await showServerSettingsDialog(context))
                          _checkInitialState();
                      },
                      icon: const Icon(Icons.dns_outlined),
                      label: const Text('Server address'),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
