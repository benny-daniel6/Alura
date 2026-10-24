import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/foundation.dart';

import '../../wardrobe/data/wardrobe_repository.dart';
import '../data/outfit_repository.dart';
import 'outfit_layout.dart';

/// A garment placed on the canvas. (x, y) is the top-left of the untransformed
/// [OutfitCanvasController.itemSize] box; scale and rotation (radians, clockwise) apply around its centre.
class CanvasPlacedItem {
  final WardrobeItemModel garment;
  double x;
  double y;
  double scale;
  double rotation;
  int zIndex;

  CanvasPlacedItem({
    required this.garment,
    this.x = 0.0,
    this.y = 0.0,
    this.scale = 1.0,
    this.rotation = 0.0,
    this.zIndex = 0,
  });

  Offset get center => Offset(
        x + OutfitCanvasController.itemSize.width / 2,
        y + OutfitCanvasController.itemSize.height / 2,
      );

  CanvasItemModel toModel() => CanvasItemModel(
        itemId: garment.id,
        x: x,
        y: y,
        scale: scale,
        rotation: rotation,
        zIndex: zIndex,
      );
}

/// All canvas state and editing operations, independent of widgets so it can be unit tested.
class OutfitCanvasController extends ChangeNotifier {
  static const Size itemSize = Size(160, 200);
  // Must stay within the backend CanvasItemState bounds (ge=0.2, le=5.0)
  static const double minScale = 0.2;
  static const double maxScale = 5.0;

  final List<CanvasPlacedItem> _items = [];
  CanvasPlacedItem? _selected;

  double _gestureStartScale = 1.0;
  double _gestureStartRotation = 0.0;

  List<CanvasPlacedItem> get items => List.unmodifiable(_items);
  CanvasPlacedItem? get selected => _selected;
  bool get isEmpty => _items.isEmpty;

  /// Back-to-front order for painting.
  List<CanvasPlacedItem> get paintOrder =>
      [..._items]..sort((a, b) => a.zIndex.compareTo(b.zIndex));

  bool contains(String garmentId) =>
      _items.any((i) => i.garment.id == garmentId);

  CanvasPlacedItem add(WardrobeItemModel garment, Size canvasSize) {
    final existing = _items.where((i) => i.garment.id == garment.id);
    if (existing.isNotEmpty) {
      select(existing.first);
      return existing.first;
    }
    final cascade = (_items.length % 6) * 18.0;
    final item = CanvasPlacedItem(
      garment: garment,
      x: (canvasSize.width - itemSize.width) / 2 + cascade,
      y: (canvasSize.height - itemSize.height) / 2 + cascade,
      zIndex:
          _items.isEmpty ? 0 : _items.map((e) => e.zIndex).reduce(math.max) + 1,
    );
    _items.add(item);
    _selected = item;
    notifyListeners();
    return item;
  }

  /// Replaces the canvas with [garments] laid out as a flat lay.
  void arrange(List<WardrobeItemModel> garments, Size canvasSize) {
    final state = autoArrangeOutfit(garments, canvasSize);
    final byId = {for (final g in garments) g.id: g};
    _items
      ..clear()
      ..addAll(state.items.map((e) => CanvasPlacedItem(
            garment: byId[e.itemId]!,
            x: e.x,
            y: e.y,
            scale: e.scale,
            rotation: e.rotation,
            zIndex: e.zIndex,
          )));
    _selected = null;
    notifyListeners();
  }

  /// Adds garments not yet on the canvas at their flat-lay spots, leaving placed pieces untouched.
  /// Returns how many were added.
  int addArranged(List<WardrobeItemModel> garments, Size canvasSize) {
    final fresh = garments.where((g) => !contains(g.id)).toList();
    if (fresh.isEmpty) return 0;
    final layout = autoArrangeOutfit(
        [..._items.map((i) => i.garment), ...fresh], canvasSize);
    final byId = {for (final e in layout.items) e.itemId: e};
    var z =
        _items.isEmpty ? 0 : _items.map((e) => e.zIndex).reduce(math.max) + 1;
    for (final g in fresh) {
      final e = byId[g.id]!;
      _items.add(CanvasPlacedItem(
          garment: g, x: e.x, y: e.y, scale: e.scale, zIndex: z++));
    }
    _selected = null;
    notifyListeners();
    return fresh.length;
  }

  void select(CanvasPlacedItem? item) {
    if (_selected == item) return;
    _selected = item;
    notifyListeners();
  }

  void removeSelected() {
    if (_selected == null) return;
    _items.remove(_selected);
    _selected = null;
    _normalizeZ();
    notifyListeners();
  }

