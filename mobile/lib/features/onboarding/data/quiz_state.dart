import '../../../core/constants/api_constants.dart';
import '../../../core/network/api_client.dart';

class QuizPreferencesModel {
  List<String> styleVibes;
  List<String> preferredColors;
  List<String> avoidedColors;
  List<String> primaryOccasions;
  String climateZone;
  String sizingPreference;

  QuizPreferencesModel({
    List<String>? styleVibes,
    List<String>? preferredColors,
    List<String>? avoidedColors,
    List<String>? primaryOccasions,
    this.climateZone = 'temperate',
    this.sizingPreference = 'regular',
  })  : styleVibes = styleVibes ?? [],
        preferredColors = preferredColors ?? [],
        avoidedColors = avoidedColors ?? [],
        primaryOccasions = primaryOccasions ?? [];

  Map<String, dynamic> toJson() {
    return {
      'style_vibes': styleVibes,
      'preferred_colors': preferredColors,
      'avoided_colors': avoidedColors,
      'primary_occasions': primaryOccasions,
      'climate_zone': climateZone,
      'sizing_preference': sizingPreference,
    };
  }

  Future<bool> submit() async {
    final client = ApiClient();
    final response = await client.dio.put(
      ApiConstants.usersPreferences,
      data: toJson(),
    );
    return response.statusCode == 200;
  }
}
