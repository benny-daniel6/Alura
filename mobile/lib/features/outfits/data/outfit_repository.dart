import 'dart:typed_data';
import 'package:dio/dio.dart';
import '../../../core/constants/api_constants.dart';
import '../../../core/network/api_client.dart';
import '../../wardrobe/data/wardrobe_repository.dart';

class CanvasItemModel {
  final String itemId;
  double x;
  double y;
  double scale;
  double rotation;
  int zIndex;

  CanvasItemModel({
    required this.itemId,
    this.x = 0.0,
    this.y = 0.0,
    this.scale = 1.0,
    this.rotation = 0.0,
    this.zIndex = 0,
  });

  Map<String, dynamic> toJson() {
    return {
      'item_id': itemId,
      'x': x,
      'y': y,
      'scale': scale,
      'rotation': rotation,
      'z_index': zIndex,
    };
  }

  factory CanvasItemModel.fromJson(Map<String, dynamic> json) {
    return CanvasItemModel(
      itemId: json['item_id'] ?? '',
      x: (json['x'] as num?)?.toDouble() ?? 0.0,
      y: (json['y'] as num?)?.toDouble() ?? 0.0,
      scale: (json['scale'] as num?)?.toDouble() ?? 1.0,
      rotation: (json['rotation'] as num?)?.toDouble() ?? 0.0,
      zIndex: json['z_index'] ?? 0,
    );
  }
}

class CanvasStateModel {
  List<CanvasItemModel> items;
  String backgroundColor;
  // Logical size the coordinates were authored at, so other screen sizes can rescale them
  double? canvasWidth;
  double? canvasHeight;

  CanvasStateModel({
    List<CanvasItemModel>? items,
    this.backgroundColor = '#141418',
    this.canvasWidth,
    this.canvasHeight,
  }) : items = items ?? [];

  Map<String, dynamic> toJson() {
    return {
      'items': items.map((e) => e.toJson()).toList(),
      'background_color': backgroundColor,
      if (canvasWidth != null) 'canvas_width': canvasWidth,
      if (canvasHeight != null) 'canvas_height': canvasHeight,
    };
  }

  factory CanvasStateModel.fromJson(Map<String, dynamic> json) {
    return CanvasStateModel(
      items: (json['items'] as List?)
              ?.map((e) => CanvasItemModel.fromJson(e))
              .toList() ??
          [],
      backgroundColor: json['background_color'] ?? '#141418',
      canvasWidth: (json['canvas_width'] as num?)?.toDouble(),
      canvasHeight: (json['canvas_height'] as num?)?.toDouble(),
    );
  }
}

class OutfitModel {
  final String id;
  final String userId;
  final String name;
  final String? description;
  final List<String> occasions;
  final String season;
  final CanvasStateModel canvasState;
  final String? previewImageUrl;
  final bool isFavorite;
  final bool isPublic;
  final int itemsCount;
  final List<WardrobeItemModel> items;
  final DateTime createdAt;

  OutfitModel({
    required this.id,
    required this.userId,
    required this.name,
    this.description,
    required this.occasions,
    required this.season,
    required this.canvasState,
    this.previewImageUrl,
    required this.isFavorite,
    required this.isPublic,
    required this.itemsCount,
    required this.items,
    required this.createdAt,
  });

  factory OutfitModel.fromJson(Map<String, dynamic> json) {
    return OutfitModel(
      id: json['id'] ?? '',
      userId: json['user_id'] ?? '',
      name: json['name'] ?? 'Untitled Outfit',
      description: json['description'],
      occasions: List<String>.from(json['occasions'] ?? []),
      season: json['season'] ?? 'all_season',
      canvasState: CanvasStateModel.fromJson(json['canvas_state'] ?? {}),
      previewImageUrl: json['preview_image_url'],
      isFavorite: json['is_favorite'] ?? false,
      isPublic: json['is_public'] ?? false,
      itemsCount: json['items_count'] ?? 0,
      items: (json['items'] as List?)
              ?.map((e) => WardrobeItemModel.fromJson(e))
              .toList() ??
          [],
      createdAt: DateTime.tryParse(json['created_at'] ?? '') ?? DateTime.now(),
    );
  }
}

class OutfitRepository {
  final ApiClient _apiClient = ApiClient();

  Future<OutfitModel> createOutfit({
    required String name,
    String? description,
    required List<String> occasions,
    required String season,
    required CanvasStateModel canvasState,
    String? previewImageUrl,
    bool isFavorite = false,
  }) async {
    final response = await _apiClient.dio.post(
      ApiConstants.outfits,
      data: {
        'name': name,
        if (description != null) 'description': description,
        'occasions': occasions,
        'season': season,
        'canvas_state': canvasState.toJson(),
        if (previewImageUrl != null) 'preview_image_url': previewImageUrl,
        'is_favorite': isFavorite,
      },
    );
    return OutfitModel.fromJson(response.data);
  }

  Future<List<OutfitModel>> getOutfits({
    String? occasion,
    String? season,
    bool? isFavorite,
  }) async {
    final queryParams = <String, dynamic>{};
    if (occasion != null) queryParams['occasion'] = occasion;
    if (season != null) queryParams['season'] = season;
    if (isFavorite != null) queryParams['is_favorite'] = isFavorite;

    final response = await _apiClient.dio.get(
      ApiConstants.outfits,
      queryParameters: queryParams,
    );
    final list = response.data as List;
    return list.map((e) => OutfitModel.fromJson(e)).toList();
  }

  Future<OutfitModel> getOutfit(String outfitId) async {
    final response =
        await _apiClient.dio.get('${ApiConstants.outfits}/$outfitId');
    return OutfitModel.fromJson(response.data);
  }

  Future<OutfitModel> updateOutfit(
      String outfitId, Map<String, dynamic> data) async {
    final response = await _apiClient.dio
        .patch('${ApiConstants.outfits}/$outfitId', data: data);
    return OutfitModel.fromJson(response.data);
  }

  Future<bool> deleteOutfit(String outfitId) async {
    final response =
        await _apiClient.dio.delete('${ApiConstants.outfits}/$outfitId');
    return response.statusCode == 200;
  }

  /// Uploads the PNG snapshot rendered from the canvas RepaintBoundary.
  Future<OutfitModel> uploadPreview(String outfitId, Uint8List pngBytes) async {
    final response = await _apiClient.dio.post(
      '${ApiConstants.outfits}/$outfitId/preview',
      data: FormData.fromMap({
        'file': MultipartFile.fromBytes(
          pngBytes,
          filename: 'preview.png',
          contentType: DioMediaType('image', 'png'),
        ),
      }),
    );
    return OutfitModel.fromJson(response.data);
  }
}
