import '../../../core/utils/labels.dart';
import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../stylist/presentation/stylist_screen.dart';
import '../data/wardrobe_repository.dart';
import 'garment_image.dart';

class ItemDetailDialog extends StatefulWidget {
  final WardrobeItemModel item;
  final VoidCallback onUpdated;
  const ItemDetailDialog(
      {super.key, required this.item, required this.onUpdated});

  @override
  State<ItemDetailDialog> createState() => _ItemDetailDialogState();
}

class _ItemDetailDialogState extends State<ItemDetailDialog> {
  final WardrobeRepository _repo = WardrobeRepository();
  late TextEditingController _nameController;
  late TextEditingController _brandController;
  late TextEditingController _sizeController;
  late String _selectedCategory;
  late bool _isFavorite;
  bool _isSaving = false;
  late GarmentImageVariant _variant;

  final List<String> _categories = [
    'top',
    'bottom',
    'outerwear',
    'dress',
    'one_piece',
    'footwear',
    'bag',
    'accessory',
    'headwear'
  ];

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.item.name ?? '');
    _brandController = TextEditingController(text: widget.item.brand ?? '');
    _sizeController = TextEditingController(text: widget.item.size ?? '');
    _selectedCategory = widget.item.category;
    _isFavorite = widget.item.isFavorite;
    _variant = widget.item.showcaseImageUrl != null
        ? GarmentImageVariant.showcase
        : GarmentImageVariant.cutout;
  }

  void _styleThisPiece() {
    final navigator = Navigator.of(context);
    navigator.pop();
    navigator.push(MaterialPageRoute(
      builder: (_) =>
          StylistScreen(anchorItems: [widget.item], standalone: true),
    ));
  }

  @override
  void dispose() {
    _nameController.dispose();
    _brandController.dispose();
    _sizeController.dispose();
    super.dispose();
  }

  Future<void> _handleSave() async {
    setState(() => _isSaving = true);
    try {
      await _repo.updateItem(widget.item.id, {
        'name': _nameController.text.trim(),
        'category': _selectedCategory,
        'brand': _brandController.text.trim(),
        'size': _sizeController.text.trim(),
        'is_favorite': _isFavorite,
      });
      widget.onUpdated();
      if (!mounted) return;
      Navigator.of(context).pop();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('Failed to update: $e'),
            backgroundColor: AuraColors.error),
      );
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  Future<void> _handleDelete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AuraColors.surface,
        title: const Text('Delete Garment?'),
        content: const Text('Remove this item from your digital wardrobe?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Cancel')),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
                backgroundColor: AuraColors.error,
                minimumSize: const Size(0, 48)),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      await _repo.deleteItem(widget.item.id);
      widget.onUpdated();
      if (!mounted) return;
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: AuraColors.surface,
      insetPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            // Garment image: studio photo (white), transparent cutout, or the original photo
            Container(
              height: 240,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: _variant == GarmentImageVariant.showcase
                    ? Colors.white
                    : AuraColors.surfaceLight,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AuraColors.border),
              ),
              child: GarmentImage(garment: widget.item, variant: _variant),
            ),
            const SizedBox(height: 10),
            SegmentedButton<GarmentImageVariant>(
              showSelectedIcon: false,
              style: SegmentedButton.styleFrom(
                selectedBackgroundColor:
                    AuraColors.accentIris.withOpacity(0.25),
                foregroundColor: AuraColors.textSecondary,
                selectedForegroundColor: AuraColors.textPrimary,
                side: BorderSide(color: AuraColors.border),
                visualDensity: VisualDensity.compact,
              ),
              segments: [
                if (widget.item.showcaseImageUrl != null)
                  const ButtonSegment(
                      value: GarmentImageVariant.showcase,
                      label: Text('Studio')),
                const ButtonSegment(
                    value: GarmentImageVariant.cutout, label: Text('Cutout')),
                const ButtonSegment(
                    value: GarmentImageVariant.original,
                    label: Text('Original')),
              ],
              selected: {_variant},
              onSelectionChanged: (v) => setState(() => _variant = v.first),
            ),
            const SizedBox(height: 14),
            ElevatedButton.icon(
              onPressed:
                  widget.item.status == 'completed' ? _styleThisPiece : null,
              icon: const Icon(Icons.auto_awesome),
              label: const Text('Style This Piece'),
            ),
            const SizedBox(height: 20),

            // AI Detected Tags Info Chip Bar
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _buildInfoBadge(
                    'Color: ${widget.item.primaryColor ?? "Neutral"}'),
                _buildInfoBadge('Season: ${tagList(widget.item.seasons)}'),
                _buildInfoBadge('Worn: ${widget.item.wearCount} times'),
                if (widget.item.occasions.isNotEmpty)
                  _buildInfoBadge('For: ${tagList(widget.item.occasions)}'),
              ],
            ),
            const SizedBox(height: 20),

            // Edit Name
            TextField(
              controller: _nameController,
              style: TextStyle(color: AuraColors.textPrimary),
              decoration: const InputDecoration(labelText: 'Item Name'),
            ),
            const SizedBox(height: 14),

            // Edit Category Dropdown
            DropdownButtonFormField<String>(
              value: _selectedCategory,
              dropdownColor: AuraColors.surfaceLight,
              style: TextStyle(color: AuraColors.textPrimary),
              decoration: const InputDecoration(labelText: 'Category'),
              items: _categories.map((c) {
                return DropdownMenuItem(value: c, child: Text(tagLabel(c)));
              }).toList(),
              onChanged: (val) {
                if (val != null) setState(() => _selectedCategory = val);
              },
            ),
            const SizedBox(height: 14),

            // Brand & Size Row
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _brandController,
                    style: TextStyle(color: AuraColors.textPrimary),
                    decoration: const InputDecoration(labelText: 'Brand'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _sizeController,
                    style: TextStyle(color: AuraColors.textPrimary),
                    decoration: const InputDecoration(labelText: 'Size'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),

            // Favorite Switch
            SwitchListTile(
              title: const Text('Mark as Favorite'),
              value: _isFavorite,
              activeColor: AuraColors.accentIris,
              contentPadding: EdgeInsets.zero,
              onChanged: (val) => setState(() => _isFavorite = val),
            ),
            const SizedBox(height: 20),

            // Action Buttons
            ElevatedButton(
              onPressed: _isSaving ? null : _handleSave,
              child: _isSaving
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('Save Changes'),
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: _handleDelete,
              icon:
                  Icon(Icons.delete_outline, color: AuraColors.error, size: 20),
              label: Text('Remove from Wardrobe',
                  style: TextStyle(color: AuraColors.error)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoBadge(String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: AuraColors.surfaceLight,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AuraColors.border),
      ),
      child: Text(text,
          style: TextStyle(fontSize: 12, color: AuraColors.textSecondary)),
    );
  }
}
