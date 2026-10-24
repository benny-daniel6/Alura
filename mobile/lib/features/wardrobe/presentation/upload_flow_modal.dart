import '../../../core/utils/labels.dart';
import 'dart:async';
import 'dart:typed_data';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import '../../../core/theme/app_theme.dart';
import '../data/wardrobe_repository.dart';
import 'garment_image.dart';

class UploadFlowModal extends StatefulWidget {
  final VoidCallback onCompleted;
  const UploadFlowModal({super.key, required this.onCompleted});

  @override
  State<UploadFlowModal> createState() => _UploadFlowModalState();
}

class _UploadFlowModalState extends State<UploadFlowModal> {
  final WardrobeRepository _repo = WardrobeRepository();
  bool _isProcessing = false;
  int _currentStep = 0; // 0: upload, 1: rembg, 2: clip, 3: completed
  String? _errorMessage;
  WardrobeItemModel? _completedItem;
  Timer? _pollingTimer;

  final ImagePicker _picker = ImagePicker();
  Uint8List? _pickedBytes;
  String _pickedName = 'garment.jpg';
  String? _selectedCategory;

  static const _categories = [
    'top',
    'bottom',
    'outerwear',
    'dress',
    'footwear',
    'bag',
    'accessory',
    'headwear',
    'one_piece',
  ];

  Future<void> _pickImage(ImageSource source) async {
    try {
      // Full-resolution bytes; ClientImageCompressor does the resize/EXIF/JPEG step before upload.
      final file =
          await _picker.pickImage(source: source, requestFullMetadata: true);
      if (file == null) return;
      final bytes = await file.readAsBytes();
      setState(() {
        _pickedBytes = bytes;
        _pickedName = file.name;
        _errorMessage = null;
      });
    } catch (e) {
      setState(() => _errorMessage = 'Could not access photo: $e');
    }
  }

  @override
  void dispose() {
    _pollingTimer?.cancel();
    super.dispose();
  }

