import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../auth/data/auth_repository.dart';
import '../data/quiz_state.dart';
import '../../home/presentation/home_shell_screen.dart';

class QuizScreen extends StatefulWidget {
  final UserModel user;
  const QuizScreen({super.key, required this.user});

  @override
  State<QuizScreen> createState() => _QuizScreenState();
}

class _QuizScreenState extends State<QuizScreen> {
  final PageController _pageController = PageController();
  final QuizPreferencesModel _quizData = QuizPreferencesModel();

  int _currentStep = 0;
  final int _totalSteps = 4;
  bool _isSubmitting = false;

  // Options Data
  final List<Map<String, String>> _styleVibes = [
    {
      'id': 'minimalist',
      'label': 'Minimalist',
      'desc': 'Clean lines, monochromatic & timeless silhouettes'
    },
    {
      'id': 'quiet_luxury',
      'label': 'Quiet Luxury',
      'desc': 'High-texture cashmere, silk, subtle tailoring'
    },
    {
      'id': 'streetwear',
      'label': 'Streetwear',
      'desc': 'Boxy cuts, sneakers, graphic layers'
    },
    {
      'id': 'dark_academia',
      'label': 'Dark Academia',
      'desc': 'Tweeds, wool blazers, dark plaids'
    },
    {
      'id': 'avant_garde',
      'label': 'Avant-Garde',
      'desc': 'Asymmetric geometry, architectural drapery'
    },
    {
      'id': 'casual_chic',
      'label': 'Casual Chic',
      'desc': 'Effortless elevated denim and crisp basics'
    },
    {
      'id': 'utilitarian',
      'label': 'Utilitarian',
      'desc': 'Cargo, technical fabrics, structural outerwear'
    },
    {
      'id': 'retro_90s',
      'label': '90s Archive',
      'desc': 'Vintage denim, leather jackets, grunge accents'
    },
  ];

  final List<Map<String, dynamic>> _colorPalettes = [
    {
      'id': 'monochrome',
      'name': 'Monochrome',
      'colors': [Colors.black, Colors.grey, Colors.white]
    },
    {
      'id': 'earth_tones',
      'name': 'Earth & Clay',
      'colors': [Color(0xFF8B5A2B), Color(0xFFC2B280), Color(0xFF556B2F)]
    },
    {
      'id': 'jewel_tones',
      'name': 'Jewel Tones',
      'colors': [Color(0xFF0F52BA), Color(0xFF50C878), Color(0xFF800020)]
    },
    {
      'id': 'slate_neutrals',
      'name': 'Slate & Stone',
      'colors': [Color(0xFF708090), Color(0xFFDCDCDC), Color(0xFF2F4F4F)]
    },
    {
      'id': 'pastels',
      'name': 'Muted Pastels',
      'colors': [Color(0xFFE6E6FA), Color(0xFF98FF98), Color(0xFFFFB6C1)]
    },
    {
      'id': 'vibrant',
      'name': 'High Energy',
      'colors': [Color(0xFFFF4500), Color(0xFFFFD700), Color(0xFF1E90FF)]
    },
  ];

  final List<Map<String, dynamic>> _occasions = [
    {'id': 'casual_daily', 'title': 'Casual Daily', 'icon': Icons.coffee},
    {
      'id': 'office_work',
      'title': 'Office & Creative Work',
      'icon': Icons.laptop_chromebook
    },
    {
      'id': 'evening_dinner',
      'title': 'Evening Dining & Drinks',
      'icon': Icons.wine_bar
    },
    {'id': 'nightlife', 'title': 'Nightlife & Events', 'icon': Icons.nightlife},
    {
      'id': 'formal_gala',
      'title': 'Formal & Ceremonies',
      'icon': Icons.celebration
    },
    {
      'id': 'active_lounge',
      'title': 'Loungewear & Athleisure',
      'icon': Icons.fitness_center
    },
  ];

  final List<Map<String, String>> _climates = [
    {'id': 'temperate', 'name': 'Temperate (4 Seasons)'},
    {'id': 'tropical', 'name': 'Warm & Tropical'},
    {'id': 'cold_dry', 'name': 'Cold & Crisp'},
    {'id': 'oceanic', 'name': 'Breezy & Coastal'},
  ];

  final List<Map<String, String>> _silhouettes = [
    {
      'id': 'oversized',
      'name': 'Relaxed & Oversized',
      'desc': 'Draped shoulders, wide legs, comfortable volume'
    },
    {
      'id': 'regular',
      'name': 'Classic Regular',
      'desc': 'Balanced proportions and standard tailoring'
    },
    {
      'id': 'fitted',
      'name': 'Slim & Fitted',
      'desc': 'Close-to-body contouring and sharp cuts'
    },
  ];

