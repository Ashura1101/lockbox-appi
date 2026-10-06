import 'package:flutter_test/flutter_test.dart';

import 'package:lockbox_mobile/main.dart';

void main() {
  testWidgets('App renderiza la pantalla de login', (WidgetTester tester) async {
    await tester.pumpWidget(const LockboxApp());
    await tester.pump();

    expect(find.text('LOCKBOX'), findsOneWidget);
  });
}