  Future<void> _startUploadAndPoll() async {
    final bytes = _pickedBytes;
    if (bytes == null) return;
    setState(() {
      _isProcessing = true;
      _currentStep = 0;
      _errorMessage = null;
    });

    try {
      // 1. Resize to max 1024px + JPEG q85 on a background isolate, then upload
      final uploadResult = await _repo.uploadGarment(
        bytes: bytes,
        filename: _pickedName,
        initialCategory: _selectedCategory,
      );

      if (!mounted) return;
      setState(() => _currentStep = 1);

      // 2. Poll status endpoint every 1.5 seconds
      int pollAttempts = 0;
      _pollingTimer =
          Timer.periodic(const Duration(milliseconds: 1500), (timer) async {
        pollAttempts++;
        try {
          final statusResult = await _repo.pollStatus(uploadResult.itemId);
          if (!mounted) {
            timer.cancel();
            return;
          }

          if (statusResult.status == 'processing') {
            setState(() => _currentStep = 2);
          } else if (statusResult.status == 'completed') {
            timer.cancel();
            setState(() {
              _currentStep = 3;
              HapticFeedback.mediumImpact();
              _completedItem = statusResult.item;
              _isProcessing = false;
            });
            widget.onCompleted();
          } else if (statusResult.status == 'failed') {
            timer.cancel();
            setState(() {
              _errorMessage =
                  statusResult.errorMessage ?? 'ML processing failed.';
              _isProcessing = false;
            });
          }

          if (pollAttempts > 160) {
            // 4 min: studio photo + high-quality cutout on a CPU worker
            timer.cancel();
            setState(() {
              _errorMessage =
                  'Processing timed out. Please check your network.';
              _isProcessing = false;
            });
          }
        } catch (e) {
          // Keep polling on transient network hiccup
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = _describeError(e);
        _isProcessing = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
      decoration: BoxDecoration(
        color: AuraColors.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      // Preview + chips + error banner can exceed the screen height on phones
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Drag handle
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: AuraColors.border,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 20),

            Text(
              'Digitise Garment',
              style: theme.textTheme.displayMedium?.copyWith(fontSize: 22),
            ),
            const SizedBox(height: 6),
            Text(
              'Snap any garment, even on a bed or a hanger. Alura turns it into a clean studio photo, cuts it out for your outfit canvas and tags it automatically.',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 24),

            if (_errorMessage != null) ...[
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: AuraColors.error.withOpacity(0.12),
                  border: Border.all(color: AuraColors.error.withOpacity(0.4)),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  _errorMessage!,
                  style: theme.textTheme.bodyMedium
                      ?.copyWith(color: AuraColors.error),
                ),
              ),
              const SizedBox(height: 16),
            ],

            if (_isProcessing || _currentStep == 3) ...[
              // Live Status Stepper
              _buildPipelineStep(
                theme,
                stepIndex: 0,
                label: 'Resized to 1024px, JPEG q85 & uploaded',
                isDone: _currentStep > 0,
                isActive: _currentStep == 0,
              ),
              _buildPipelineStep(
                theme,
                stepIndex: 1,
                label: 'Creating studio photo & cutout…',
                isDone: _currentStep > 1,
                isActive: _currentStep == 1,
              ),
              _buildPipelineStep(
                theme,
                stepIndex: 2,
                label: 'Tagging colours, category & occasions…',
                isDone: _currentStep > 2,
                isActive: _currentStep == 2,
              ),
              _buildPipelineStep(
                theme,
                stepIndex: 3,
                label: 'Garment successfully added to your digital wardrobe!',
                isDone: _currentStep == 3,
                isActive: false,
              ),
              const SizedBox(height: 24),

              if (_currentStep == 3 && _completedItem != null) ...[
                // The transparent cutout produced by the worker
                Container(
                  height: 200,
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: _completedItem!.showcaseImageUrl != null
                        ? Colors.white
                        : AuraColors.surfaceLight,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: GarmentImage(
                      garment: _completedItem!,
                      variant: GarmentImageVariant.showcase),
                ),
                if (_completedItem!.name != null) ...[
                  const SizedBox(height: 8),
                  Text(_completedItem!.name!,
                      textAlign: TextAlign.center,
                      style: theme.textTheme.titleMedium),
                ],
                const SizedBox(height: 16),
              ],
              if (_currentStep == 3)
                ElevatedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('View in Closet'),
                ),
            ] else if (_pickedBytes == null) ...[
              // Source selection
              Row(
                children: [
                  Expanded(
                    child: _buildSourceButton(
                      theme,
                      icon: Icons.photo_camera_outlined,
                      label: 'Camera',
                      onTap: () => _pickImage(ImageSource.camera),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _buildSourceButton(
                      theme,
                      icon: Icons.photo_library_outlined,
                      label: 'Gallery',
                      onTap: () => _pickImage(ImageSource.gallery),
                    ),
                  ),
                ],
              ),
            ] else ...[
              // Preview + optional category hint, then upload
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: Container(
                  color: AuraColors.surfaceLight,
                  height: 220,
                  child: Image.memory(_pickedBytes!, fit: BoxFit.contain),
                ),
              ),
              const SizedBox(height: 14),
              Text('Category (optional — AI will tag it)',
                  style: theme.textTheme.bodyMedium),
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: _categories.map((c) {
                  return ChoiceChip(
                    label:
                        Text(tagLabel(c), style: const TextStyle(fontSize: 12)),
                    selected: _selectedCategory == c,
                    onSelected: (sel) =>
                        setState(() => _selectedCategory = sel ? c : null),
                    selectedColor: AuraColors.accentIris.withOpacity(0.3),
                    backgroundColor: AuraColors.surfaceLight,
                  );
                }).toList(),
              ),
              const SizedBox(height: 18),
              Row(
                children: [
                  TextButton(
                    onPressed: () => setState(() => _pickedBytes = null),
                    child: const Text('Choose another'),
                  ),
                  const Spacer(),
                  ElevatedButton.icon(
                    // Theme buttons are full-width (Size.fromHeight); a Row gives unbounded width
                    style: ElevatedButton.styleFrom(
                        minimumSize: const Size(0, 54)),
                    onPressed: _startUploadAndPoll,
                    icon: const Icon(Icons.cloud_upload_outlined),
                    label: const Text('Digitise'),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  static String _describeError(Object e) {
    if (e is DioException) {
      if (e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout) {
        return 'Cannot reach the Alura server. Check your connection, or the server address (server icon at the top).';
      }
      final detail =
          e.response?.data is Map ? (e.response!.data as Map)['detail'] : null;
      if (detail is String) return detail;
    }
    return e.toString().replaceAll('Exception: ', '');
  }

  Widget _buildSourceButton(
    ThemeData theme, {
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 22),
        decoration: BoxDecoration(
          color: AuraColors.surfaceLight,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AuraColors.border),
        ),
        child: Column(
          children: [
            Icon(icon, color: AuraColors.accentIris, size: 30),
            const SizedBox(height: 8),
            Text(label,
                style: theme.textTheme.titleMedium?.copyWith(fontSize: 15)),
          ],
        ),
      ),
    );
  }

  Widget _buildPipelineStep(
    ThemeData theme, {
    required int stepIndex,
    required String label,
    required bool isDone,
    required bool isActive,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          if (isDone)
            Icon(Icons.check_circle, color: AuraColors.success, size: 22)
          else if (isActive)
            SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(
                  strokeWidth: 2, color: AuraColors.accentIris),
            )
          else
            Icon(Icons.radio_button_unchecked,
                color: AuraColors.textTertiary, size: 22),
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              label,
              style: theme.textTheme.bodyLarge?.copyWith(
                color: isDone || isActive
                    ? AuraColors.textPrimary
                    : AuraColors.textTertiary,
                fontWeight: isActive ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
