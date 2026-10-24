import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../wardrobe/data/wardrobe_repository.dart';
import '../../wardrobe/presentation/garment_image.dart';
import '../data/outfit_repository.dart';
import '../domain/outfit_canvas_controller.dart';
import '../domain/outfit_layout.dart';

/// Static render of an outfit's canvas layout, scaled to fit whatever space it is given.
/// Used where no snapshot PNG exists (AI suggestions, outfits saved without the canvas).
class OutfitCollage extends StatelessWidget {
  final CanvasStateModel state;
  final List<WardrobeItemModel> garments;

  /// Defaults to the theme's light surface.
  final Color? background;

  const OutfitCollage({
    super.key,
    required this.state,
    required this.garments,
    this.background,
  });

  /// Auto-arranged flat lay of [garments].
  factory OutfitCollage.arranged(List<WardrobeItemModel> garments,
      {Key? key, Color? background}) {
    return OutfitCollage(
      key: key,
      state: autoArrangeOutfit(garments, collageReferenceSize),
      garments: garments,
      background: background,
    );
  }

  /// A saved outfit: its own canvas layout when it has one, otherwise an auto-arranged flat lay.
  factory OutfitCollage.forOutfit(OutfitModel outfit, {Key? key}) {
    final usable = outfit.canvasState.items.isNotEmpty &&
        outfit.canvasState.canvasWidth != null &&
        outfit.canvasState.canvasHeight != null;
    return usable
        ? OutfitCollage(
            key: key, state: outfit.canvasState, garments: outfit.items)
        : OutfitCollage.arranged(outfit.items, key: key);
  }

  /// Area the visible garments occupy (with a margin), so sparse looks fill the frame
  /// instead of floating small in an empty canvas.
  static Rect contentBounds(List<CanvasItemModel> items, Size canvas) {
    const box = OutfitCanvasController.itemSize;
    Rect? bounds;
    for (final e in items) {
      final centre = Offset(e.x + box.width / 2, e.y + box.height / 2);
      // Rotation can swing the box either way; the longer side bounds it safely
      final half = e.rotation == 0
          ? Size(box.width / 2 * e.scale, box.height / 2 * e.scale)
          : Size.square(box.longestSide / 2 * e.scale);
      final r = Rect.fromCenter(
          center: centre, width: half.width * 2, height: half.height * 2);
      bounds = bounds == null ? r : bounds.expandToInclude(r);
    }
    if (bounds == null) return Offset.zero & canvas;
    return bounds.inflate(bounds.longestSide * 0.06);
  }

  @override
  Widget build(BuildContext context) {
    final canvas = Size(
      state.canvasWidth ?? collageReferenceSize.width,
      state.canvasHeight ?? collageReferenceSize.height,
    );
    final byId = {for (final g in garments) g.id: g};
    final ordered = [...state.items.where((e) => byId.containsKey(e.itemId))]
      ..sort((a, b) => a.zIndex.compareTo(b.zIndex));
    final bounds = contentBounds(ordered, canvas);
    const box = OutfitCanvasController.itemSize;

    return ColoredBox(
      color: background ?? AuraColors.surfaceLight,
      // Tight constraints make FittedBox fill the slot (centred) instead of shrinking to the art
      child: SizedBox.expand(
        child: FittedBox(
          fit: BoxFit.contain,
          child: SizedBox(
            width: bounds.width,
            height: bounds.height,
            child: Stack(
              clipBehavior: Clip.hardEdge,
              children: [
                for (final e in ordered)
                  Positioned(
                    left: e.x - bounds.left,
                    top: e.y - bounds.top,
                    width: box.width,
                    height: box.height,
                    child: Transform.rotate(
                      angle: e.rotation,
                      child: Transform.scale(
                        scale: e.scale,
                        child: GarmentImage(garment: byId[e.itemId]!),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
