import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../stylist/presentation/stylist_screen.dart' show describeApiError;
import '../data/auth_repository.dart';

/// Turns a guest account into a full account (email + password). Returns the updated user, or null.
Future<UserModel?> showSaveAccountDialog(BuildContext context) {
  return showDialog<UserModel>(
      context: context, builder: (_) => const _SaveAccountDialog());
}

class _SaveAccountDialog extends StatefulWidget {
  const _SaveAccountDialog();

  @override
  State<_SaveAccountDialog> createState() => _SaveAccountDialogState();
}

class _SaveAccountDialogState extends State<_SaveAccountDialog> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final user = await AuthRepository().upgradeGuest(
        email: _email.text,
        password: _password.text,
        displayName: _name.text,
      );
      if (mounted) Navigator.of(context).pop(user);
    } catch (e) {
      if (mounted) setState(() => _error = describeApiError(e));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final fieldStyle = TextStyle(color: AuraColors.textPrimary);
    return AlertDialog(
      title: const Text('Save your account'),
      content: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Add an email and password to keep your wardrobe and outfits and sign in on any phone.',
                style: TextStyle(color: AuraColors.textSecondary, fontSize: 13),
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _name,
                style: fieldStyle,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'Name (optional)'),
              ),
              const SizedBox(height: 10),
              TextFormField(
                controller: _email,
                style: fieldStyle,
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                decoration: const InputDecoration(labelText: 'Email'),
                validator: (v) => RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
                        .hasMatch(v?.trim() ?? '')
                    ? null
                    : 'Enter a valid email',
              ),
              const SizedBox(height: 10),
              TextFormField(
                controller: _password,
                style: fieldStyle,
                obscureText: true,
                decoration: const InputDecoration(
                    labelText: 'Password', helperText: 'At least 8 characters'),
                validator: (v) =>
                    (v?.length ?? 0) >= 8 ? null : 'Use at least 8 characters',
              ),
              if (_error != null) ...[
                const SizedBox(height: 10),
                Text(_error!,
                    style: TextStyle(color: AuraColors.error, fontSize: 12)),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
            onPressed: _saving ? null : () => Navigator.of(context).pop(),
            child: const Text('Not now')),
        TextButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Saving…' : 'Save')),
      ],
    );
  }
}
