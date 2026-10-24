/// Human-readable labels for the API's snake_case tags (categories, seasons, occasions).
const Map<String, String> _labels = {
  'all_season': 'All seasons',
  'one_piece': 'One-piece',
  'casual_daily': 'Casual',
  'office_work': 'Work',
  'evening_dinner': 'Dinner',
  'formal_events': 'Formal',
  'nightlife': 'Night out',
};

String tagLabel(String tag) {
  final known = _labels[tag];
  if (known != null) return known;
  final words = tag.replaceAll('_', ' ').trim();
  return words.isEmpty ? words : words[0].toUpperCase() + words.substring(1);
}

String tagList(Iterable<String> tags) => tags.map(tagLabel).join(', ');
