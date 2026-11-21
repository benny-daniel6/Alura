import 'dart:typed_data';
import 'package:dio/dio.dart';
import '../../../core/constants/api_constants.dart';
import '../../../core/network/api_client.dart';
import '../../../core/utils/image_compressor.dart';

class WardrobeItemModel {
  final String id;
  final String userId;
  String? name;
  String category;
  String? subCategory;
  String? primaryColor;
  String? secondaryColor;
  List<String> seasons;
  List<String> occasions;
  String? brand;
  String? size;
  final String originalImageUrl;
  String? cutoutImageUrl;
  String? showcaseImageUrl;
  String? thumbnailUrl;
  String status;
  String? errorMessage;
  bool isFavorite;
  int wearCount;
  DateTime? lastWornAt;

  WardrobeItemModel({
    required this.id,
    required this.userId,
    this.name,
    required this.category,
    this.subCategory,
    this.primaryColor,
    this.secondaryColor,
    required this.seasons,
    required this.occasions,
    this.brand,
    this.size,
    required this.originalImageUrl,
    this.cutoutImageUrl,
    this.showcaseImageUrl,
    this.thumbnailUrl,
    required this.status,
    this.errorMessage,
    required this.isFavorite,
    required this.wearCount,
    this.lastWornAt,
  });

  factory WardrobeItemModel.fromJson(Map<String, dynamic> json) {
    return WardrobeItemModel(
      id: json['id'] ?? '',
      userId: json['user_id'] ?? '',
      name: json['name'],
      category: json['category'] ?? 'top',
      subCategory: json['sub_category'],
      primaryColor: json['primary_color'],
      secondaryColor: json['secondary_color'],
      seasons: List<String>.from(json['seasons'] ?? ['all_season']),
      occasions: List<String>.from(json['occasions'] ?? []),
      brand: json['brand'],
      size: json['size'],
      originalImageUrl: json['original_image_url'] ?? '',
      cutoutImageUrl: json['cutout_image_url'],
      showcaseImageUrl: json['showcase_image_url'],
      thumbnailUrl: json['thumbnail_url'],
      status: json['status'] ?? 'pending',
      errorMessage: json['error_message'],
      isFavorite: json['is_favorite'] ?? false,
      wearCount: json['wear_count'] ?? 0,
      lastWornAt: DateTime.tryParse(json['last_worn_at'] ?? ''),
    );
  }
}

class WardrobeUploadResult {
  final String itemId;
  final String jobId;
  final String status;
  final String message;

  WardrobeUploadResult({
    required this.itemId,
    required this.jobId,
    required this.status,
    required this.message,
  });

  factory WardrobeUploadResult.fromJson(Map<String, dynamic> json) {
    return WardrobeUploadResult(
      itemId: json['item_id'] ?? '',
      jobId: json['job_id'] ?? '',
      status: json['status'] ?? 'pending',
      message: json['message'] ?? '',
    );
  }
}

class WardrobeStatusResult {
  final String itemId;
  final String status;
  final String? errorMessage;
  final WardrobeItemModel? item;

  WardrobeStatusResult({
    required this.itemId,
    required this.status,
    this.errorMessage,
    this.item,
  });

  factory WardrobeStatusResult.fromJson(Map<String, dynamic> json) {
    return WardrobeStatusResult(
      itemId: json['item_id'] ?? '',
      status: json['status'] ?? 'pending',
      errorMessage: json['error_message'],
      item: json['item'] != null
          ? WardrobeItemModel.fromJson(json['item'])
          : null,
    );
  }
}

class WardrobeRepository {
  final ApiClient _apiClient = ApiClient();

  /// Uploads garment image bytes with client-side compression (max 1024px, quality 85)
  Future<WardrobeUploadResult> uploadGarment({
    required Uint8List bytes,
    required String filename,
    String? initialCategory,
  }) async {
    // 1. Real client-side resize to max 1024px and JPEG 85 compression (off the UI isolate).
    // Undecodable input throws ImageCompressionException; raw bytes are never uploaded uncompressed.
    final processedBytes = await ClientImageCompressor.compressInBackground(
      bytes,
      maxDimension: 1024,
      quality: 85,
    );

    // 2. Server limit is 10MB; a 1024px q85 JPEG is typically 100-400KB
    const maxBytes = 10 * 1024 * 1024;
    if (processedBytes.length > maxBytes) {
      throw Exception('Image exceeds 10MB after compression.');
    }

    final uploadFilename =
        '${filename.replaceAll(RegExp(r'\.[^.]+$'), '')}.jpg';
    final formData = FormData.fromMap({
      'file': MultipartFile.fromBytes(
        processedBytes,
        filename: uploadFilename,
        contentType: DioMediaType('image', 'jpeg'),
      ),
      if (initialCategory != null) 'initial_category': initialCategory,
    });

    final response = await _apiClient.dio.post(
      ApiConstants.wardrobeUpload,
      data: formData,
    );

    return WardrobeUploadResult.fromJson(response.data);
  }

  /// Polls processing status of background job
  Future<WardrobeStatusResult> pollStatus(String itemId) async {
    final response = await _apiClient.dio.get(
      '${ApiConstants.wardrobeItems}/$itemId/status',
    );
    return WardrobeStatusResult.fromJson(response.data);
  }

  /// List user's wardrobe items with category / favorite filters
  Future<List<WardrobeItemModel>> getItems({
    String? category,
    String? season,
    bool? isFavorite,
    String? search,
  }) async {
    final queryParams = <String, dynamic>{};
    if (category != null && category != 'all')
      queryParams['category'] = category;
    if (season != null) queryParams['season'] = season;
    if (isFavorite != null) queryParams['is_favorite'] = isFavorite;
    if (search != null && search.isNotEmpty) queryParams['search'] = search;

    final response = await _apiClient.dio.get(
      ApiConstants.wardrobeItems,
      queryParameters: queryParams,
    );

    final list = response.data as List;
    return list.map((e) => WardrobeItemModel.fromJson(e)).toList();
  }

  /// Manually edit tags
  Future<WardrobeItemModel> updateItem(
      String itemId, Map<String, dynamic> updateData) async {
    final response = await _apiClient.dio.patch(
      '${ApiConstants.wardrobeItems}/$itemId',
      data: updateData,
    );
    return WardrobeItemModel.fromJson(response.data);
  }

  /// Logs the garments as worn today (wear_count + 1, last_worn_at = now)
  Future<void> markWorn(List<String> itemIds) async {
    await _apiClient.dio
        .post(ApiConstants.wardrobeWear, data: {'item_ids': itemIds});
  }

  /// Delete item
  Future<bool> deleteItem(String itemId) async {
    final response = await _apiClient.dio.delete(
      '${ApiConstants.wardrobeItems}/$itemId',
    );
    return response.statusCode == 200;
  }
}
