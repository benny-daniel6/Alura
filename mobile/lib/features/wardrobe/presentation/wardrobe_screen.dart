import '../../../core/utils/labels.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../data/wardrobe_repository.dart';
import 'garment_image.dart';
import 'upload_flow_modal.dart';
import 'item_detail_dialog.dart';

class WardrobeScreen extends StatefulWidget {
  const WardrobeScreen({super.key});

  @override
  State<WardrobeScreen> createState() => _WardrobeScreenState();
}

class _WardrobeScreenState extends State<WardrobeScreen> {
  final WardrobeRepository _repo = WardrobeRepository();
  List<WardrobeItemModel> _items = [];
  bool _isLoading = true;
  String _selectedCategory = 'all';
  String _searchQuery = '';
  Timer? _searchDebounce;

  bool get _isFiltered => _searchQuery.isNotEmpty || _selectedCategory != 'all';

  final List<Map<String, String>> _categories = [
    {'id': 'all', 'label': 'All Items'},
    {'id': 'top', 'label': 'Tops'},
    {'id': 'bottom', 'label': 'Bottoms'},
    {'id': 'outerwear', 'label': 'Outerwear'},
    {'id': 'dress', 'label': 'Dresses'},
    {'id': 'one_piece', 'label': 'One-pieces'},
    {'id': 'footwear', 'label': 'Footwear'},
    {'id': 'bag', 'label': 'Bags'},
    {'id': 'accessory', 'label': 'Accessories'},
    {'id': 'headwear', 'label': 'Headwear'},
  ];

