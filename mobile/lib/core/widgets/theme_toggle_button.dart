import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Switches between the dark and the light (white + green) theme; the choice is remembered.
class ThemeToggleButton extends StatelessWidget {
  const ThemeToggleButton({super.key});

  @override
  Widget build(BuildContext context) {
    final isLight = AuraColors.isLight;
    return IconButton(
      tooltip: isLight ? 'Dark mode' : 'Light mode',
      icon: Icon(isLight ? Icons.dark_mode_outlined : Icons.light_mode_outlined,
          color: AuraColors.textSecondary),
      onPressed: () =>
          AuraThemeController.instance.toggle(Theme.of(context).brightness),
    );
  }
}
