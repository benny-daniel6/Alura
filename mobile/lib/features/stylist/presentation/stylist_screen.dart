import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:smooth_page_indicator/smooth_page_indicator.dart';

import '../../../core/theme/app_theme.dart';
import '../../outfits/data/outfit_repository.dart';
import '../../outfits/domain/outfit_layout.dart';
import '../../outfits/presentation/outfit_canvas_screen.dart';
import '../../outfits/presentation/outfit_collage.dart';
import '../../wardrobe/data/wardrobe_repository.dart';
import '../../wardrobe/presentation/garment_image.dart';
import '../data/stylist_repository.dart';

const stylistOccasions = [
  {'id': 'casual_daily', 'label': 'Casual'},
  {'id': 'office_work', 'label': 'Work'},
  {'id': 'evening_dinner', 'label': 'Dinner'},
  {'id': 'nightlife', 'label': 'Night Out'},
  {'id': 'formal_events', 'label': 'Formal'},
  {'id': 'athleisure', 'label': 'Athleisure'},
];

String describeApiError(Object e) {
  if (e is DioException) {
    if (e.type == DioExceptionType.connectionError ||
        e.type == DioExceptionType.connectionTimeout) {
      return 'Cannot reach the Alura server. Check your connection, or the server address (server icon at the top).';
    }
    if (e.type == DioExceptionType.receiveTimeout) {
      return 'The stylist took too long to answer. Please try again.';
    }
    final data = e.response?.data;
    if (data is Map && data['detail'] is String) return data['detail'];
  }
  return e.toString().replaceAll('Exception: ', '');
}

class StylistScreen extends StatefulWidget {
  /// Garments every suggestion must include ("Style this piece").
  final List<WardrobeItemModel> anchorItems;

  /// True when pushed as its own page (shows an app bar) rather than shown as a tab.
  final bool standalone;

  const StylistScreen(
      {super.key, this.anchorItems = const [], this.standalone = false});

  @override
  State<StylistScreen> createState() => _StylistScreenState();
}

class _StylistScreenState extends State<StylistScreen> {
  final StylistRepository _repo = StylistRepository();
  final OutfitRepository _outfitRepo = OutfitRepository();
  final WardrobeRepository _wardrobeRepo = WardrobeRepository();
  final TextEditingController _promptController = TextEditingController();
  final PageController _pageController = PageController(viewportFraction: 0.92);

  String _occasion = 'casual_daily';
  String? _city;
  WeatherInfoModel? _weather;
  bool _loadingWeather = false;

  bool _isStyling = false;
  String? _error;
  StylistResultModel? _result;
  final Set<int> _savedLooks = {};

  @override
  void initState() {
    super.initState();
    _initCity();
  }

