import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../stylist/presentation/stylist_screen.dart' show describeApiError;
import '../data/auth_repository.dart';

Future<void> showChangePasswordDialog(BuildContext context) {
  return showDialog<void>(
      context: context, builder: (_) => const _ChangePasswordDialog());
}

class _ChangePasswordDialog extends StatefulWidget {
  const _ChangePasswordDialog();

  @override
  State<_ChangePasswordDialog> createState() => _ChangePasswordDialogState();
}

class _ChangePasswordDialogState extends State<_ChangePasswordDialog> {
  final _formKey = GlobalKey<FormState>();
  final _current = TextEditingController();
  final _next = TextEditingController();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await AuthRepository().changePassword(
          currentPassword: _current.text, newPassword: _next.text);
      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content:
                const Text('Password changed. Other devices were signed out.'),
            backgroundColor: AuraColors.success),
      );
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
      title: const Text('Change password'),
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextFormField(
              controller: _current,
              obscureText: true,
              style: fieldStyle,
              autofillHints: const [AutofillHints.password],
              decoration: const InputDecoration(labelText: 'Current password'),
              validator: (v) =>
                  (v?.isEmpty ?? true) ? 'Enter your current password' : null,
            ),
            const SizedBox(height: 10),
            TextFormField(
              controller: _next,
              obscureText: true,
              style: fieldStyle,
              autofillHints: const [AutofillHints.newPassword],
              decoration: const InputDecoration(
                  labelText: 'New password',
                  helperText: 'At least 8 characters'),
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
      actions: [
        TextButton(
            onPressed: _saving ? null : () => Navigator.of(context).pop(),
            child: const Text('Cancel')),
        TextButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Saving…' : 'Change')),
      ],
    );
  }
}
