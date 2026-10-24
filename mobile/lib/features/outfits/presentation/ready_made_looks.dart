import '../../../core/utils/labels.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_theme.dart';
import '../../stylist/data/stylist_repository.dart';
import '../../stylist/presentation/stylist_screen.dart'
    show describeApiError, stylistOccasions;
import '../../wardrobe/data/wardrobe_repository.dart';
import '../data/outfit_repository.dart';
import '../domain/outfit_layout.dart';
import 'outfit_canvas_screen.dart';
import 'outfit_collage.dart';

/// Outfits tab: looks generated from the user's wardrobe for every occasion, ready to save or wear.
class ReadyMadeLooks extends StatefulWidget {
  /// Called after a look is saved so the saved list below can refresh.
  final VoidCallback onSaved;

  const ReadyMadeLooks({super.key, required this.onSaved});

  @override
  State<ReadyMadeLooks> createState() => _ReadyMadeLooksState();
}

class _ReadyMadeLooksState extends State<ReadyMadeLooks> {
  final StylistRepository _stylistRepo = StylistRepository();
  final OutfitRepository _outfitRepo = OutfitRepository();
  final WardrobeRepository _wardrobeRepo = WardrobeRepository();

  LookbookModel? _lookbook;
  bool _loading = true;
  String? _error;
  final Set<String> _saved = {};

  static final Map<String, String> _occasionLabels = {
    for (final o in stylistOccasions) o['id']!: o['label']!,
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final city = await _stylistRepo.getSavedCity();
      final lookbook = await _stylistRepo.getLookbook(city: city);
      if (mounted) setState(() => _lookbook = lookbook);
    } catch (e) {
      if (mounted) setState(() => _error = describeApiError(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _key(SuggestedOutfitModel look) =>
      (look.items.map((g) => g.id).toList()..sort()).join(',');

  Future<void> _save(SuggestedOutfitModel look) async {
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
      setState(() => _saved.add(_key(look)));
      widget.onSaved();
      _snack('Saved to your lookbook');
    } catch (e) {
      _snack('Could not save: ${describeApiError(e)}', error: true);
    }
  }

  Future<void> _wear(SuggestedOutfitModel look) async {
    try {
      await _wardrobeRepo.markWorn(look.items.map((g) => g.id).toList());
      _snack('Logged as worn today');
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

  void _openLook(SuggestedOutfitModel look) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AuraColors.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) {
        final theme = Theme.of(ctx);
        final saved = _saved.contains(_key(look));
        return DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.85,
          maxChildSize: 0.95,
          builder: (ctx, controller) => ListView(
            controller: controller,
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: SizedBox(
                    height: 340, child: OutfitCollage.arranged(look.items)),
              ),
              const SizedBox(height: 16),
              Text(look.name, style: theme.textTheme.titleLarge),
              const SizedBox(height: 6),
              Text(look.rationale, style: theme.textTheme.bodyMedium),
              ...look.stylingTips.map((tip) => Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.auto_awesome,
                            size: 14, color: AuraColors.champagne),
                        const SizedBox(width: 8),
                        Expanded(
                            child:
                                Text(tip, style: theme.textTheme.bodyMedium)),
                      ],
                    ),
                  )),
              const SizedBox(height: 12),
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
              const SizedBox(height: 18),
              ElevatedButton.icon(
                onPressed: saved
                    ? null
                    : () {
                        Navigator.of(ctx).pop();
                        _save(look);
                      },
                icon: Icon(saved ? Icons.bookmark : Icons.bookmark_border),
                label: Text(saved ? 'Saved' : 'Save to Lookbook'),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () {
                        Navigator.of(ctx).pop();
                        Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => OutfitCanvasScreen(
                            onSaved: widget.onSaved,
                            initialGarments: look.items,
                            initialName: look.name,
                          ),
                        ));
                      },
                      icon: const Icon(Icons.layers_outlined),
                      label: const Text('Edit in Studio'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () {
                        Navigator.of(ctx).pop();
                        _wear(look);
                      },
                      icon: const Icon(Icons.check_circle_outline),
                      label: const Text('Wear Today'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final w = _lookbook?.weather;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 4, 12, 0),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Ready-made for you',
                        style: theme.textTheme.titleLarge),
                    Text(
                      w != null && !w.isFallback
                          ? 'From your closet · ${w.temperatureC.round()}° ${w.condition.toLowerCase()}'
                          : 'Styled from your closet',
                      style: theme.textTheme.bodyMedium?.copyWith(fontSize: 12),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'New looks',
                onPressed: _loading ? null : _load,
                icon: Icon(Icons.refresh, color: AuraColors.textSecondary),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        if (_loading)
          SizedBox(
            height: 220,
            child: Center(
                child: CircularProgressIndicator(
                    color: AuraColors.accentIris, strokeWidth: 2)),
          )
        else if (_error != null)
          _message(
              theme,
              _error!.contains('No completed wardrobe items')
                  ? 'Add a few garments to your wardrobe and Alura will put outfits together for you.'
                  : _error!)
        else if (_lookbook == null || _lookbook!.sections.isEmpty)
          _message(theme,
              'Not enough pieces for a full outfit yet. Add at least one top and one bottom (or a dress).')
        else
          ..._lookbook!.sections
              .map((section) => _buildSection(theme, section)),
      ],
    );
  }

  Widget _message(ThemeData theme, String text) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AuraColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AuraColors.border),
      ),
      child: Text(text, style: theme.textTheme.bodyMedium),
    );
  }

  Widget _buildSection(ThemeData theme, LookbookSectionModel section) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 10, 24, 8),
          child: Text(
            (_occasionLabels[section.occasion] ?? tagLabel(section.occasion))
                .toUpperCase(),
            style: theme.textTheme.labelMedium?.copyWith(
                color: AuraColors.champagneLight, letterSpacing: 1.4),
          ),
        ),
        SizedBox(
          height: 250,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 20),
            itemCount: section.outfits.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (ctx, i) => _buildCard(theme, section.outfits[i]),
          ),
        ),
      ],
    );
  }

  Widget _buildCard(ThemeData theme, SuggestedOutfitModel look) {
    final saved = _saved.contains(_key(look));
    return SizedBox(
      width: 160,
      child: Material(
        color: AuraColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: AuraColors.border),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => _openLook(look),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: OutfitCollage.arranged(look.items)),
              Padding(
                padding: const EdgeInsets.fromLTRB(10, 8, 6, 8),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(look.name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.titleMedium
                                  ?.copyWith(fontSize: 13)),
                          Text('${look.items.length} pieces',
                              style: theme.textTheme.bodyMedium
                                  ?.copyWith(fontSize: 11)),
                        ],
                      ),
                    ),
                    if (saved)
                      Icon(Icons.bookmark,
                          size: 16, color: AuraColors.champagne),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