  void _nextStep() {
    if (_currentStep < _totalSteps - 1) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOutCubic,
      );
      setState(() => _currentStep++);
    } else {
      _finishQuiz();
    }
  }

  void _prevStep() {
    if (_currentStep > 0) {
      _pageController.previousPage(
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOutCubic,
      );
      setState(() => _currentStep--);
    }
  }

  Future<void> _finishQuiz() async {
    setState(() => _isSubmitting = true);
    try {
      await _quizData.submit();
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => HomeShellScreen(user: widget.user)),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to save preferences: $e'),
          backgroundColor: AuraColors.error,
        ),
      );
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: _currentStep > 0
            ? IconButton(
                icon: const Icon(Icons.arrow_back_ios_new, size: 18),
                onPressed: _prevStep,
              )
            : null,
        title: Text(
          'STEP ${_currentStep + 1} OF $_totalSteps',
          style: theme.textTheme.labelMedium?.copyWith(
            letterSpacing: 2.0,
            color: AuraColors.textSecondary,
          ),
        ),
        centerTitle: true,
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Linear Progress Indicator
            LinearProgressIndicator(
              value: (_currentStep + 1) / _totalSteps,
              backgroundColor: AuraColors.surfaceLight,
              valueColor: AlwaysStoppedAnimation<Color>(AuraColors.accentIris),
              minHeight: 3,
            ),

            Expanded(
              child: PageView(
                controller: _pageController,
                physics: const NeverScrollableScrollPhysics(),
                children: [
                  _buildStep1Aesthetics(theme),
                  _buildStep2Colors(theme),
                  _buildStep3Occasions(theme),
                  _buildStep4ClimateSizing(theme),
                ],
              ),
            ),

            // Bottom Navigation Action Bar
            Padding(
              padding:
                  const EdgeInsets.symmetric(horizontal: 24.0, vertical: 20.0),
              child: ElevatedButton(
                onPressed: _isSubmitting ? null : _nextStep,
                child: _isSubmitting
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white),
                      )
                    : Text(
                        _currentStep == _totalSteps - 1
                            ? 'Curate My Wardrobe'
                            : 'Continue',
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // STEP 1: Aesthetic & Silhouette Vibes
  Widget _buildStep1Aesthetics(ThemeData theme) {
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
      children: [
        Text('Style Archetypes', style: theme.textTheme.displayMedium),
        const SizedBox(height: 8),
        Text(
          'Select the vibes that resonate with your personal expression. (Pick 1 or more)',
          style: theme.textTheme.bodyLarge,
        ),
        const SizedBox(height: 24),
        ..._styleVibes.map((vibe) {
          final isSelected = _quizData.styleVibes.contains(vibe['id']);
          return Padding(
            padding: const EdgeInsets.only(bottom: 12.0),
            child: InkWell(
              onTap: () {
                setState(() {
                  if (isSelected) {
                    _quizData.styleVibes.remove(vibe['id']);
                  } else {
                    _quizData.styleVibes.add(vibe['id']!);
                  }
                });
              },
              borderRadius: BorderRadius.circular(16),
              child: Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color:
                      isSelected ? AuraColors.surfaceLight : AuraColors.surface,
                  border: Border.all(
                    color:
                        isSelected ? AuraColors.accentIris : AuraColors.border,
                    width: isSelected ? 1.6 : 1.0,
                  ),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(vibe['label']!,
                              style: theme.textTheme.titleMedium),
                          const SizedBox(height: 4),
                          Text(vibe['desc']!,
                              style: theme.textTheme.bodyMedium),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    Icon(
                      isSelected
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      color: isSelected
                          ? AuraColors.accentIris
                          : AuraColors.textTertiary,
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ],
    );
  }

  // STEP 2: Color Palette
  Widget _buildStep2Colors(ThemeData theme) {
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
      children: [
        Text('Color Palette', style: theme.textTheme.displayMedium),
        const SizedBox(height: 8),
        Text(
          'Which color spectrums anchor your ideal outfit rotations?',
          style: theme.textTheme.bodyLarge,
        ),
        const SizedBox(height: 24),
        ..._colorPalettes.map((palette) {
          final isSelected = _quizData.preferredColors.contains(palette['id']);
          final colors = palette['colors'] as List<Color>;
          return Padding(
            padding: const EdgeInsets.only(bottom: 12.0),
            child: InkWell(
              onTap: () {
                setState(() {
                  if (isSelected) {
                    _quizData.preferredColors.remove(palette['id']);
                  } else {
                    _quizData.preferredColors.add(palette['id']);
                  }
                });
              },
              borderRadius: BorderRadius.circular(16),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
                decoration: BoxDecoration(
                  color:
                      isSelected ? AuraColors.surfaceLight : AuraColors.surface,
                  border: Border.all(
                    color:
                        isSelected ? AuraColors.accentIris : AuraColors.border,
                    width: isSelected ? 1.6 : 1.0,
                  ),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(
                  children: [
                    // Color swatch dots
                    Row(
                      children: colors.map((c) {
                        return Container(
                          margin: const EdgeInsets.only(right: 6),
                          width: 22,
                          height: 22,
                          decoration: BoxDecoration(
                            color: c,
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white24, width: 1),
                          ),
                        );
                      }).toList(),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Text(palette['name'],
                          style: theme.textTheme.titleMedium),
                    ),
                    Icon(
                      isSelected
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      color: isSelected
                          ? AuraColors.accentIris
                          : AuraColors.textTertiary,
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ],
    );
  }

  // STEP 3: Occasions
  Widget _buildStep3Occasions(ThemeData theme) {
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
      children: [
        Text('Everyday Contexts', style: theme.textTheme.displayMedium),
        const SizedBox(height: 8),
        Text(
          'Where do you spend most of your waking hours? Our AI Stylist will prioritize outfits for these.',
          style: theme.textTheme.bodyLarge,
        ),
        const SizedBox(height: 24),
        ..._occasions.map((occ) {
          final isSelected = _quizData.primaryOccasions.contains(occ['id']);
          return Padding(
            padding: const EdgeInsets.only(bottom: 12.0),
            child: InkWell(
              onTap: () {
                setState(() {
                  if (isSelected) {
                    _quizData.primaryOccasions.remove(occ['id']);
                  } else {
                    _quizData.primaryOccasions.add(occ['id']);
                  }
                });
              },
              borderRadius: BorderRadius.circular(16),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
                decoration: BoxDecoration(
                  color:
                      isSelected ? AuraColors.surfaceLight : AuraColors.surface,
                  border: Border.all(
                    color:
                        isSelected ? AuraColors.accentIris : AuraColors.border,
                    width: isSelected ? 1.6 : 1.0,
                  ),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(
                  children: [
                    Icon(occ['icon'] as IconData,
                        color: isSelected
                            ? AuraColors.accentIris
                            : AuraColors.textSecondary),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Text(occ['title'] as String,
                          style: theme.textTheme.titleMedium),
                    ),
                    Icon(
                      isSelected
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      color: isSelected
                          ? AuraColors.accentIris
                          : AuraColors.textTertiary,
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ],
    );
  }

  // STEP 4: Climate & Silhouette Cut
  Widget _buildStep4ClimateSizing(ThemeData theme) {
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
      children: [
        Text('Climate & Silhouette', style: theme.textTheme.displayMedium),
        const SizedBox(height: 8),
        Text('Fine-tune weather sensitivity and cut preferences.',
            style: theme.textTheme.bodyLarge),
        const SizedBox(height: 24),
        Text('Primary Climate Zone', style: theme.textTheme.titleMedium),
        const SizedBox(height: 12),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: _climates.map((c) {
            final isSelected = _quizData.climateZone == c['id'];
            return ChoiceChip(
              label: Text(c['name']!),
              selected: isSelected,
              onSelected: (selected) {
                if (selected) setState(() => _quizData.climateZone = c['id']!);
              },
              selectedColor: AuraColors.accentIris.withOpacity(0.2),
              backgroundColor: AuraColors.surface,
              side: BorderSide(
                color: isSelected ? AuraColors.accentIris : AuraColors.border,
              ),
              labelStyle: TextStyle(
                color: isSelected
                    ? AuraColors.textPrimary
                    : AuraColors.textSecondary,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 32),
        Text('Preferred Silhouette Cut', style: theme.textTheme.titleMedium),
        const SizedBox(height: 12),
        ..._silhouettes.map((s) {
          final isSelected = _quizData.sizingPreference == s['id'];
          return Padding(
            padding: const EdgeInsets.only(bottom: 10.0),
            child: InkWell(
              onTap: () =>
                  setState(() => _quizData.sizingPreference = s['id']!),
              borderRadius: BorderRadius.circular(14),
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color:
                      isSelected ? AuraColors.surfaceLight : AuraColors.surface,
                  border: Border.all(
                    color:
                        isSelected ? AuraColors.accentIris : AuraColors.border,
                    width: isSelected ? 1.6 : 1.0,
                  ),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(s['name']!, style: theme.textTheme.titleMedium),
                          const SizedBox(height: 4),
                          Text(s['desc']!, style: theme.textTheme.bodyMedium),
                        ],
                      ),
                    ),
                    Icon(
                      isSelected
                          ? Icons.radio_button_checked
                          : Icons.radio_button_unchecked,
                      color: isSelected
                          ? AuraColors.accentIris
                          : AuraColors.textTertiary,
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ],
    );
  }
}
