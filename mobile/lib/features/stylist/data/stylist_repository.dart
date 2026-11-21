import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/constants/api_constants.dart';
import '../../../core/network/api_client.dart';
import '../../wardrobe/data/wardrobe_repository.dart';

class WeatherInfoModel {
  final String? locationName;
  final double temperatureC;
  final double apparentTemperatureC;
  final String condition;
  final bool isRainy;
  final bool isCold;
  final bool isHot;
  final bool isFallback;

  WeatherInfoModel({
    this.locationName,
    required this.temperatureC,
    required this.apparentTemperatureC,
    required this.condition,
    required this.isRainy,
    required this.isCold,
    required this.isHot,
    required this.isFallback,
  });

  factory WeatherInfoModel.fromJson(Map<String, dynamic> json) =>
      WeatherInfoModel(
        locationName: json['location_name'],
        temperatureC: (json['temperature_c'] as num?)?.toDouble() ?? 20,
        apparentTemperatureC:
            (json['apparent_temperature_c'] as num?)?.toDouble() ?? 20,
        condition: json['condition'] ?? '',
        isRainy: json['is_rainy'] ?? false,
        isCold: json['is_cold'] ?? false,
        isHot: json['is_hot'] ?? false,
        isFallback: json['is_fallback'] ?? false,
      );
}

class SuggestedOutfitModel {
  final String name;
  final List<WardrobeItemModel> items;
  final String occasion;
  final String rationale;
  final List<String> stylingTips;
  final bool isComplete;
  final List<String> missingCategories;
  final List<String> missingPieces;

  SuggestedOutfitModel({
    required this.name,
    required this.items,
    required this.occasion,
    required this.rationale,
    required this.stylingTips,
    required this.isComplete,
    required this.missingCategories,
    required this.missingPieces,
  });

  factory SuggestedOutfitModel.fromJson(Map<String, dynamic> json) =>
      SuggestedOutfitModel(
        name: json['name'] ?? 'Curated Look',
        items: (json['items'] as List? ?? [])
            .map((e) => WardrobeItemModel.fromJson(e))
            .toList(),
        occasion: json['occasion'] ?? 'casual_daily',
        rationale: json['rationale'] ?? '',
        stylingTips: List<String>.from(json['styling_tips'] ?? []),
        isComplete: json['is_complete'] ?? true,
        missingCategories: List<String>.from(json['missing_categories'] ?? []),
        missingPieces: List<String>.from(json['missing_pieces'] ?? []),
      );
}

class StylistResultModel {
  final List<SuggestedOutfitModel> outfits;
  final WeatherInfoModel weather;
  final String engine;
  final int totalWardrobeItems;

  StylistResultModel({
    required this.outfits,
    required this.weather,
    required this.engine,
    required this.totalWardrobeItems,
  });

  factory StylistResultModel.fromJson(Map<String, dynamic> json) =>
      StylistResultModel(
        outfits: (json['outfits'] as List? ?? [])
            .map((e) => SuggestedOutfitModel.fromJson(e))
            .toList(),
        weather: WeatherInfoModel.fromJson(json['weather'] ?? const {}),
        engine: json['engine'] ?? 'rule_engine',
        totalWardrobeItems: json['total_wardrobe_items'] ?? 0,
      );
}

class StylistRepository {
  final ApiClient _apiClient = ApiClient();
  static const _cityKey = 'aura_stylist_city';

  Future<String?> getSavedCity() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_cityKey);
  }

  Future<void> saveCity(String city) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_cityKey, city.trim());
  }

  Future<WeatherInfoModel> getWeather({String? city}) async {
    final response = await _apiClient.dio.get(
      ApiConstants.stylistWeather,
      queryParameters: {if (city != null && city.isNotEmpty) 'city': city},
    );
    return WeatherInfoModel.fromJson(response.data);
  }

  Future<StylistResultModel> suggest({
    required String occasion,
    String? prompt,
    String? city,
    List<String> anchorItemIds = const [],
    int numOutfits = 3,
  }) async {
    final response = await _apiClient.dio.post(
      ApiConstants.stylistSuggest,
      data: {
        'occasion': occasion,
        if (prompt != null && prompt.trim().isNotEmpty) 'prompt': prompt.trim(),
        if (city != null && city.isNotEmpty) 'city': city,
        'anchor_item_ids': anchorItemIds,
        'num_outfits': numOutfits,
      },
      // LLM styling can take longer than the default receive timeout
      options: Options(receiveTimeout: const Duration(seconds: 90)),
    );
    return StylistResultModel.fromJson(response.data);
  }

  /// Ready-made looks for every occasion (rule engine on the server, so it is fast and free).
  Future<LookbookModel> getLookbook({String? city, int perOccasion = 2}) async {
    final response = await _apiClient.dio.get(
      ApiConstants.stylistLookbook,
      queryParameters: {
        if (city != null && city.isNotEmpty) 'city': city,
        'per_occasion': perOccasion,
      },
    );
    return LookbookModel.fromJson(response.data);
  }
}

class LookbookSectionModel {
  final String occasion;
  final List<SuggestedOutfitModel> outfits;

  LookbookSectionModel({required this.occasion, required this.outfits});

  factory LookbookSectionModel.fromJson(Map<String, dynamic> json) =>
      LookbookSectionModel(
        occasion: json['occasion'] ?? 'casual_daily',
        outfits: (json['outfits'] as List? ?? [])
            .map((e) => SuggestedOutfitModel.fromJson(e))
            .toList(),
      );
}

class LookbookModel {
  final List<LookbookSectionModel> sections;
  final WeatherInfoModel weather;

  LookbookModel({required this.sections, required this.weather});

  factory LookbookModel.fromJson(Map<String, dynamic> json) => LookbookModel(
        sections: (json['sections'] as List? ?? [])
            .map((e) => LookbookSectionModel.fromJson(e))
            .toList(),
        weather: WeatherInfoModel.fromJson(json['weather'] ?? const {}),
      );
}