  @override
  void dispose() {
    _promptController.dispose();
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _initCity() async {
    final city = await _repo.getSavedCity();
    if (!mounted) return;
    setState(() => _city = city);
    if (city != null && city.isNotEmpty) _loadWeather();
  }

  Future<void> _loadWeather() async {
    setState(() => _loadingWeather = true);
    try {
      final weather = await _repo.getWeather(city: _city);
      if (mounted) setState(() => _weather = weather);
    } catch (e) {
      if (mounted) _snack(describeApiError(e), error: true);
    } finally {
      if (mounted) setState(() => _loadingWeather = false);
    }
  }

  Future<void> _editCity() async {
    final controller = TextEditingController(text: _city ?? '');
    final city = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AuraColors.surface,
        title: const Text('Your city'),
        content: TextField(
          controller: controller,
          autofocus: true,
          textCapitalization: TextCapitalization.words,
          style: TextStyle(color: AuraColors.textPrimary),
          decoration:
              const InputDecoration(labelText: 'City', hintText: 'e.g. Mumbai'),
          onSubmitted: (v) => Navigator.of(ctx).pop(v),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(controller.text),
              child: const Text('Save')),
        ],
      ),
    );
    if (city == null || city.trim().isEmpty) return;
    final previous = _city;
    setState(() => _city = city.trim());
    try {
      final weather = await _repo.getWeather(city: _city);
      await _repo.saveCity(_city!);
      if (mounted) setState(() => _weather = weather);
    } catch (e) {
      if (!mounted) return;
      setState(() => _city = previous);
      _snack(describeApiError(e), error: true);
    }
  }

  Future<void> _styleMe() async {
    HapticFeedback.lightImpact();
    FocusScope.of(context).unfocus();
    setState(() {
      _isStyling = true;
      _error = null;
    });
    try {
      final result = await _repo.suggest(
        occasion: _occasion,
        prompt: _promptController.text,
        city: _city,
        anchorItemIds: widget.anchorItems.map((g) => g.id).toList(),
      );
      if (!mounted) return;
      setState(() {
        _result = result;
        _weather = result.weather.isFallback && _weather != null
            ? _weather
            : result.weather;
        _savedLooks.clear();
      });
      if (_pageController.hasClients) _pageController.jumpToPage(0);
    } catch (e) {
      if (mounted) setState(() => _error = describeApiError(e));
    } finally {
      if (mounted) setState(() => _isStyling = false);
    }
  }

  Future<void> _saveLook(int index, SuggestedOutfitModel look) async {
    try {
      await _outfitRepo.createOutfit(
        name: look.name,
        description: look.rationale.length > 500
            ? look.rationale.substring(0, 500)
            : look.rationale,
        occasions: [look.occasion],
        season: 'all_season',
        canvasState: autoArrangeOutfit(look.items, collageReferenceSize),
      );
      if (!mounted) return;
      HapticFeedback.mediumImpact();
      setState(() => _savedLooks.add(index));
      _snack('Saved to your Lookbook');
    } catch (e) {
      _snack('Could not save: ${describeApiError(e)}', error: true);
    }
  }

  void _openInStudio(SuggestedOutfitModel look) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => OutfitCanvasScreen(
          onSaved: () {}, initialGarments: look.items, initialName: look.name),
    ));
  }

  Future<void> _wearToday(SuggestedOutfitModel look) async {
    try {
      await _wardrobeRepo.markWorn(look.items.map((g) => g.id).toList());
      _snack('Logged as worn today. Your stylist will rotate these pieces.');
    } catch (e) {
      _snack('Could not log: ${describeApiError(e)}', error: true);
    }
  }

  void _snack(String message, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text(message),
          backgroundColor: error ? AuraColors.error : AuraColors.success),
    );
  }

  // ---------------- Build ----------------

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final body = ListView(
      padding: const EdgeInsets.fromLTRB(0, 16, 0, 32),
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (!widget.standalone) ...[
                Text('AI Stylist',
                    style:
                        theme.textTheme.displayMedium?.copyWith(fontSize: 24)),
                Text('Looks from your own closet, for today',
                    style: theme.textTheme.bodyMedium),
                const SizedBox(height: 16),
              ],
              if (widget.anchorItems.isNotEmpty) ...[
                _buildAnchors(theme),
                const SizedBox(height: 14),
              ],
              _buildWeatherCard(theme),
              const SizedBox(height: 18),
              Text('Occasion',
                  style: theme.textTheme.titleMedium?.copyWith(fontSize: 14)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: stylistOccasions.map((occ) {
                  final selected = _occasion == occ['id'];
                  return ChoiceChip(
                    label: Text(occ['label']!),
                    selected: selected,
                    onSelected: (_) => setState(() => _occasion = occ['id']!),
                    selectedColor: AuraColors.accentIris.withOpacity(0.25),
                    backgroundColor: AuraColors.surface,
                    side: BorderSide(
                        color: selected
                            ? AuraColors.accentIris
                            : AuraColors.border),
                    labelStyle: TextStyle(
                      color: selected
                          ? AuraColors.textPrimary
                          : AuraColors.textSecondary,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                    ),
                  );
                }).toList(),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _promptController,
                maxLength: 300,
                minLines: 1,
                maxLines: 3,
                style: TextStyle(color: AuraColors.textPrimary),
                decoration: const InputDecoration(
                  labelText: 'Anything specific? (optional)',
                  hintText:
                      'e.g. brunch with friends, relaxed but put together',
                  prefixIcon: Icon(Icons.chat_bubble_outline, size: 20),
                ),
              ),
              const SizedBox(height: 6),
              ElevatedButton.icon(
                onPressed: _isStyling ? null : _styleMe,
                icon: _isStyling
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.auto_awesome),
                label: Text(_isStyling
                    ? 'Styling your looks…'
                    : (_result == null ? 'Style Me' : 'Restyle')),
              ),
              if (_error != null) ...[
                const SizedBox(height: 14),
                _buildErrorBox(theme, _error!),
              ],
            ],
          ),
        ),
        if (_result != null) ...[
          const SizedBox(height: 24),
          _buildResults(theme, _result!),
        ],
      ],
    );

    if (!widget.standalone) return SafeArea(child: body);
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        title: Text('Style This Piece', style: theme.textTheme.titleLarge),
      ),
      body: SafeArea(child: body),
    );
  }

  Widget _buildAnchors(ThemeData theme) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AuraColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AuraColors.accentIris.withOpacity(0.5)),
      ),
      child: Row(
        children: [
          ...widget.anchorItems.take(3).map((g) => Container(
                width: 48,
                height: 48,
                margin: const EdgeInsets.only(right: 10),
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                    color: AuraColors.surfaceLight,
                    borderRadius: BorderRadius.circular(10)),
                child: GarmentImage(garment: g, preferThumbnail: true),
              )),
          Expanded(
            child: Text(
              'Every look will include ${widget.anchorItems.map((g) => g.name ?? g.category).join(', ')}',
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: AuraColors.textPrimary),
            ),
          ),
        ],
      ),
    );
  }

  IconData _weatherIcon(WeatherInfoModel w) {
    final c = w.condition.toLowerCase();
    if (w.isRainy || c.contains('rain') || c.contains('drizzle'))
      return Icons.umbrella_outlined;
    if (c.contains('snow')) return Icons.ac_unit;
    if (c.contains('thunder')) return Icons.thunderstorm_outlined;
    if (c.contains('cloud') || c.contains('overcast') || c.contains('fog'))
      return Icons.cloud_outlined;
    return Icons.wb_sunny_outlined;
  }

  Widget _buildWeatherCard(ThemeData theme) {
    final w = _weather;
    final hasCity = _city != null && _city!.isNotEmpty;
    final String title;
    final String subtitle;
    if (_loadingWeather) {
      title = 'Checking the weather…';
      subtitle = _city ?? '';
    } else if (w != null && !w.isFallback) {
      title = '${w.temperatureC.round()}° · ${w.condition}';
      subtitle =
          '${w.locationName ?? _city} · feels like ${w.apparentTemperatureC.round()}°';
    } else {
      title = hasCity ? 'Weather unavailable' : 'Add your city';
      subtitle = hasCity
          ? 'Tap to change $_city'
          : 'For weather-aware outfit suggestions';
    }
    return InkWell(
      onTap: _editCity,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: AuraColors.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AuraColors.border),
        ),
        child: Row(
          children: [
            Icon(
              w != null && !w.isFallback
                  ? _weatherIcon(w)
                  : Icons.location_on_outlined,
              color: AuraColors.champagne,
              size: 26,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style:
                          theme.textTheme.titleMedium?.copyWith(fontSize: 15)),
                  if (subtitle.isNotEmpty)
                    Text(subtitle,
                        style:
                            theme.textTheme.bodyMedium?.copyWith(fontSize: 12)),
                ],
              ),
            ),
            Icon(Icons.edit_location_alt_outlined,
                color: AuraColors.textTertiary, size: 20),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorBox(ThemeData theme, String message) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AuraColors.error.withOpacity(0.12),
        border: Border.all(color: AuraColors.error.withOpacity(0.4)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(message,
          style: theme.textTheme.bodyMedium?.copyWith(color: AuraColors.error)),
    );
  }

  Widget _buildResults(ThemeData theme, StylistResultModel result) {
    if (result.outfits.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: _buildErrorBox(theme,
            'No looks could be built from your closet yet. Add a few more garments.'),
      );
    }
    final engineLabel = switch (result.engine) {
      'gemini' => 'Styled by Gemini',
      'openai' => 'Styled by AI',
      _ => 'Styled by Alura rules (add a Gemini key for AI styling)',
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Row(
            children: [
              Text('${result.outfits.length} looks for you',
                  style: theme.textTheme.titleLarge),
              const Spacer(),
              SmoothPageIndicator(
                controller: _pageController,
                count: result.outfits.length,
                effect: WormEffect(
                  dotHeight: 7,
                  dotWidth: 7,
                  activeDotColor: AuraColors.accentIris,
                  dotColor: AuraColors.border,
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 2, 24, 10),
          child: Text(engineLabel,
              style: theme.textTheme.bodyMedium?.copyWith(fontSize: 11)),
        ),
        SizedBox(
          height: 640,
          child: PageView.builder(
            controller: _pageController,
            itemCount: result.outfits.length,
            itemBuilder: (ctx, i) =>
                _buildLookCard(theme, i, result.outfits[i]),
          ),
        ),
      ],
    );
  }

  Widget _buildLookCard(ThemeData theme, int index, SuggestedOutfitModel look) {
    final saved = _savedLooks.contains(index);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6),
      child: Container(
        decoration: BoxDecoration(
          color: AuraColors.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AuraColors.border),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(height: 300, child: OutfitCollage.arranged(look.items)),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(look.name,
                        style:
                            theme.textTheme.titleLarge?.copyWith(fontSize: 19)),
                    const SizedBox(height: 6),
                    Text(look.rationale, style: theme.textTheme.bodyMedium),
                    if (look.stylingTips.isNotEmpty) ...[
                      const SizedBox(height: 10),
                      ...look.stylingTips.map((tip) => Padding(
                            padding: const EdgeInsets.only(bottom: 4),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Icon(Icons.auto_awesome,
                                    size: 14, color: AuraColors.champagne),
                                const SizedBox(width: 8),
                                Expanded(
                                    child: Text(tip,
                                        style: theme.textTheme.bodyMedium
                                            ?.copyWith(fontSize: 13))),
                              ],
                            ),
                          )),
                    ],
                    if (!look.isComplete || look.missingPieces.isNotEmpty) ...[
                      const SizedBox(height: 10),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: AuraColors.champagne.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                              color: AuraColors.champagne.withOpacity(0.35)),
                        ),
                        child: Text(
                          look.missingPieces.isNotEmpty
                              ? 'To complete this look, add: ${look.missingPieces.join('; ')}'
                              : 'This look still needs: ${look.missingCategories.join(', ')}',
                          style: theme.textTheme.bodyMedium?.copyWith(
                              fontSize: 12, color: AuraColors.champagneLight),
                        ),
                      ),
                    ],
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: look.items
                          .map((g) => Chip(
                                visualDensity: VisualDensity.compact,
                                backgroundColor: AuraColors.surfaceLight,
                                side: BorderSide(color: AuraColors.border),
                                label: Text(g.name ?? g.category,
                                    style: const TextStyle(fontSize: 11)),
                              ))
                          .toList(),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
              child: Row(
                children: [
                  Expanded(
                    child: _actionButton(
                      icon: saved ? Icons.bookmark : Icons.bookmark_border,
                      label: saved ? 'Saved' : 'Save',
                      onPressed: saved ? null : () => _saveLook(index, look),
                      primary: true,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _actionButton(
                      icon: Icons.layers_outlined,
                      label: 'Studio',
                      onPressed: () => _openInStudio(look),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _actionButton(
                      icon: Icons.check_circle_outline,
                      label: 'Wear',
                      onPressed: () => _wearToday(look),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _actionButton({
    required IconData icon,
    required String label,
    required VoidCallback? onPressed,
    bool primary = false,
  }) {
    return ElevatedButton.icon(
      style: ElevatedButton.styleFrom(
        minimumSize: const Size(0, 46),
        padding: const EdgeInsets.symmetric(horizontal: 8),
        backgroundColor:
            primary ? AuraColors.accentIris : AuraColors.surfaceLight,
        foregroundColor: primary ? Colors.white : AuraColors.textPrimary,
        side: primary ? null : BorderSide(color: AuraColors.border),
      ),
      onPressed: onPressed,
      icon: Icon(icon, size: 18),
      label: Text(label, style: const TextStyle(fontSize: 13)),
    );
  }
}
