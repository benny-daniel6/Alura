import 'dart:typed_data';

import 'package:aura_wardrobe/core/utils/image_compressor.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

Uint8List _png(int width, int height) => Uint8List.fromList(img.encodePng(
    img.Image(width: width, height: height)..clear(img.ColorRgb8(30, 40, 90))));

void main() {
  group('ClientImageCompressor', () {
    test(
        'downscales landscape so the longest side is 1024px, keeping aspect ratio',
        () {
      final out = img.decodeJpg(
          ClientImageCompressor.compressAndResize(_png(4032, 3024)))!;
      expect(out.width, 1024);
      expect(out.height, 768);
    });

    test('downscales portrait by height', () {
      final out = img.decodeJpg(
          ClientImageCompressor.compressAndResize(_png(3000, 4000)))!;
      expect(out.height, 1024);
      expect(out.width, 768);
    });

    test('never upscales small images but still re-encodes to JPEG', () {
      final bytes = ClientImageCompressor.compressAndResize(_png(640, 480));
      expect(bytes.sublist(0, 2), [0xFF, 0xD8]); // JPEG SOI marker
      final out = img.decodeJpg(bytes)!;
      expect(out.width, 640);
      expect(out.height, 480);
    });

    test('uses quality 85 by default (smaller than q100, larger than q50)', () {
      final noisy = img.Image(width: 1024, height: 1024);
      for (final p in noisy) {
        p
          ..r = (p.x * 7 + p.y * 13) % 256
          ..g = (p.x * p.y) % 256
          ..b = (p.x ^ p.y) % 256;
      }
      final source = Uint8List.fromList(img.encodePng(noisy));
      final q85 = ClientImageCompressor.compressAndResize(source).length;
      final q100 =
          ClientImageCompressor.compressAndResize(source, quality: 100).length;
      final q50 =
          ClientImageCompressor.compressAndResize(source, quality: 50).length;
      expect(q85, lessThan(q100));
      expect(q85, greaterThan(q50));
    });

    test('bakes EXIF orientation into pixels', () {
      // Stored 400x200 with "rotate 90° CW" orientation -> displayed 200x400
      final stored = img.Image(width: 400, height: 200)
        ..clear(img.ColorRgb8(255, 255, 255));
      stored.exif.imageIfd.orientation = 6;
      final jpeg = Uint8List.fromList(img.encodeJpg(stored));

      final out = img.decodeJpg(ClientImageCompressor.compressAndResize(jpeg))!;
      expect(out.width, 200);
      expect(out.height, 400);
      expect(out.exif.imageIfd.orientation ?? 1, 1);
    });

    test('throws instead of passing through bytes it cannot decode', () {
      expect(
        () => ClientImageCompressor.compressAndResize(
            Uint8List.fromList(List.generate(1024, (i) => i % 256))),
        throwsA(isA<ImageCompressionException>()),
      );
    });
  });
}
