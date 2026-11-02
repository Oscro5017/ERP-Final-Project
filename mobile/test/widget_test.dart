import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:erp_oganic_farm/main.dart';

void main() {
  testWidgets('ERP Organic Farm App smoke test', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    // Build our app and trigger a frame.
    await tester.pumpWidget(const ErpOrganicFarmApp());
    await tester.pumpAndSettle();

    // Verify login screen or app loads
    expect(find.text('ERP Organic Farm'), findsOneWidget);
  });
}
