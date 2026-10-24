import 'dart:ui';

import 'package:aura_wardrobe/features/outfits/data/outfit_repository.dart';
import 'package:aura_wardrobe/features/outfits/domain/outfit_canvas_controller.dart';
import 'package:aura_wardrobe/features/outfits/domain/outfit_layout.dart';
import 'package:aura_wardrobe/features/outfits/presentation/outfit_collage.dart';
import 'package:aura_wardrobe/features/stylist/data/stylist_repository.dart';
import 'package:aura_wardrobe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:flutter_test/flutter_test.dart';

WardrobeItemModel garment(String id, String category) => WardrobeItemModel(
      id: id,
      userId: 'u1',
      name: id,
      category: category,
      seasons: const ['all_season'],
      occasions: const [],
      originalImageUrl: '/static/originals/$id.jpg',
      cutoutImageUrl: '/static/cutouts/$id.png',
      status: 'completed',
      isFavorite: false,
      wearCount: 0,
    );

const canvas = Size(400, 600);

void main() {
  group('autoArrangeOutfit', () {
    Offset centre(CanvasStateModel s, String id) {
      final e = s.items.firstWhere((i) => i.itemId == id);
      return Offset(
        e.x + OutfitCanvasController.itemSize.width / 2,
        e.y + OutfitCanvasController.itemSize.height / 2,
      );
    }

    test(
        'lays out a flat lay: hat, top, bottom, shoes from top to bottom; jacket beside the top',
        () {
      final state = autoArrangeOutfit([
        garment('shoes', 'footwear'),
        garment('jeans', 'bottom'),
        garment('tee', 'top'),
        garment('jacket', 'outerwear'),
        garment('cap', 'headwear'),
      ], canvas);
      final s = state;

      expect(centre(s, 'cap').dy, lessThan(centre(s, 'tee').dy));
      expect(centre(s, 'tee').dy, lessThan(centre(s, 'jeans').dy));
      expect(centre(s, 'jeans').dy, lessThan(centre(s, 'shoes').dy));
      expect(centre(s, 'jacket').dx, greaterThan(centre(s, 'tee').dx));
      expect(state.canvasWidth, 400);
      expect(state.canvasHeight, 600);
    });

    test(
        'paint order puts the top over the bottom and the jacket over the top, with contiguous z',
        () {
      final state = autoArrangeOutfit(
        [
          garment('tee', 'top'),
          garment('jeans', 'bottom'),
          garment('jacket', 'outerwear')
        ],
        canvas,
      );
      final z = {for (final e in state.items) e.itemId: e.zIndex};
      expect(z['jeans']! < z['tee']! && z['tee']! < z['jacket']!, isTrue);
      expect(state.items.map((e) => e.zIndex).toList()..sort(), [0, 1, 2]);
    });

    test('scales with the canvas and stays within backend scale bounds', () {
      final small =
          autoArrangeOutfit([garment('dress', 'dress')], const Size(100, 150));
      final big = autoArrangeOutfit(
          [garment('dress', 'dress')], const Size(4000, 6000));
      expect(small.items.single.scale, closeTo(1.55 * 0.25, 1e-9));
      expect(big.items.single.scale, OutfitCanvasController.maxScale);
    });

    test('extra accessories beyond the slots still get a position', () {
      final state = autoArrangeOutfit(
        [for (var i = 0; i < 4; i++) garment('acc$i', 'accessory')],
        canvas,
      );
      expect(state.items.length, 4);
    });
  });

  group('canvas controller AI helpers', () {
    test('arrange replaces the canvas with an auto layout', () {
      final c = OutfitCanvasController()..add(garment('old', 'top'), canvas);
      c.arrange([garment('tee', 'top'), garment('jeans', 'bottom')], canvas);
      expect(c.items.map((e) => e.garment.id), containsAll(['tee', 'jeans']));
      expect(c.contains('old'), isFalse);
      expect(c.selected, isNull);
    });

    test('addArranged adds only new pieces, on top, without moving placed ones',
        () {
      final c = OutfitCanvasController();
      final tee = c.add(garment('tee', 'top'), canvas)
        ..x = 5
        ..y = 7;
      final added = c.addArranged([
        garment('tee', 'top'),
        garment('jeans', 'bottom'),
        garment('shoes', 'footwear')
      ], canvas);
      expect(added, 2);
      expect(c.items.length, 3);
      expect(tee.x, 5);
      expect(tee.y, 7);
      final newest = c.items.where((e) => e.garment.id != 'tee');
      expect(newest.every((e) => e.zIndex > tee.zIndex), isTrue);
      expect(c.addArranged([garment('tee', 'top')], canvas), 0);
    });
  });

  test('collage crops to the garments so a single piece fills the frame', () {
    final state = autoArrangeOutfit([garment('tee', 'top')], canvas);
    final bounds = OutfitCollage.contentBounds(state.items, canvas);
    final e = state.items.single;
    expect(bounds.width, lessThan(canvas.width / 1.5));
    expect(bounds.contains(Offset(e.x + 80, e.y + 100)), isTrue);
    expect(OutfitCollage.contentBounds(const [], canvas), Offset.zero & canvas);
  });

  test('stylist response parsing', () {
    final result = StylistResultModel.fromJson({
      'engine': 'gemini',
      'total_wardrobe_items': 2,
      'weather': {
        'location_name': 'Mumbai, India',
        'temperature_c': 31,
        'apparent_temperature_c': 35.5,
        'condition': 'Partly cloudy',
        'is_hot': true,
      },
      'outfits': [
        {
          'name': 'Coastal Ease',
          'occasion': 'casual_daily',
          'rationale': 'Light and breezy.',
          'styling_tips': ['Roll the sleeves.'],
          'is_complete': false,
          'missing_categories': ['bottom'],
          'missing_pieces': ['light chinos'],
          'items': [
            {
              'id': 'a',
              'user_id': 'u1',
              'category': 'top',
              'original_image_url': '/x.jpg',
              'showcase_image_url': '/static/showcase/a.png',
              'status': 'completed',
              'last_worn_at': '2026-10-20T08:00:00Z'
            },
          ],
        },
      ],
    });
    expect(result.engine, 'gemini');
    expect(result.weather.temperatureC, 31.0);
    expect(result.weather.isHot, isTrue);
    expect(result.weather.isFallback, isFalse);
    final look = result.outfits.single;
    expect(look.isComplete, isFalse);
    expect(look.missingPieces, ['light chinos']);
    expect(look.items.single.showcaseImageUrl, '/static/showcase/a.png');
    expect(look.items.single.lastWornAt, DateTime.utc(2026, 10, 20, 8));
  });
}