  void clear() {
    _items.clear();
    _selected = null;
    notifyListeners();
  }

  /// Topmost item whose rotated/scaled box contains [point] (canvas coordinates).
  CanvasPlacedItem? hitTest(Offset point) {
    for (final item in paintOrder.reversed) {
      final d = point - item.center;
      // Inverse rotation, then inverse scale, into the item's local box
      final cosR = math.cos(item.rotation);
      final sinR = math.sin(item.rotation);
      final localX = (d.dx * cosR + d.dy * sinR) / item.scale;
      final localY = (-d.dx * sinR + d.dy * cosR) / item.scale;
      if (localX.abs() <= itemSize.width / 2 &&
          localY.abs() <= itemSize.height / 2) {
        return item;
      }
    }
    return null;
  }

  // ---------- Gestures (one-finger drag, two-finger pinch + twist) ----------

  void beginTransform() {
    final item = _selected;
    if (item == null) return;
    _gestureStartScale = item.scale;
    _gestureStartRotation = item.rotation;
  }

  /// [focalDelta] is the focal point movement since the last update; [scale] and [rotation]
  /// are cumulative since [beginTransform] (as reported by ScaleUpdateDetails).
  void updateTransform(
      {required Offset focalDelta, double scale = 1.0, double rotation = 0.0}) {
    final item = _selected;
    if (item == null) return;
    item.x += focalDelta.dx;
    item.y += focalDelta.dy;
    item.scale = (_gestureStartScale * scale).clamp(minScale, maxScale);
    item.rotation = _normalizeAngle(_gestureStartRotation + rotation);
    notifyListeners();
  }

  void resetTransformOfSelected() {
    final item = _selected;
    if (item == null) return;
    item.scale = 1.0;
    item.rotation = 0.0;
    notifyListeners();
  }

  // ---------- Layering ----------

  void bringToFront() => _reorder((order, i) {
        order.add(order.removeAt(i));
      });

  void sendToBack() => _reorder((order, i) {
        order.insert(0, order.removeAt(i));
      });

  void bringForward() => _reorder((order, i) {
        if (i < order.length - 1) order.insert(i + 1, order.removeAt(i));
      });

  void sendBackward() => _reorder((order, i) {
        if (i > 0) order.insert(i - 1, order.removeAt(i));
      });

  void _reorder(void Function(List<CanvasPlacedItem> order, int index) change) {
    final item = _selected;
    if (item == null) return;
    final order = paintOrder;
    change(order, order.indexOf(item));
    for (var z = 0; z < order.length; z++) {
      order[z].zIndex = z;
    }
    notifyListeners();
  }

  void _normalizeZ() {
    final order = paintOrder;
    for (var z = 0; z < order.length; z++) {
      order[z].zIndex = z;
    }
  }

  // ---------- Persistence ----------

  CanvasStateModel toCanvasState(Size canvasSize) {
    _normalizeZ();
    return CanvasStateModel(
      items: paintOrder.map((e) => e.toModel()).toList(),
      canvasWidth: canvasSize.width,
      canvasHeight: canvasSize.height,
    );
  }

  /// Restores a saved outfit, rescaling positions if it was authored on a different canvas size.
  void loadOutfit(OutfitModel outfit, Size canvasSize) {
    final garmentsById = {for (final g in outfit.items) g.id: g};
    final state = outfit.canvasState;
    final sx = (state.canvasWidth != null && state.canvasWidth! > 0)
        ? canvasSize.width / state.canvasWidth!
        : 1.0;
    final sy = (state.canvasHeight != null && state.canvasHeight! > 0)
        ? canvasSize.height / state.canvasHeight!
        : 1.0;
    final sizeFactor = math.min(sx, sy);

    _items
      ..clear()
      ..addAll(
          state.items.where((e) => garmentsById.containsKey(e.itemId)).map((e) {
        // Rescale around item centres so garments keep their relative composition
        final cx = (e.x + itemSize.width / 2) * sx;
        final cy = (e.y + itemSize.height / 2) * sy;
        return CanvasPlacedItem(
          garment: garmentsById[e.itemId]!,
          x: cx - itemSize.width / 2,
          y: cy - itemSize.height / 2,
          scale: (e.scale * sizeFactor).clamp(minScale, maxScale),
          rotation: e.rotation,
          zIndex: e.zIndex,
        );
      }));
    _selected = null;
    _normalizeZ();
    notifyListeners();
  }

  static double _normalizeAngle(double angle) {
    const twoPi = 2 * math.pi;
    var a = angle % twoPi;
    if (a > math.pi) a -= twoPi;
    return a;
  }
}
