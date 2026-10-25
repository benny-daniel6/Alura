import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/settings_sheet.dart';
import '../../auth/data/auth_repository.dart';
import '../../auth/presentation/auth_screen.dart';
import '../../auth/presentation/change_password_dialog.dart';
import '../../auth/presentation/save_account_dialog.dart';
import '../../wardrobe/presentation/wardrobe_screen.dart';
import '../../outfits/presentation/outfits_list_screen.dart';
import '../../stylist/presentation/stylist_screen.dart';

class HomeShellScreen extends StatefulWidget {
  final UserModel user;
  const HomeShellScreen({super.key, required this.user});

  @override
  State<HomeShellScreen> createState() => _HomeShellScreenState();
}

class _HomeShellScreenState extends State<HomeShellScreen> {
  int _selectedTabIndex = 0;
  int _wardrobeGeneration = 0;
  int _outfitsGeneration = 0;
  final AuthRepository _authRepo = AuthRepository();
  late UserModel _user = widget.user;

  Future<void> _saveGuestAccount() async {
    final upgraded = await showSaveAccountDialog(context);
    if (upgraded == null || !mounted) return;
    setState(() => _user = upgraded);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: const Text('Account saved'),
          backgroundColor: AuraColors.success),
    );
  }

  Future<void> _handleDeleteData() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AuraColors.surface,
        title: const Text('Delete all your data?'),
        content: Text(
          'This permanently erases your garments and their photos, your outfits, style preferences and account from Alura. It cannot be undone.',
          style: TextStyle(color: AuraColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
                backgroundColor: AuraColors.error,
                minimumSize: const Size(0, 48)),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete everything'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      final success = await _authRepo.deleteMyData();
      if (!mounted) return;
      if (success) {
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const AuthScreen()),
          (route) => false,
        );
      }
    }
  }

  String get _initial {
    final source = (_user.displayName?.trim().isNotEmpty ?? false)
        ? _user.displayName!
        : _user.email;
    return source.isEmpty ? '?' : source.trim()[0].toUpperCase();
  }

  Future<void> _handleSignOutEverywhere() async {
    try {
      await _authRepo.signOutEverywhere();
    } catch (_) {
      await _authRepo.signOut(); // signed out here regardless
    }
    if (!mounted) return;
    Navigator.of(context)
        .pushReplacement(MaterialPageRoute(builder: (_) => const AuthScreen()));
  }

  Future<void> _handleSignOut() async {
    await _authRepo.signOut();
    if (!mounted) return;
    Navigator.of(context)
        .pushReplacement(MaterialPageRoute(builder: (_) => const AuthScreen()));
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
          title: Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: AuraColors.accentIris.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  'ALURA',
                  style: theme.textTheme.titleMedium?.copyWith(
                    letterSpacing: 2.0,
                    color: AuraColors.accentIrisGlow,
                  ),
                ),
              ),
            ],
          ),
          actions: [
            IconButton(
              tooltip: 'Profile & settings',
              icon: CircleAvatar(
                radius: 16,
                backgroundColor: AuraColors.accentIris.withOpacity(0.15),
                child: Text(
                  _initial,
                  style: theme.textTheme.titleMedium?.copyWith(
                      fontSize: 14, color: AuraColors.accentIrisGlow),
                ),
              ),
              onPressed: () => showSettingsSheet(
                context,
                email: _user.email,
                displayName: _user.displayName,
                onServerChanged: () => setState(() {
                  _wardrobeGeneration++;
                  _outfitsGeneration++;
                }),
                onDeleteData: _handleDeleteData,
                onSignOut: _handleSignOut,
                isGuest: _user.isGuest,
                onSaveAccount: _saveGuestAccount,
                onChangePassword: () => showChangePasswordDialog(context),
                onSignOutEverywhere: _handleSignOutEverywhere,
              ),
            ),
            const SizedBox(width: 8),
          ],
        ),
        // The stylist keeps its results across tab switches; the lists reload each time they are opened
        body: Column(
          children: [
            if (_user.isGuest)
              Material(
                color: AuraColors.accentIris.withOpacity(0.12),
                child: InkWell(
                  onTap: _saveGuestAccount,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 20, vertical: 10),
                    child: Row(
                      children: [
                        Icon(Icons.info_outline,
                            size: 18, color: AuraColors.accentIrisGlow),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            "You're using a guest account. Save it to keep your wardrobe.",
                            style: theme.textTheme.bodyMedium?.copyWith(
                                color: AuraColors.textPrimary, fontSize: 12),
                          ),
                        ),
                        Text('Save',
                            style: theme.textTheme.labelLarge
                                ?.copyWith(color: AuraColors.accentIrisGlow)),
                      ],
                    ),
                  ),
                ),
              ),
            Expanded(
                child: IndexedStack(
              index: _selectedTabIndex,
              children: [
                WardrobeScreen(key: ValueKey('wardrobe-$_wardrobeGeneration')),
                OutfitsListScreen(key: ValueKey('outfits-$_outfitsGeneration')),
                const StylistScreen(),
              ],
            )),
          ],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _selectedTabIndex,
          onDestinationSelected: (idx) => setState(() {
            if (idx == 0 && _selectedTabIndex != 0) _wardrobeGeneration++;
            if (idx == 1 && _selectedTabIndex != 1) _outfitsGeneration++;
            _selectedTabIndex = idx;
          }),
          backgroundColor: AuraColors.surface,
          indicatorColor: AuraColors.accentIris.withOpacity(0.2),
          destinations: [
            NavigationDestination(
              icon: Icon(Icons.checkroom_outlined),
              selectedIcon: Icon(Icons.checkroom, color: AuraColors.accentIris),
              label: 'Wardrobe',
            ),
            NavigationDestination(
              icon: Icon(Icons.dashboard_customize_outlined),
              selectedIcon:
                  Icon(Icons.dashboard_customize, color: AuraColors.accentIris),
              label: 'Outfits',
            ),
            NavigationDestination(
              icon: Icon(Icons.auto_awesome_outlined),
              selectedIcon:
                  Icon(Icons.auto_awesome, color: AuraColors.accentIris),
              label: 'Stylist',
            ),
          ],
        ),
      ),
    );
  }
}
