import 'dart:math' as math;
import 'dart:ui';

import '../../wardrobe/data/wardrobe_repository.dart';
import '../data/outfit_repository.dart';
import 'outfit_canvas_controller.dart';

/// Where a category sits in an auto-arranged flat lay: centre as a fraction of the canvas,
/// size relative to a 400x600 reference canvas, and paint order (higher = in front).
class _Slot {
  final double cx;
  final double cy;
  final double scale;
  final int z;
  const _Slot(this.cx, this.cy, this.scale, this.z);
}

const _referenceSize = Size(400, 600);

const Map<String, List<_Slot>> _slots = {
  'headwear': [_Slot(0.17, 0.10, 0.55, 6)],
  'top': [_Slot(0.42, 0.29, 1.05, 3)],
  'dress': [_Slot(0.45, 0.42, 1.55, 3)],
  'one_piece': [_Slot(0.45, 0.42, 1.55, 3)],
  'outerwear': [_Slot(0.70, 0.33, 1.05, 4)],
  'bottom': [_Slot(0.42, 0.63, 1.15, 2)],
  'footwear': [_Slot(0.40, 0.89, 0.6, 1)],
  'bag': [_Slot(0.82, 0.68, 0.62, 5)],
  'accessory': [_Slot(0.82, 0.12, 0.45, 6), _Slot(0.16, 0.80, 0.45, 6)],
};

const _overflowSlot = _Slot(0.82, 0.88, 0.45, 7);

/// Arranges garments as an editorial flat lay (top above bottom, shoes below, accessories at the side).
/// Coordinates follow the canvas convention: (x, y) is the top-left of the unscaled item box.
CanvasStateModel autoArrangeOutfit(
    List<WardrobeItemModel> garments, Size canvasSize) {
  final k = math.min(canvasSize.width / _referenceSize.width,
      canvasSize.height / _referenceSize.height);
  final hasOuterwear = garments.any((g) => g.category == 'outerwear');
  final used = <String, int>{};
  final placed = <CanvasItemModel>[];

  for (final g in garments) {
    final options = _slots[g.category] ?? _slots['accessory']!;
    final n = used[g.category] ?? 0;
    used[g.category] = n + 1;
    var slot = n < options.length ? options[n] : _overflowSlot;
    // Make room for a jacket beside the top
    if (hasOuterwear &&
        (g.category == 'top' ||
            g.category == 'dress' ||
            g.category == 'one_piece')) {
      slot = _Slot(slot.cx - 0.12, slot.cy, slot.scale, slot.z);
    }
    final box = OutfitCanvasController.itemSize;
    placed.add(CanvasItemModel(
      itemId: g.id,
      x: slot.cx * canvasSize.width - box.width / 2,
      y: slot.cy * canvasSize.height - box.height / 2,
      scale: (slot.scale * k).clamp(
          OutfitCanvasController.minScale, OutfitCanvasController.maxScale),
      zIndex: slot.z,
    ));
  }

  // Contiguous z-indexes in paint order
  final order = [...placed]..sort((a, b) => a.zIndex.compareTo(b.zIndex));
  for (var i = 0; i < order.length; i++) {
    order[i].zIndex = i;
  }
  return CanvasStateModel(
      items: order,
      canvasWidth: canvasSize.width,
      canvasHeight: canvasSize.height);
}

/// Logical canvas size used for collages that are not tied to a screen (e.g. stylist suggestions).
const Size collageReferenceSize = _referenceSize;