  @override
  void dispose() {
    _searchDebounce?.cancel();
    super.dispose();
  }

  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 350), () {
      if (!mounted || value.trim() == _searchQuery) return;
      setState(() => _searchQuery = value.trim());
      _loadItems();
    });
  }

  @override
  void initState() {
    super.initState();
    _loadItems();
  }

  Future<void> _loadItems() async {
    setState(() => _isLoading = true);
    try {
      final items = await _repo.getItems(
        category: _selectedCategory == 'all' ? null : _selectedCategory,
        search: _searchQuery.isEmpty ? null : _searchQuery,
      );
      setState(() => _items = items);
    } catch (_) {
      // Fallback empty list on connection error
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _openUploadModal() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => UploadFlowModal(onCompleted: _loadItems),
    );
  }

  void _openItemDetail(WardrobeItemModel item) {
    showDialog(
      context: context,
      builder: (_) => ItemDetailDialog(item: item, onUpdated: _loadItems),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Colors.transparent, // shell paints the gradient
      body: SafeArea(
        child: Column(
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 16, 24, 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Digital Closet',
                          style: theme.textTheme.displayMedium
                              ?.copyWith(fontSize: 24)),
                      Text(
                          _isFiltered
                              ? '${_items.length} shown'
                              : '${_items.length} / 150 garments',
                          style: theme.textTheme.bodyMedium),
                    ],
                  ),
                  IconButton(
                    onPressed: _openUploadModal,
                    icon: Icon(Icons.add_circle,
                        color: AuraColors.accentIris, size: 32),
                  ),
                ],
              ),
            ),

            // Search
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
              child: TextField(
                onChanged: _onSearchChanged,
                textInputAction: TextInputAction.search,
                style: TextStyle(color: AuraColors.textPrimary),
                decoration: InputDecoration(
                  isDense: true,
                  hintText: 'Search your closet',
                  prefixIcon:
                      Icon(Icons.search, color: AuraColors.textTertiary),
                  contentPadding: const EdgeInsets.symmetric(vertical: 12),
                ),
              ),
            ),

            // Category Filter Pills
            SizedBox(
              height: 42,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 20),
                itemCount: _categories.length,
                itemBuilder: (ctx, i) {
                  final cat = _categories[i];
                  final isSelected = _selectedCategory == cat['id'];
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(cat['label']!),
                      selected: isSelected,
                      onSelected: (selected) {
                        if (selected) {
                          setState(() => _selectedCategory = cat['id']!);
                          _loadItems();
                        }
                      },
                      selectedColor: AuraColors.accentIris.withOpacity(0.2),
                      backgroundColor: AuraColors.surface,
                      side: BorderSide(
                        color: isSelected
                            ? AuraColors.accentIris
                            : AuraColors.border,
                      ),
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

            // Wardrobe Grid Content
            Expanded(
              child: _isLoading
                  ? Center(
                      child: CircularProgressIndicator(
                          color: AuraColors.accentIris, strokeWidth: 2))
                  : _items.isEmpty
                      ? _buildEmptyState(theme)
                      : RefreshIndicator(
                          onRefresh: _loadItems,
                          color: AuraColors.accentIris,
                          child: GridView.builder(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 20, vertical: 8),
                            gridDelegate:
                                const SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: 2,
                              childAspectRatio: 0.76,
                              crossAxisSpacing: 14,
                              mainAxisSpacing: 14,
                            ),
                            itemCount: _items.length,
                            itemBuilder: (ctx, i) =>
                                _buildGarmentCard(theme, _items[i]),
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildGarmentCard(ThemeData theme, WardrobeItemModel item) {
    return InkWell(
      onTap: () => _openItemDetail(item),
      borderRadius: BorderRadius.circular(18),
      child: Container(
        decoration: BoxDecoration(
          color: AuraColors.surface,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: AuraColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Transparent Cutout Container
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  // Studio photos have a white background, like a shop listing
                  color: item.showcaseImageUrl != null
                      ? Colors.white
                      : AuraColors.surfaceLight,
                  borderRadius:
                      const BorderRadius.vertical(top: Radius.circular(18)),
                ),
                child: Center(
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      Positioned.fill(
                        child: Padding(
                          padding: const EdgeInsets.all(10),
                          child: GarmentImage(
                            garment: item,
                            preferThumbnail: true,
                            variant: item.showcaseImageUrl != null
                                ? GarmentImageVariant.showcase
                                : GarmentImageVariant.cutout,
                          ),
                        ),
                      ),
                      if (item.status == 'pending' ||
                          item.status == 'processing')
                        Positioned(
                          top: 8,
                          left: 8,
                          child: SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: AuraColors.accentIris),
                          ),
                        ),
                      if (item.status == 'failed')
                        Positioned(
                          top: 8,
                          left: 8,
                          child: Icon(Icons.error_outline,
                              size: 18, color: AuraColors.error),
                        ),
                      if (item.isFavorite)
                        Positioned(
                          top: 8,
                          right: 8,
                          child: Icon(Icons.favorite,
                              size: 16, color: AuraColors.champagne),
                        ),
                    ],
                  ),
                ),
              ),
            ),
            // Item Info
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.name ?? tagLabel(item.category),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleMedium?.copyWith(fontSize: 14),
                  ),
                  const SizedBox(height: 3),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: AuraColors.surfaceLight,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          tagLabel(item.category).toUpperCase(),
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontSize: 9,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.6,
                            color: AuraColors.accentIrisGlow,
                          ),
                        ),
                      ),
                      const Spacer(),
                      Text(
                        item.primaryColor ?? 'Neutral',
                        style:
                            theme.textTheme.bodyMedium?.copyWith(fontSize: 11),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState(ThemeData theme) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: AuraColors.surface,
                shape: BoxShape.circle,
                border: Border.all(color: AuraColors.border),
              ),
              child: Icon(Icons.checkroom_outlined,
                  size: 48, color: AuraColors.textTertiary),
            ),
            const SizedBox(height: 20),
            Text('Your Closet is Empty', style: theme.textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(
              'Upload your first garment. Our ML worker will automatically remove the background and tag it with OpenCLIP.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyLarge,
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: _openUploadModal,
              icon: const Icon(Icons.add_a_photo_outlined),
              label: const Text('Digitise First Garment'),
            ),
          ],
        ),
      ),
    );
  }
}
