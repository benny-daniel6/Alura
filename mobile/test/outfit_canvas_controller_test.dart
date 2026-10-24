import 'dart:math' as math;
import 'dart:ui';

import 'package:aura_wardrobe/features/outfits/data/outfit_repository.dart';
import 'package:aura_wardrobe/features/outfits/domain/outfit_canvas_controller.dart';
import 'package:aura_wardrobe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:flutter_test/flutter_test.dart';

WardrobeItemModel garment(String id) => WardrobeItemModel(
      id: id,
      userId: 'u1',
      name: 'Garment $id',
      category: 'top',
      seasons: const ['all_season'],
      occasions: const [],
      originalImageUrl: '/static/originals/$id.jpg',
      cutoutImageUrl: '/static/cutouts/$id.png',
      status: 'completed',
      isFavorite: false,
      wearCount: 0,
    );

const canvasSize = Size(400, 600);
// Mirrors OutfitCanvasController.itemSize (asserted below) so offsets can be const
const double w = 160;
const double h = 200;

void main() {
  late OutfitCanvasController c;

  setUp(() => c = OutfitCanvasController());

  test('item box size matches the constants used in these tests', () {
    expect(OutfitCanvasController.itemSize, const Size(w, h));
  });

  test(
      'add centres the item, selects it, and stacks z-index; duplicates are not added twice',
      () {
    final a = c.add(garment('a'), canvasSize);
    expect(a.x, (400 - w) / 2);
    expect(a.y, (600 - h) / 2);
    expect(c.selected, a);
    final b = c.add(garment('b'), canvasSize);
    expect(b.zIndex, greaterThan(a.zIndex));

    c.add(garment('a'), canvasSize);
    expect(c.items.length, 2);
    expect(c.selected, a);
  });

  group('hitTest', () {
    test('returns the topmost item under the point', () {
      final a = c.add(garment('a'), canvasSize);
      final b = c.add(garment('b'), canvasSize);
      expect(c.hitTest(b.center), b);
      c.select(a);
      c.bringToFront();
      expect(c.hitTest(a.center), a);
      expect(c.hitTest(const Offset(1, 1)), isNull);
    });

    test('respects scale', () {
      final a = c.add(garment('a'), canvasSize);
      final justOutside = a.center + const Offset(w / 2 + 10, 0);
      expect(c.hitTest(justOutside), isNull);
      a.scale = 1.5;
      expect(c.hitTest(justOutside), a);
    });

    test('respects rotation', () {
      final a = c.add(garment('a'), canvasSize);
      // Point inside the tall box vertically but outside its width
      final p = a.center + const Offset(0, -(w / 2 + 15));
      expect(c.hitTest(p), a);
      final q = a.center + const Offset(w / 2 + 15, 0);
      expect(c.hitTest(q), isNull);
      a.rotation = math.pi / 2; // now wide: q is inside, p is outside
      expect(c.hitTest(q), a);
      expect(c.hitTest(a.center + const Offset(0, -(h / 2 - 5))), isNull);
    });
  });

  group('gestures', () {
    test(
        'drag moves, pinch scales from the gesture start, twist rotates; scale is clamped',
        () {
      final a = c.add(garment('a'), canvasSize);
      final start = Offset(a.x, a.y);
      c.beginTransform();
      c.updateTransform(
          focalDelta: const Offset(10, -5), scale: 1.5, rotation: 0.2);
      c.updateTransform(
          focalDelta: const Offset(5, 5), scale: 2.0, rotation: 0.4);
      expect(Offset(a.x, a.y), start + const Offset(15, 0));
      expect(a.scale, 2.0); // cumulative, not compounded
      expect(a.rotation, closeTo(0.4, 1e-9));

      c.beginTransform();
      c.updateTransform(focalDelta: Offset.zero, scale: 100);
      expect(a.scale, OutfitCanvasController.maxScale);
      c.beginTransform();
      c.updateTransform(focalDelta: Offset.zero, scale: 0.0001);
      expect(a.scale, OutfitCanvasController.minScale);
    });

    test('no-op without a selection', () {
      c.add(garment('a'), canvasSize);
      c.select(null);
      c.beginTransform();
      c.updateTransform(focalDelta: const Offset(50, 50), scale: 3);
      expect(c.items.single.scale, 1.0);
    });
  });

  group('layering', () {
    late CanvasPlacedItem a, b, d;
    setUp(() {
      a = c.add(garment('a'), canvasSize);
      b = c.add(garment('b'), canvasSize);
      d = c.add(garment('d'), canvasSize);
    });

    List<String> order() => c.paintOrder.map((e) => e.garment.id).toList();

    test('bring to front / send to back', () {
      c.select(a);
      c.bringToFront();
      expect(order(), ['b', 'd', 'a']);
      c.select(d);
      c.sendToBack();
      expect(order(), ['d', 'b', 'a']);
    });

    test('step forward / backward and stop at the ends', () {
      c.select(a);
      c.bringForward();
      expect(order(), ['b', 'a', 'd']);
      c.bringForward();
      c.bringForward();
      expect(order(), ['b', 'd', 'a']);
      c.select(b);
      c.sendBackward();
      expect(order(), ['b', 'd', 'a']);
    });

    test('z-indexes stay contiguous after removal', () {
      c.select(b);
      c.removeSelected();
      expect(c.paintOrder.map((e) => e.zIndex), [0, 1]);
      expect(c.selected, isNull);
    });
  });

  test(
      'toCanvasState round-trips through loadOutfit, rescaling to a new canvas size',
      () {
    final a = c.add(garment('a'), canvasSize)
      ..x = 20
      ..y = 40
      ..scale = 1.2
      ..rotation = 0.5;
    c.add(garment('b'), canvasSize);
    c.select(a);
    c.bringToFront();

    final state = c.toCanvasState(canvasSize);
    expect(state.canvasWidth, 400);
    expect(state.canvasHeight, 600);
    expect(state.items.last.itemId, 'a');
    expect(state.items.map((e) => e.zIndex), [0, 1]);

    final json = state.toJson();
    final outfit = OutfitModel.fromJson({
      'id': 'o1',
      'user_id': 'u1',
      'name': 'Look',
      'occasions': <String>[],
      'season': 'fall',
      'canvas_state': json,
      'is_favorite': false,
      'is_public': false,
      'items_count': 2,
      'items': [
        for (final id in ['b', 'a'])
          {
            'id': id,
            'user_id': 'u1',
            'category': 'top',
            'original_image_url': '/static/originals/$id.jpg',
            'status': 'completed',
          }
      ],
      'created_at': '2026-10-20T00:00:00Z',
    });

    // Same size: identical placement
    final same = OutfitCanvasController()..loadOutfit(outfit, canvasSize);
    final restored = same.items.firstWhere((e) => e.garment.id == 'a');
    expect(restored.x, closeTo(20, 1e-9));
    expect(restored.y, closeTo(40, 1e-9));
    expect(restored.scale, closeTo(1.2, 1e-9));
    expect(restored.rotation, closeTo(0.5, 1e-9));
    expect(same.paintOrder.last.garment.id, 'a');

    // Half-size canvas: centres scale by 0.5, garment size by 0.5
    final half = OutfitCanvasController()
      ..loadOutfit(outfit, const Size(200, 300));
    final small = half.items.firstWhere((e) => e.garment.id == 'a');
    expect(small.center.dx, closeTo((20 + w / 2) * 0.5, 1e-9));
    expect(small.center.dy, closeTo((40 + h / 2) * 0.5, 1e-9));
    expect(small.scale, closeTo(0.6, 1e-9));
  });

  test('loadOutfit drops canvas entries whose garment no longer exists', () {
    final outfit = OutfitModel(
      id: 'o1',
      userId: 'u1',
      name: 'Look',
      occasions: const [],
      season: 'all_season',
      canvasState: CanvasStateModel(items: [
        CanvasItemModel(itemId: 'gone'),
        CanvasItemModel(itemId: 'a', zIndex: 3),
      ]),
      isFavorite: false,
      isPublic: false,
      itemsCount: 1,
      items: [garment('a')],
      createdAt: DateTime(2026),
    );
    c.loadOutfit(outfit, canvasSize);
    expect(c.items.map((e) => e.garment.id), ['a']);
    expect(c.items.single.zIndex, 0);
  });
}
