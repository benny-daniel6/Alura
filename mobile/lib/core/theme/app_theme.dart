import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// One complete colour set. The app has a dark editorial palette and a light white + mint-green one.
class AuraPalette {
  final Brightness brightness;
  final Color background;
  final Color surface;
  final Color surfaceLight;
  final Color card;
  final Color border;
  final Color accentIris;
  final Color accentIrisGlow;
  final Color champagne;
  final Color champagneLight;
  final Color success;
  final Color error;
  final Color textPrimary;
  final Color textSecondary;
  final Color textTertiary;
  final List<Color> backgroundGradient;

  const AuraPalette({
    required this.brightness,
    required this.background,
    required this.surface,
    required this.surfaceLight,
    required this.card,
    required this.border,
    required this.accentIris,
    required this.accentIrisGlow,
    required this.champagne,
    required this.champagneLight,
    required this.success,
    required this.error,
    required this.textPrimary,
    required this.textSecondary,
    required this.textTertiary,
    required this.backgroundGradient,
  });

  static const dark = AuraPalette(
    brightness: Brightness.dark,
    background: Color(0xFF0A0A0C),
    surface: Color(0xFF141418),
    surfaceLight: Color(0xFF1E1E26),
    card: Color(0xFF16161C),
    border: Color(0xFF282832),
    accentIris: Color(0xFF7C6EE6),
    accentIrisGlow: Color(0xFF9E92FF),
    champagne: Color(0xFFD4AF37),
    champagneLight: Color(0xFFF3E5AB),
    success: Color(0xFF34D399),
    error: Color(0xFFF87171),
    textPrimary: Color(0xFFF5F5F7),
    textSecondary: Color(0xFFA1A1AA),
    textTertiary: Color(0xFF71717A),
    backgroundGradient: [Color(0xFF0A0A0C), Color(0xFF0A0A0C)],
  );

  /// White with a light-green hue. Accent roles map to greens; text stays dark enough for WCAG AA on white.
  static const light = AuraPalette(
    brightness: Brightness.light,
    background: Color(0xFFF7FBF8),
    surface: Color(0xFFFFFFFF),
    surfaceLight: Color(0xFFEEF7F1),
    card: Color(0xFFFFFFFF),
    border: Color(0xFFD7E8DD),
    accentIris: Color(0xFF23855A),
    accentIrisGlow: Color(0xFF1F7A52),
    champagne: Color(0xFF3FA877),
    champagneLight: Color(0xFF1C6B48),
    success: Color(0xFF238A5B),
    error: Color(0xFFD14343),
    textPrimary: Color(0xFF13241C),
    textSecondary: Color(0xFF4A5D54),
    textTertiary: Color(0xFF5D7067),
    backgroundGradient: [Color(0xFFFFFFFF), Color(0xFFE6F6EC)],
  );
}

/// Colours for the active palette. Read at build time, so widgets pick up a theme switch on rebuild.
class AuraColors {
  static AuraPalette _active = AuraPalette.dark;

  static AuraPalette get palette => _active;
  static bool get isLight => _active.brightness == Brightness.light;
  static void use(AuraPalette palette) => _active = palette;

  static Color get background => _active.background;
  static Color get surface => _active.surface;
  static Color get surfaceLight => _active.surfaceLight;
  static Color get card => _active.card;
  static Color get border => _active.border;

  // Accents (iris/champagne in dark mode, greens in light mode)
  static Color get accentIris => _active.accentIris;
  static Color get accentIrisGlow => _active.accentIrisGlow;
  static Color get champagne => _active.champagne;
  static Color get champagneLight => _active.champagneLight;

  // Status & Feedback
  static Color get success => _active.success;
  static Color get error => _active.error;

  // Typography
  static Color get textPrimary => _active.textPrimary;
  static Color get textSecondary => _active.textSecondary;
  static Color get textTertiary => _active.textTertiary;

  /// Page background: flat in dark mode, white fading into light green in light mode.
  static BoxDecoration get pageBackground => BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: _active.backgroundGradient,
        ),
      );
}

