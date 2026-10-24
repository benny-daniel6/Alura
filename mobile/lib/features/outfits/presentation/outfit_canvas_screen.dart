import '../../../core/utils/labels.dart';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../../../core/theme/app_theme.dart';
import '../../stylist/data/stylist_repository.dart';
import '../../stylist/presentation/stylist_screen.dart'
    show describeApiError, stylistOccasions;
import '../../wardrobe/data/wardrobe_repository.dart';
import '../../wardrobe/presentation/garment_image.dart';
import '../data/outfit_repository.dart';
import '../domain/outfit_canvas_controller.dart';

const _occasionOptions = [
  {'id': 'office_work', 'label': 'Office / Work'},
  {'id': 'casual_daily', 'label': 'Casual Daily'},
  {'id': 'evening_dinner', 'label': 'Evening Dinner'},
  {'id': 'nightlife', 'label': 'Nightlife'},
  {'id': 'formal_events', 'label': 'Formal Event'},
  {'id': 'athleisure', 'label': 'Athleisure'},
];

const _seasons = ['all_season', 'spring', 'summer', 'fall', 'winter'];

/// Snapshots are capped so the PNG stays well inside the backend's 4096px / 5MB preview limits.
const double _maxSnapshotPixels = 2048;

class OutfitCanvasScreen extends StatefulWidget {
  final VoidCallback onSaved;

  /// When set, the canvas opens this outfit for editing and saving updates it in place.
  final OutfitModel? existing;

  /// Garments to start with, auto-arranged as a flat lay (e.g. an AI stylist suggestion).
  final List<WardrobeItemModel>? initialGarments;

  /// Default title in the save dialog for a new outfit.
  final String? initialName;

  const OutfitCanvasScreen({
    super.key,
    required this.onSaved,
    this.existing,
    this.initialGarments,
    this.initialName,
  });

  @override
  State<OutfitCanvasScreen> createState() => _OutfitCanvasScreenState();
}

class _OutfitCanvasScreenState extends State<OutfitCanvasScreen> {
  final OutfitRepository _outfitRepo = OutfitRepository();
  final WardrobeRepository _wardrobeRepo = WardrobeRepository();
  final StylistRepository _stylistRepo = StylistRepository();
  final OutfitCanvasController _canvas = OutfitCanvasController();
  final GlobalKey _snapshotKey = GlobalKey();

  Size _canvasSize = Size.zero;
  bool _loadedExisting = false;
  bool _isSaving = false;
  bool _aiBusy = false;
  bool _capturing =
      false; // hides selection chrome while rendering the snapshot

  @override
  void dispose() {
    _canvas.dispose();
    super.dispose();
  }

