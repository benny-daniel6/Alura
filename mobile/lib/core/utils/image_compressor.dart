import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as img;

class ImageCompressionException implements Exception {
  final String message;
  ImageCompressionException(this.message);

  @override
  String toString() => message;
}

class ClientImageCompressor {
  static const int defaultMaxDimension = 1024;
  static const int defaultQuality = 85;

  /// Downscales image to max 1024px on the longest side while preserving aspect ratio,
  /// bakes EXIF orientation into the pixels, and encodes as JPEG with quality 85.
  /// Never upscales. Throws [ImageCompressionException] if the bytes are not a decodable image.
  static Uint8List compressAndResize(
    Uint8List rawBytes, {
    int maxDimension = defaultMaxDimension,
    int quality = defaultQuality,
  }) {
    // 1. Decode original image bytes (JPEG/PNG/WebP/HEIC-converted-by-picker etc.)
    final image = img.decodeImage(rawBytes);
    if (image == null) {
      throw ImageCompressionException(
          'Unsupported or corrupt image; could not decode it for compression.');
    }

    // 2. EXIF orientation normalization
    final orientedImage = img.bakeOrientation(image);

    // 3. Resize so the longest side is at most maxDimension
    img.Image resizedImage = orientedImage;
    if (orientedImage.width > maxDimension ||
        orientedImage.height > maxDimension) {
      final landscape = orientedImage.width >= orientedImage.height;
      resizedImage = img.copyResize(
        orientedImage,
        width: landscape ? maxDimension : null,
        height: landscape ? null : maxDimension,
        interpolation: img.Interpolation.average,
      );
    }

    // 4. Encode to JPEG with requested quality (85). Alpha is flattened; the server cuts out the garment anyway.
    return Uint8List.fromList(img.encodeJpg(resizedImage, quality: quality));
  }

  /// Runs [compressAndResize] on a background isolate so large camera photos don't jank the UI.
  static Future<Uint8List> compressInBackground(
    Uint8List rawBytes, {
    int maxDimension = defaultMaxDimension,
    int quality = defaultQuality,
  }) {
    return compute(
      _compressEntry,
      _CompressionRequest(rawBytes, maxDimension, quality),
    );
  }

  static Uint8List _compressEntry(_CompressionRequest request) =>
      compressAndResize(
        request.bytes,
        maxDimension: request.maxDimension,
        quality: request.quality,
      );
}

class _CompressionRequest {
  final Uint8List bytes;
  final int maxDimension;
  final int quality;

  const _CompressionRequest(this.bytes, this.maxDimension, this.quality);
}
