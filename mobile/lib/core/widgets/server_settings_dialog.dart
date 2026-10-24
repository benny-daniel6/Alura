import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../constants/api_constants.dart';
import '../theme/app_theme.dart';

/// Lets the user point the app at a different Alura server (e.g. the PC's Wi-Fi address)
/// and checks it is reachable before saving.
Future<bool> showServerSettingsDialog(BuildContext context) async {
  final saved = await showDialog<bool>(
      context: context, builder: (_) => const _ServerSettingsDialog());
  return saved ?? false;
}

class _ServerSettingsDialog extends StatefulWidget {
  const _ServerSettingsDialog();

  @override
  State<_ServerSettingsDialog> createState() => _ServerSettingsDialogState();
}

class _ServerSettingsDialogState extends State<_ServerSettingsDialog> {
  late final TextEditingController _controller;
  bool _testing = false;
  String? _message;
  bool _ok = false;

  @override
  void initState() {
    super.initState();
    final uri = Uri.parse(ApiConstants.baseUrl);
    _controller = TextEditingController(text: '${uri.host}:${uri.port}');
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _testAndSave() async {
    final baseUrl = ApiConstants.normalizeServerInput(_controller.text);
    if (baseUrl == null) {
      setState(() {
        _ok = false;
        _message = 'Enter an address like 192.168.1.20:8000';
      });
      return;
    }
    setState(() {
      _testing = true;
      _message = null;
    });
    try {
      final origin = Uri.parse(baseUrl).origin;
      final dio = Dio(BaseOptions(
          connectTimeout: const Duration(seconds: 5),
          receiveTimeout: const Duration(seconds: 5)));
      final resp = await dio.get('$origin/health');
      if (resp.data is! Map || resp.data['service'] == null)
        throw Exception('Not an Alura server');
      await ApiConstants.saveServer(baseUrl);
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (_) {
      setState(() {
        _ok = false;
        _message =
            'Could not reach an Alura server at that address. Check the phone and PC are on the same '
            'Wi-Fi, the backend is running with --host 0.0.0.0, and the firewall allows port 8000.';
      });
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AuraColors.surface,
      title: const Text('Server'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Address of the computer running the Alura backend.',
            style: TextStyle(color: AuraColors.textSecondary, fontSize: 13),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _controller,
            keyboardType: TextInputType.url,
            autocorrect: false,
            style: TextStyle(color: AuraColors.textPrimary),
            decoration: const InputDecoration(
                labelText: 'Server address', hintText: '192.168.1.20:8000'),
            onSubmitted: (_) => _testAndSave(),
          ),
          if (_message != null) ...[
            const SizedBox(height: 10),
            Text(_message!,
                style: TextStyle(
                    fontSize: 12,
                    color: _ok ? AuraColors.success : AuraColors.error)),
          ],
        ],
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel')),
        TextButton(
          onPressed: _testing ? null : _testAndSave,
          child: Text(_testing ? 'Testing…' : 'Test & Save'),
        ),
      ],
    );
  }
}