  void _onCanvasSized(Size size) {
    if (size == _canvasSize) return;
    _canvasSize = size;
    if (_loadedExisting || size == Size.zero) return;
    if (widget.existing != null) {
      _loadedExisting = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _canvas.loadOutfit(widget.existing!, size);
      });
    } else if (widget.initialGarments != null &&
        widget.initialGarments!.isNotEmpty) {
      _loadedExisting = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _canvas.arrange(widget.initialGarments!, size);
      });
    }
  }

  // ---------- Gestures ----------

  void _onTapUp(TapUpDetails details) {
    _canvas.select(_canvas.hitTest(details.localPosition));
  }

  void _onScaleStart(ScaleStartDetails details) {
    final hit = _canvas.hitTest(details.localFocalPoint);
    if (hit != null) {
      _canvas.select(hit);
    } else if (details.pointerCount < 2) {
      // One finger on empty canvas: nothing to drag. Two fingers anywhere keep editing the selection.
      _canvas.select(null);
    }
    _canvas.beginTransform();
  }

  void _onScaleUpdate(ScaleUpdateDetails details) {
    _canvas.updateTransform(
      focalDelta: details.focalPointDelta,
      scale: details.scale,
      rotation: details.rotation,
    );
  }

  // ---------- Add garments ----------

  Future<void> _openAddGarmentSheet() async {
    List<WardrobeItemModel> garments;
    try {
      garments = (await _wardrobeRepo.getItems())
          .where((g) => g.status == 'completed')
          .toList();
    } catch (e) {
      _showSnack('Could not load your wardrobe: $e', error: true);
      return;
    }
    if (!mounted) return;

    showModalBottomSheet(
      context: context,
      backgroundColor: AuraColors.surface,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) {
        return SizedBox(
          height: MediaQuery.of(ctx).size.height * 0.6,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Add Garment to Moodboard',
                    style: Theme.of(ctx).textTheme.titleLarge),
                const SizedBox(height: 14),
                Expanded(
                  child: garments.isEmpty
                      ? Center(
                          child: Text(
                              'No processed garments yet. Digitise garments first.',
                              style:
                                  TextStyle(color: AuraColors.textSecondary)),
                        )
                      : GridView.builder(
                          gridDelegate:
                              const SliverGridDelegateWithFixedCrossAxisCount(
                            crossAxisCount: 3,
                            childAspectRatio: 0.8,
                            crossAxisSpacing: 10,
                            mainAxisSpacing: 10,
                          ),
                          itemCount: garments.length,
                          itemBuilder: (c, idx) {
                            final g = garments[idx];
                            final placed = _canvas.contains(g.id);
                            return Opacity(
                              opacity: placed ? 0.35 : 1,
                              child: InkWell(
                                onTap: placed
                                    ? null
                                    : () {
                                        _canvas.add(g, _canvasSize);
                                        Navigator.of(ctx).pop();
                                      },
                                borderRadius: BorderRadius.circular(12),
                                child: Container(
                                  padding: const EdgeInsets.all(8),
                                  decoration: BoxDecoration(
                                    color: AuraColors.surfaceLight,
                                    borderRadius: BorderRadius.circular(12),
                                    border:
                                        Border.all(color: AuraColors.border),
                                  ),
                                  child: Column(
                                    children: [
                                      Expanded(
                                          child: GarmentImage(
                                              garment: g,
                                              preferThumbnail: true)),
                                      const SizedBox(height: 6),
                                      Text(
                                        placed
                                            ? 'On canvas'
                                            : (g.name ?? tagLabel(g.category)),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: TextStyle(
                                            fontSize: 11,
                                            color: AuraColors.textPrimary),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  // ---------- AI: complete this look ----------

  Future<void> _aiComplete(String occasion) async {
    if (_canvas.isEmpty) {
      _showSnack(
          'Add a piece first, then let AI build the rest of the look around it.',
          error: true);
      return;
    }
    setState(() => _aiBusy = true);
    try {
      final anchors =
          _canvas.paintOrder.map((e) => e.garment.id).take(6).toList();
      final result = await _stylistRepo.suggest(
        occasion: occasion,
        city: await _stylistRepo.getSavedCity(),
        anchorItemIds: anchors,
        numOutfits: 1,
      );
      if (!mounted) return;
      if (result.outfits.isEmpty) {
        _showSnack('No matching pieces found in your closet.', error: true);
        return;
      }
      final look = result.outfits.first;
      final added = _canvas.addArranged(look.items, _canvasSize);
      final missing = look.missingPieces.isNotEmpty
          ? ' Consider adding: ${look.missingPieces.first}.'
          : '';
      _showSnack(
        added > 0
            ? 'Added ${added == 1 ? '1 piece' : '$added pieces'}. ${look.rationale}$missing'
            : 'Nothing in your closet improves this look.$missing',
        error: added == 0 && missing.isNotEmpty,
      );
    } catch (e) {
      _showSnack(describeApiError(e), error: true);
    } finally {
      if (mounted) setState(() => _aiBusy = false);
    }
  }

  // ---------- Save ----------

  void _showSaveDialog() {
    if (_canvas.isEmpty) {
      _showSnack('Add at least one garment to save this outfit.', error: true);
      return;
    }

    final existing = widget.existing;
    final nameController = TextEditingController(
      text: existing?.name ?? widget.initialName ?? 'Editorial Capsule Look',
    );
    final descController =
        TextEditingController(text: existing?.description ?? '');
    final selectedOccasions = <String>[
      ...(existing?.occasions ?? const ['casual_daily'])
    ];
    String selectedSeason = existing?.season ?? 'all_season';

    showDialog(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            return AlertDialog(
              backgroundColor: AuraColors.surface,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20)),
              title: Text(
                  existing == null ? 'Save Outfit Look' : 'Update Outfit Look'),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TextField(
                      controller: nameController,
                      maxLength: 150,
                      style: TextStyle(color: AuraColors.textPrimary),
                      decoration:
                          const InputDecoration(labelText: 'Outfit Title'),
                    ),
                    const SizedBox(height: 4),
                    TextField(
                      controller: descController,
                      maxLength: 500,
                      style: TextStyle(color: AuraColors.textPrimary),
                      decoration: const InputDecoration(
                          labelText: 'Styling Notes (Optional)'),
                    ),
                    const SizedBox(height: 12),
                    Text('Occasions',
                        style: TextStyle(
                            fontWeight: FontWeight.w600,
                            color: AuraColors.textSecondary)),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: _occasionOptions.map((occ) {
                        return FilterChip(
                          label: Text(occ['label']!,
                              style: const TextStyle(fontSize: 12)),
                          selected: selectedOccasions.contains(occ['id']),
                          onSelected: (val) => setDialogState(() {
                            val
                                ? selectedOccasions.add(occ['id']!)
                                : selectedOccasions.remove(occ['id']);
                          }),
                          selectedColor: AuraColors.accentIris.withOpacity(0.3),
                          backgroundColor: AuraColors.surfaceLight,
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 16),
                    Text('Season',
                        style: TextStyle(
                            fontWeight: FontWeight.w600,
                            color: AuraColors.textSecondary)),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String>(
                      value: _seasons.contains(selectedSeason)
                          ? selectedSeason
                          : 'all_season',
                      dropdownColor: AuraColors.surfaceLight,
                      style: TextStyle(color: AuraColors.textPrimary),
                      items: _seasons
                          .map((s) => DropdownMenuItem(
                              value: s, child: Text(s.toUpperCase())))
                          .toList(),
                      onChanged: (val) {
                        if (val != null)
                          setDialogState(() => selectedSeason = val);
                      },
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                    onPressed: () => Navigator.of(ctx).pop(),
                    child: const Text('Cancel')),
                ElevatedButton(
                  // Dialog actions get unbounded width; the theme's Size.fromHeight would be infinite
                  style:
                      ElevatedButton.styleFrom(minimumSize: const Size(0, 48)),
                  onPressed: () {
                    Navigator.of(ctx).pop();
                    _executeSave(
                      name: nameController.text.trim(),
                      description: descController.text.trim(),
                      occasions: selectedOccasions,
                      season: selectedSeason,
                    );
                  },
                  child:
                      Text(existing == null ? 'Save Outfit' : 'Update Outfit'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  /// Renders the canvas (without selection chrome) to PNG via its RepaintBoundary.
  Future<Uint8List?> _captureSnapshot() async {
    final devicePixelRatio = MediaQuery.of(context).devicePixelRatio;
    setState(() => _capturing = true);
    try {
      await WidgetsBinding.instance.endOfFrame;
      final boundary = _snapshotKey.currentContext?.findRenderObject()
          as RenderRepaintBoundary?;
      if (boundary == null || _canvasSize.isEmpty) return null;
      final pixelRatio = math.min(
          devicePixelRatio, _maxSnapshotPixels / _canvasSize.longestSide);
      final image = await boundary.toImage(pixelRatio: pixelRatio);
      try {
        final data = await image.toByteData(format: ui.ImageByteFormat.png);
        return data?.buffer.asUint8List();
      } finally {
        image.dispose();
      }
    } finally {
      if (mounted) setState(() => _capturing = false);
    }
  }

  Future<void> _executeSave({
    required String name,
    required String description,
    required List<String> occasions,
    required String season,
  }) async {
    setState(() => _isSaving = true);
    try {
      final snapshot = await _captureSnapshot();
      final canvasState = _canvas.toCanvasState(_canvasSize);
      final title = name.isEmpty ? 'Untitled Outfit' : name;

      final OutfitModel saved;
      if (widget.existing == null) {
        saved = await _outfitRepo.createOutfit(
          name: title,
          description: description.isEmpty ? null : description,
          occasions: occasions,
          season: season,
          canvasState: canvasState,
        );
      } else {
        saved = await _outfitRepo.updateOutfit(widget.existing!.id, {
          'name': title,
          'description': description.isEmpty ? null : description,
          'occasions': occasions,
          'season': season,
          'canvas_state': canvasState.toJson(),
        });
      }

      String? previewWarning;
      if (snapshot != null) {
        try {
          await _outfitRepo.uploadPreview(saved.id, snapshot);
        } catch (e) {
          previewWarning =
              'Outfit saved, but the preview image failed to upload.';
        }
      }

      widget.onSaved();
      if (!mounted) return;
      _showSnack(previewWarning ?? 'Outfit saved to Lookbook!',
          error: previewWarning != null);
      Navigator.of(context).pop(saved);
    } catch (e) {
      _showSnack('Failed to save outfit: $e', error: true);
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  void _showSnack(String message, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text(message),
          backgroundColor: error ? AuraColors.error : AuraColors.success),
    );
  }

  // ---------- Build ----------

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text(widget.existing == null ? 'Studio Canvas' : 'Edit Look',
            style: theme.textTheme.titleLarge),
        actions: [
          _aiBusy
              ? const Padding(
                  padding: EdgeInsets.all(14),
                  child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2)),
                )
              : PopupMenuButton<String>(
                  tooltip: 'AI: complete this look',
                  icon: Icon(Icons.auto_awesome,
                      color: AuraColors.accentIrisGlow),
                  color: AuraColors.surfaceLight,
                  enabled: !_isSaving,
                  onSelected: _aiComplete,
                  itemBuilder: (_) => [
                    const PopupMenuItem<String>(
                      enabled: false,
                      child: Text('Complete this look for…',
                          style: TextStyle(fontSize: 12)),
                    ),
                    ...stylistOccasions.map((o) => PopupMenuItem<String>(
                        value: o['id'], child: Text(o['label']!))),
                  ],
                ),
          IconButton(
            tooltip: 'Clear Canvas',
            icon: Icon(Icons.refresh, color: AuraColors.textSecondary),
            onPressed: _isSaving ? null : _canvas.clear,
          ),
          IconButton(
            tooltip: 'Save Outfit',
            icon: Icon(Icons.check, color: AuraColors.champagne),
            onPressed: _isSaving ? null : _showSaveDialog,
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            ListenableBuilder(
              listenable: _canvas,
              builder: (context, _) => _buildSelectionToolbar(),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(18),
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      _onCanvasSized(constraints.biggest);
                      return GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTapUp: _onTapUp,
                        onScaleStart: _onScaleStart,
                        onScaleUpdate: _onScaleUpdate,
                        child: RepaintBoundary(
                          key: _snapshotKey,
                          child: ListenableBuilder(
                            listenable: _canvas,
                            builder: (context, _) => _buildCanvas(theme),
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
            ),
            _buildBottomBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildCanvas(ThemeData theme) {
    return Stack(
      clipBehavior: Clip.hardEdge,
      children: [
        Positioned.fill(child: ColoredBox(color: AuraColors.surface)),
        for (final item in _canvas.paintOrder)
          Positioned(
            left: item.x,
            top: item.y,
            width: OutfitCanvasController.itemSize.width,
            height: OutfitCanvasController.itemSize.height,
            child: IgnorePointer(
              child: Transform.rotate(
                angle: item.rotation,
                child: Transform.scale(
                  scale: item.scale,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      border: (!_capturing && _canvas.selected == item)
                          ? Border.all(
                              color: AuraColors.champagne,
                              width: 1.5 / item.scale)
                          : null,
                    ),
                    child: GarmentImage(garment: item.garment),
                  ),
                ),
              ),
            ),
          ),
        if (_canvas.isEmpty && !_capturing)
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.touch_app_outlined,
                    size: 48, color: AuraColors.textTertiary),
                const SizedBox(height: 12),
                Text('Moodboard Canvas', style: theme.textTheme.titleMedium),
                const SizedBox(height: 6),
                Text(
                    'Add cutouts from your closet, then drag,\npinch and twist to style them.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyMedium),
              ],
            ),
          ),
      ],
    );
  }

  Widget _buildSelectionToolbar() {
    final hasSelection = _canvas.selected != null;
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 150),
      opacity: hasSelection ? 1 : 0.4,
      child: Container(
        margin: const EdgeInsets.fromLTRB(12, 4, 12, 10),
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: AuraColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AuraColors.border),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            _toolButton(Icons.vertical_align_top, 'Bring to Front',
                hasSelection ? _canvas.bringToFront : null),
            _toolButton(Icons.flip_to_front, 'Bring Forward',
                hasSelection ? _canvas.bringForward : null),
            _toolButton(Icons.flip_to_back, 'Send Backward',
                hasSelection ? _canvas.sendBackward : null),
            _toolButton(Icons.vertical_align_bottom, 'Send to Back',
                hasSelection ? _canvas.sendToBack : null),
            _toolButton(Icons.restart_alt, 'Reset Size & Rotation',
                hasSelection ? _canvas.resetTransformOfSelected : null),
            _toolButton(Icons.delete_outline, 'Remove',
                hasSelection ? _canvas.removeSelected : null,
                color: AuraColors.error),
          ],
        ),
      ),
    );
  }

  Widget _toolButton(IconData icon, String tooltip, VoidCallback? onPressed,
      {Color? color}) {
    return IconButton(
      icon: Icon(icon,
          size: 20,
          color: onPressed == null
              ? AuraColors.textTertiary
              : (color ?? AuraColors.textPrimary)),
      tooltip: tooltip,
      onPressed: onPressed,
    );
  }

  Widget _buildBottomBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      child: Row(
        children: [
          Expanded(
            child: ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: AuraColors.surfaceLight,
                foregroundColor: AuraColors.textPrimary,
                side: BorderSide(color: AuraColors.border),
              ),
              onPressed: _isSaving ? null : _openAddGarmentSheet,
              icon: Icon(Icons.add, color: AuraColors.accentIris),
              label: const Text('Add Garment'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: ElevatedButton.icon(
              onPressed: _isSaving ? null : _showSaveDialog,
              icon: _isSaving
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.bookmark_border),
              label: Text(_isSaving ? 'Saving…' : 'Save Outfit'),
            ),
          ),
        ],
      ),
    );
  }
}
