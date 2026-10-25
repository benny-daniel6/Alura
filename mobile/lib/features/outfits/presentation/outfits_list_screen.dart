import '../../../core/utils/labels.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import '../../../core/constants/api_constants.dart';
import '../../../core/theme/app_theme.dart';
import '../../wardrobe/data/wardrobe_repository.dart';
import '../../wardrobe/presentation/garment_image.dart';
import '../data/outfit_repository.dart';
import 'outfit_canvas_screen.dart';
import 'outfit_collage.dart';
import 'ready_made_looks.dart';

class OutfitsListScreen extends StatefulWidget {
  const OutfitsListScreen({super.key});

  @override
  State<OutfitsListScreen> createState() => _OutfitsListScreenState();
}

class _OutfitsListScreenState extends State<OutfitsListScreen> {
  final OutfitRepository _repo = OutfitRepository();
  final WardrobeRepository _wardrobeRepo = WardrobeRepository();
  List<OutfitModel> _outfits = [];
  bool _isLoading = true;
  String _selectedOccasion = 'all';
  int _readyMadeGeneration = 0;

  final List<Map<String, String>> _occasions = [
    {'id': 'all', 'label': 'All Looks'},
    {'id': 'office_work', 'label': 'Work'},
    {'id': 'casual_daily', 'label': 'Casual Daily'},
    {'id': 'evening_dinner', 'label': 'Evening'},
    {'id': 'nightlife', 'label': 'Nightlife'},
    {'id': 'formal_events', 'label': 'Formal'},
    {'id': 'athleisure', 'label': 'Athleisure'},
  ];

  @override
  void initState() {
    super.initState();
    _loadOutfits();
  }