/// Light / dark preference, persisted on the device. Defaults to the phone's system setting.
class AuraThemeController extends ValueNotifier<ThemeMode> {
  AuraThemeController._() : super(ThemeMode.system);
  static final AuraThemeController instance = AuraThemeController._();
  static const _prefsKey = 'aura_theme_mode';

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    value = ThemeMode.values.firstWhere(
      (m) => m.name == prefs.getString(_prefsKey),
      orElse: () => ThemeMode.system,
    );
  }

  Future<void> toggle(Brightness current) =>
      setMode(current == Brightness.dark ? ThemeMode.light : ThemeMode.dark);

  Future<void> setMode(ThemeMode mode) async {
    value = mode;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, mode.name);
  }

  /// Status bar / navigation bar icon colours that stay visible on the palette's background.
  static SystemUiOverlayStyle overlayFor(AuraPalette p) {
    final light = p.brightness == Brightness.light;
    return SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: light ? Brightness.dark : Brightness.light,
      statusBarBrightness: light ? Brightness.light : Brightness.dark, // iOS
      systemNavigationBarColor: p.surface,
      systemNavigationBarIconBrightness:
          light ? Brightness.dark : Brightness.light,
    );
  }

  AuraPalette paletteFor(Brightness platformBrightness) {
    final useLight = value == ThemeMode.light ||
        (value == ThemeMode.system && platformBrightness == Brightness.light);
    return useLight ? AuraPalette.light : AuraPalette.dark;
  }
}

class AuraTheme {
  static ThemeData get darkTheme => themeFor(AuraPalette.dark);

  static ThemeData themeFor(AuraPalette p) {
    final isDark = p.brightness == Brightness.dark;
    final scheme =
        (isDark ? const ColorScheme.dark() : const ColorScheme.light())
            .copyWith(
      primary: p.accentIris,
      secondary: p.champagne,
      surface: p.surface,
      error: p.error,
      onPrimary: Colors.white,
      onSecondary: isDark ? Colors.black : Colors.white,
      onSurface: p.textPrimary,
    );
    return ThemeData(
      brightness: p.brightness,
      scaffoldBackgroundColor: p.background,
      primaryColor: p.accentIris,
      cardColor: p.card,
      dividerColor: p.border,
      colorScheme: scheme,
      appBarTheme: AppBarTheme(
        foregroundColor: p.textPrimary,
        surfaceTintColor: Colors.transparent,
        systemOverlayStyle: AuraThemeController.overlayFor(p),
      ),
      dialogTheme: DialogThemeData(backgroundColor: p.surface),
      bottomSheetTheme: BottomSheetThemeData(
          backgroundColor: p.surface, surfaceTintColor: Colors.transparent),
      snackBarTheme: const SnackBarThemeData(
          contentTextStyle: TextStyle(color: Colors.white)),
      chipTheme: ChipThemeData(
          labelStyle: TextStyle(color: p.textPrimary),
          checkmarkColor: p.textPrimary),
      textTheme: TextTheme(
        displayLarge: GoogleFonts.outfit(
          fontSize: 32,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.8,
          color: p.textPrimary,
        ),
        displayMedium: GoogleFonts.outfit(
          fontSize: 26,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.5,
          color: p.textPrimary,
        ),
        titleLarge: GoogleFonts.outfit(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: p.textPrimary,
        ),
        titleMedium: GoogleFonts.plusJakartaSans(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: p.textPrimary,
        ),
        bodyLarge: GoogleFonts.plusJakartaSans(
          fontSize: 15,
          fontWeight: FontWeight.w400,
          color: p.textSecondary,
          height: 1.5,
        ),
        bodyMedium: GoogleFonts.plusJakartaSans(
          fontSize: 13,
          fontWeight: FontWeight.w400,
          color: p.textTertiary,
          height: 1.4,
        ),
        labelLarge: GoogleFonts.plusJakartaSans(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.3,
          color: p.textPrimary,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: p.accentIris,
          foregroundColor: Colors.white,
          elevation: 0,
          minimumSize: const Size.fromHeight(54),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          textStyle: GoogleFonts.plusJakartaSans(
            fontSize: 15,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: p.textPrimary,
          minimumSize: const Size.fromHeight(54),
          side: BorderSide(color: p.border, width: 1.2),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          textStyle: GoogleFonts.plusJakartaSans(
            fontSize: 15,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: p.surface,
        hintStyle: GoogleFonts.plusJakartaSans(
          color: p.textTertiary,
          fontSize: 14,
        ),
        labelStyle: GoogleFonts.plusJakartaSans(
          color: p.textSecondary,
          fontSize: 14,
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: p.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: p.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: p.accentIris, width: 1.5),
        ),
      ),
    );
  }
}
