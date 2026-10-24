import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../../../core/constants/api_constants.dart';
import '../../../core/theme/app_theme.dart';
import '../data/wardrobe_repository.dart';

enum GarmentImageVariant { cutout, showcase, original }

/// Renders a garment's transparent cutout (default), its white-background studio photo, or the
/// original photo, falling back through the other assets when one is missing.
class GarmentImage extends StatelessWidget {
  final WardrobeItemModel garment;
  final BoxFit fit;
  final bool preferThumbnail;
  final GarmentImageVariant variant;

  const GarmentImage({
    super.key,
    required this.garment,
    this.fit = BoxFit.contain,
    this.preferThumbnail = false,
    this.variant = GarmentImageVariant.cutout,
  });

  String? get _url {
    final List<String?> candidates;
    switch (variant) {
      case GarmentImageVariant.showcase:
        candidates = [
          garment.showcaseImageUrl,
          garment.cutoutImageUrl,
          garment.originalImageUrl
        ];
      case GarmentImageVariant.original:
        candidates = [garment.originalImageUrl];
      case GarmentImageVariant.cutout:
        candidates = preferThumbnail
            ? [
                garment.thumbnailUrl,
                garment.cutoutImageUrl,
                garment.originalImageUrl
              ]
            : [
                garment.cutoutImageUrl,
                garment.thumbnailUrl,
                garment.originalImageUrl
              ];
    }
    for (final c in candidates) {
      final resolved = ApiConstants.mediaUrl(c);
      if (resolved != null) return resolved;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final url = _url;
    if (url == null) return const _GarmentPlaceholder();
    return CachedNetworkImage(
      imageUrl: url,
      fit: fit,
      fadeInDuration: const Duration(milliseconds: 120),
      placeholder: (_, __) => Center(
        child: SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(
              strokeWidth: 2, color: AuraColors.accentIris),
        ),
      ),
      errorWidget: (_, __, ___) => const _GarmentPlaceholder(),
    );
  }
}

class _GarmentPlaceholder extends StatelessWidget {
  const _GarmentPlaceholder();

  @override
  Widget build(BuildContext context) {
    return Center(
        child: Icon(Icons.checkroom, color: AuraColors.textTertiary, size: 32));
  }
}
