import 'package:flutter/material.dart';

import '../constants/api_constants.dart';
import '../theme/app_theme.dart';
import 'server_settings_dialog.dart';

/// Keep in sync with `version:` in pubspec.yaml.
const String appVersion = '1.0.0';

/// Account & app settings: appearance, server, privacy, sign out.
Future<void> showSettingsSheet(
  BuildContext context, {
  required String email,
  String? displayName,
  required VoidCallback onServerChanged,
  required VoidCallback onDeleteData,
  required VoidCallback onSignOut,
  bool isGuest = false,
  VoidCallback? onSaveAccount,
  VoidCallback? onChangePassword,
  VoidCallback? onSignOutEverywhere,
}) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    // No fixed colour: the sheet takes it from the theme, so it repaints when the theme is switched from here
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    builder: (ctx) => _SettingsSheet(
      email: email,
      displayName: displayName,
      onServerChanged: onServerChanged,
      onDeleteData: onDeleteData,
      onSignOut: onSignOut,
      isGuest: isGuest,
      onSaveAccount: onSaveAccount,
      onChangePassword: onChangePassword,
      onSignOutEverywhere: onSignOutEverywhere,
    ),
  );
}

class _SettingsSheet extends StatelessWidget {
  final String email;
  final String? displayName;
  final VoidCallback onServerChanged;
  final VoidCallback onDeleteData;
  final VoidCallback onSignOut;
  final bool isGuest;
  final VoidCallback? onSaveAccount;
  final VoidCallback? onChangePassword;
  final VoidCallback? onSignOutEverywhere;

  const _SettingsSheet({
    required this.email,
    this.displayName,
    required this.onServerChanged,
    required this.onDeleteData,
    required this.onSignOut,
    this.isGuest = false,
    this.onSaveAccount,
    this.onChangePassword,
    this.onSignOutEverywhere,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final name = (displayName?.trim().isNotEmpty ?? false)
        ? displayName!.trim()
        : email.split('@').first;
    final server = Uri.parse(ApiConstants.baseUrl);

    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                    color: AuraColors.border,
                    borderRadius: BorderRadius.circular(2)),
              ),
            ),
            const SizedBox(height: 18),
            Row(
              children: [
                CircleAvatar(
                  radius: 24,
                  backgroundColor: AuraColors.accentIris.withOpacity(0.15),
                  child: Text(
                    name.isEmpty ? '?' : name[0].toUpperCase(),
                    style: theme.textTheme.titleLarge
                        ?.copyWith(color: AuraColors.accentIrisGlow),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(name, style: theme.textTheme.titleMedium),
                      Text(isGuest ? 'Guest account (not saved)' : email,
                          style: theme.textTheme.bodyMedium),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 22),
            _sectionLabel(theme, 'Appearance'),
            ValueListenableBuilder<ThemeMode>(
              valueListenable: AuraThemeController.instance,
              builder: (context, mode, _) => SegmentedButton<ThemeMode>(
                showSelectedIcon: false,
                style: SegmentedButton.styleFrom(
                  selectedBackgroundColor:
                      AuraColors.accentIris.withOpacity(0.18),
                  selectedForegroundColor: AuraColors.textPrimary,
                  foregroundColor: AuraColors.textSecondary,
                  side: BorderSide(color: AuraColors.border),
                ),
                segments: const [
                  ButtonSegment(
                      value: ThemeMode.system,
                      icon: Icon(Icons.brightness_auto_outlined),
                      label: Text('System')),
                  ButtonSegment(
                      value: ThemeMode.light,
                      icon: Icon(Icons.light_mode_outlined),
                      label: Text('Light')),
                  ButtonSegment(
                      value: ThemeMode.dark,
                      icon: Icon(Icons.dark_mode_outlined),
                      label: Text('Dark')),
                ],
                selected: {mode},
                onSelectionChanged: (s) =>
                    AuraThemeController.instance.setMode(s.first),
              ),
            ),
            const SizedBox(height: 18),
            _sectionLabel(theme, 'Account'),
            if (isGuest && onSaveAccount != null)
              _tile(
                theme,
                icon: Icons.verified_user_outlined,
                title: 'Save your account',
                subtitle: 'Add an email and password to keep your wardrobe',
                color: AuraColors.accentIris,
                onTap: () {
                  Navigator.of(context).pop();
                  onSaveAccount!();
                },
              ),
            if (serverSettingsAvailable)
              _tile(
                theme,
                icon: Icons.dns_outlined,
                title: 'Server',
                subtitle:
                    '${server.host}${server.hasPort ? ':${server.port}' : ''}',
                onTap: () async {
                  if (await showServerSettingsDialog(context)) {
                    onServerChanged();
                    if (context.mounted) Navigator.of(context).pop();
                  }
                },
              ),
            _tile(
              theme,
              icon: Icons.delete_forever_outlined,
              title: 'Delete my data',
              subtitle: 'Permanently erase your wardrobe, photos and outfits',
              color: AuraColors.error,
              onTap: () {
                Navigator.of(context).pop();
                onDeleteData();
              },
            ),
            if (!isGuest && onChangePassword != null)
              _tile(
                theme,
                icon: Icons.password_outlined,
                title: 'Change password',
                subtitle: 'Signs you out on your other devices',
                onTap: () {
                  Navigator.of(context).pop();
                  onChangePassword!();
                },
              ),
            if (!isGuest && onSignOutEverywhere != null)
              _tile(
                theme,
                icon: Icons.devices_other_outlined,
                title: 'Sign out on all devices',
                onTap: () {
                  Navigator.of(context).pop();
                  onSignOutEverywhere!();
                },
              ),
            _tile(
              theme,
              icon: Icons.logout,
              title: 'Sign out',
              onTap: () {
                Navigator.of(context).pop();
                onSignOut();
              },
            ),
            const SizedBox(height: 12),
            Center(
                child: Text('Alura $appVersion',
                    style: theme.textTheme.bodyMedium?.copyWith(fontSize: 11))),
          ],
        ),
      ),
    );
  }

  Widget _sectionLabel(ThemeData theme, String text) => Padding(
        padding: const EdgeInsets.only(bottom: 8, left: 2),
        child: Text(text.toUpperCase(),
            style: theme.textTheme.labelMedium
                ?.copyWith(color: AuraColors.textTertiary, letterSpacing: 1.2)),
      );

  Widget _tile(
    ThemeData theme, {
    required IconData icon,
    required String title,
    String? subtitle,
    Color? color,
    required VoidCallback onTap,
  }) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 4),
      leading: Icon(icon, color: color ?? AuraColors.textSecondary),
      title: Text(title,
          style: theme.textTheme.titleMedium
              ?.copyWith(fontSize: 15, color: color)),
      subtitle: subtitle == null
          ? null
          : Text(subtitle, style: theme.textTheme.bodyMedium),
      onTap: onTap,
    );
  }
}