  Future<void> _loadOutfits() async {
    setState(() => _isLoading = true);
    try {
      final list = await _repo.getOutfits(
        occasion: _selectedOccasion == 'all' ? null : _selectedOccasion,
      );
      if (mounted) setState(() => _outfits = list);
    } catch (e) {
      _snack('Could not load outfits: $e');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _openCanvas({OutfitModel? existing}) {
    Navigator.of(context).push(
      MaterialPageRoute(
          builder: (_) =>
              OutfitCanvasScreen(onSaved: _loadOutfits, existing: existing)),
    );
  }

  Future<void> _toggleFavorite(OutfitModel outfit) async {
    try {
      await _repo.updateOutfit(outfit.id, {'is_favorite': !outfit.isFavorite});
      await _loadOutfits();
    } catch (e) {
      _snack('Could not update favourite: $e');
    }
  }

  Future<void> _confirmDelete(OutfitModel outfit) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AuraColors.surface,
        title: const Text('Delete outfit?'),
        content: Text(
            '"${outfit.name}" will be removed from your lookbook. Garments stay in your closet.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text('Delete', style: TextStyle(color: AuraColors.error)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _repo.deleteOutfit(outfit.id);
      await _loadOutfits();
    } catch (e) {
      _snack('Could not delete outfit: $e');
    }
  }

  Future<void> _wearToday(OutfitModel outfit) async {
    try {
      await _wardrobeRepo.markWorn(outfit.items.map((g) => g.id).toList());
      _snack('"${outfit.name}" logged as worn today.', error: false);
    } catch (e) {
      _snack('Could not log outfit: $e');
    }
  }

  void _snack(String message, {bool error = true}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text(message),
          backgroundColor: error ? AuraColors.error : AuraColors.success),
    );
  }

  double _previewAspect(OutfitModel outfit) {
    final w = outfit.canvasState.canvasWidth;
    final h = outfit.canvasState.canvasHeight;
    return (w != null && h != null && h > 0) ? w / h : 0.75;
  }

  void _openDetail(OutfitModel outfit) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AuraColors.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) {
        final theme = Theme.of(ctx);
        final preview = ApiConstants.mediaUrl(outfit.previewImageUrl);
        return DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.85,
          maxChildSize: 0.95,
          builder: (ctx, scrollController) => ListView(
            controller: scrollController,
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: AspectRatio(
                  aspectRatio: preview != null ? _previewAspect(outfit) : 2 / 3,
                  child: preview != null
                      ? CachedNetworkImage(
                          imageUrl: preview,
                          cacheKey: ApiConstants.mediaCacheKey(preview),
                          fit: BoxFit.cover)
                      : OutfitCollage.forOutfit(outfit),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                      child:
                          Text(outfit.name, style: theme.textTheme.titleLarge)),
                  IconButton(
                    tooltip: outfit.isFavorite ? 'Unfavourite' : 'Favourite',
                    icon: Icon(
                        outfit.isFavorite
                            ? Icons.favorite
                            : Icons.favorite_border,
                        color: AuraColors.champagne),
                    onPressed: () {
                      Navigator.of(ctx).pop();
                      _toggleFavorite(outfit);
                    },
                  ),
                ],
              ),
              if (outfit.description != null && outfit.description!.isNotEmpty)
                Text(outfit.description!, style: theme.textTheme.bodyMedium),
              const SizedBox(height: 10),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  _buildChip(tagLabel(outfit.season).toUpperCase(),
                      color: AuraColors.champagneLight),
                  ...outfit.occasions
                      .map((o) => _buildChip(tagLabel(o).toUpperCase())),
                ],
              ),
              const SizedBox(height: 20),
              Text('${outfit.items.length} pieces',
                  style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              // Item breakdown, front-most layer first
              ...outfit.items.reversed.map((g) => Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: AuraColors.surfaceLight,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AuraColors.border),
                    ),
                    child: Row(
                      children: [
                        SizedBox(
                            width: 52,
                            height: 52,
                            child: GarmentImage(
                                garment: g, preferThumbnail: true)),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(g.name ?? g.category,
                                  style: theme.textTheme.titleMedium
                                      ?.copyWith(fontSize: 14)),
                              Text(
                                [tagLabel(g.category), g.primaryColor, g.brand]
                                    .whereType<String>()
                                    .where((s) => s.isNotEmpty)
                                    .join(' · '),
                                style: theme.textTheme.bodyMedium
                                    ?.copyWith(fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  )),
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: () {
                  Navigator.of(ctx).pop();
                  _wearToday(outfit);
                },
                icon: const Icon(Icons.check_circle_outline),
                label: const Text('Wear Today'),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  TextButton.icon(
                    onPressed: () {
                      Navigator.of(ctx).pop();
                      _confirmDelete(outfit);
                    },
                    icon: Icon(Icons.delete_outline, color: AuraColors.error),
                    label: Text('Delete',
                        style: TextStyle(color: AuraColors.error)),
                  ),
                  const Spacer(),
                  ElevatedButton.icon(
                    // Theme buttons are full-width (Size.fromHeight); a Row gives unbounded width
                    style: ElevatedButton.styleFrom(
                        minimumSize: const Size(0, 54)),
                    onPressed: () {
                      Navigator.of(ctx).pop();
                      _openCanvas(existing: outfit);
                    },
                    icon: const Icon(Icons.edit_outlined),
                    label: const Text('Edit on Canvas'),
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

    return Scaffold(
      backgroundColor: Colors.transparent, // shell paints the gradient
      body: SafeArea(
        child: RefreshIndicator(
          color: AuraColors.accentIris,
          onRefresh: () async {
            setState(() => _readyMadeGeneration++);
            await _loadOutfits();
          },
          child: ListView(
            padding: const EdgeInsets.only(bottom: 96),
            children: [
              // Header
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 16, 24, 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Lookbook Studio',
                        style: theme.textTheme.displayMedium
                            ?.copyWith(fontSize: 24)),
                  ],
                ),
              ),

              ReadyMadeLooks(
                  key: ValueKey('ready-$_readyMadeGeneration'),
                  onSaved: _loadOutfits),
              const SizedBox(height: 24),

              // Saved looks
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 0, 24, 8),
                child: Text('Your saved looks · ${_outfits.length}',
                    style: theme.textTheme.titleLarge),
              ),
              SizedBox(
                height: 42,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  itemCount: _occasions.length,
                  itemBuilder: (ctx, i) {
                    final occ = _occasions[i];
                    final isSelected = _selectedOccasion == occ['id'];
                    return Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: Text(occ['label']!),
                        selected: isSelected,
                        onSelected: (selected) {
                          if (selected) {
                            setState(() => _selectedOccasion = occ['id']!);
                            _loadOutfits();
                          }
                        },
                        selectedColor: AuraColors.accentIris.withOpacity(0.2),
                        backgroundColor: AuraColors.surface,
                        side: BorderSide(
                            color: isSelected
                                ? AuraColors.accentIris
                                : AuraColors.border),
                        labelStyle: TextStyle(
                          color: isSelected
                              ? AuraColors.textPrimary
                              : AuraColors.textSecondary,
                          fontSize: 13,
                          fontWeight:
                              isSelected ? FontWeight.w600 : FontWeight.w400,
                        ),
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 12),
              if (_isLoading)
                Padding(
                  padding: EdgeInsets.all(32),
                  child: Center(
                      child: CircularProgressIndicator(
                          color: AuraColors.accentIris, strokeWidth: 2)),
                )
              else if (_outfits.isEmpty)
                _buildEmptyState(theme)
              else
                ..._outfits.map((o) => Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 20),
                      child: _buildOutfitCard(theme, o),
                    )),
            ],
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _openCanvas(),
        backgroundColor: AuraColors.accentIris,
        icon: const Icon(Icons.palette_outlined),
        label: const Text('Create look'),
      ),
    );
  }

  Widget _buildOutfitCard(ThemeData theme, OutfitModel outfit) {
    final preview = ApiConstants.mediaUrl(outfit.previewImageUrl);
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Material(
        color: AuraColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: BorderSide(color: AuraColors.border),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => _openDetail(outfit),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Canvas snapshot if one was rendered on save, otherwise the garment cutouts
              if (preview != null)
                SizedBox(
                  height: 200,
                  width: double.infinity,
                  child: CachedNetworkImage(
                    imageUrl: preview,
                    cacheKey: ApiConstants.mediaCacheKey(preview),
                    fit: BoxFit.cover,
                    errorWidget: (_, __, ___) =>
                        ColoredBox(color: AuraColors.surfaceLight),
                  ),
                )
              else
                SizedBox(
                    height: 200,
                    width: double.infinity,
                    child: OutfitCollage.forOutfit(outfit)),
              // Info & Tags
              Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Expanded(
                          child: Text(outfit.name,
                              style: theme.textTheme.titleMedium
                                  ?.copyWith(fontSize: 16)),
                        ),
                        if (outfit.isFavorite)
                          Icon(Icons.favorite,
                              size: 18, color: AuraColors.champagne),
                      ],
                    ),
                    if (outfit.description != null &&
                        outfit.description!.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(outfit.description!,
                          style: theme.textTheme.bodyMedium),
                    ],
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        _buildChip(tagLabel(outfit.season).toUpperCase(),
                            color: AuraColors.champagneLight),
                        _buildChip('${outfit.itemsCount} PIECES'),
                        ...outfit.occasions
                            .map((o) => _buildChip(tagLabel(o).toUpperCase())),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildChip(String label, {Color? color}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AuraColors.surfaceLight,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AuraColors.border),
      ),
      child: Text(
        label,
        style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w600,
            color: color ?? AuraColors.textSecondary),
      ),
    );
  }

  Widget _buildEmptyState(ThemeData theme) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 20),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AuraColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AuraColors.border),
      ),
      child: Text(
        _selectedOccasion == 'all'
            ? 'Nothing saved yet. Save a ready-made look above, or design your own on the canvas.'
            : 'No saved looks for this occasion yet.',
        style: theme.textTheme.bodyMedium,
      ),
    );
  }
}
