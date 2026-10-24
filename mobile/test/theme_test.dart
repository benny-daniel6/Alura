import 'package:aura_wardrobe/core/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('palette follows the system until the user picks a mode, then the choice sticks', () async {
    SharedPreferences.setMockInitialValues({});
    final c = AuraThemeController.instance;
    await c.load();
    expect(c.value, ThemeMode.system);
    expect(c.paletteFor(Brightness.light), AuraPalette.light);
    expect(c.paletteFor(Brightness.dark), AuraPalette.dark);

    await c.toggle(Brightness.dark);
    expect(c.value, ThemeMode.light);
    expect(c.paletteFor(Brightness.dark), AuraPalette.light);

    c.value = ThemeMode.system;
    await c.load(); // reloads the saved choice
    expect(c.value, ThemeMode.light);
  });

  test('AuraColors reads the active palette', () {
    AuraColors.use(AuraPalette.light);
    expect(AuraColors.isLight, isTrue);
    expect(AuraColors.surface, const Color(0xFFFFFFFF));
    expect(AuraTheme.themeFor(AuraPalette.light).brightness, Brightness.light);
    AuraColors.use(AuraPalette.dark);
    expect(AuraColors.isLight, isFalse);
  });
}
