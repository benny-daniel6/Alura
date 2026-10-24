import 'package:aura_wardrobe/core/constants/api_constants.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('server input is normalised to a full API base URL', () {
    expect(ApiConstants.normalizeServerInput('10.184.20.18'),
        'http://10.184.20.18:8000/api/v1');
    expect(ApiConstants.normalizeServerInput(' 10.184.20.18:9000 '),
        'http://10.184.20.18:9000/api/v1');
    expect(ApiConstants.normalizeServerInput('https://api.aura.app'),
        'https://api.aura.app/api/v1');
    expect(ApiConstants.normalizeServerInput('http://host:8000/api/v1/'),
        'http://host:8000/api/v1');
    expect(ApiConstants.normalizeServerInput(''), isNull);
    expect(ApiConstants.normalizeServerInput('ftp://host'), isNull);
  });
}
