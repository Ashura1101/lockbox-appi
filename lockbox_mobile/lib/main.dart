import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'controllers/auth_controller.dart';
import 'core/lifecycle/app_lifecycle_observer.dart';
import 'repositories/vault_repository.dart';
import 'screens/biometric_lock_screen.dart';
import 'screens/login_screen.dart';
import 'screens/vault_screen.dart';
import 'services/api_service.dart';
import 'services/biometric_service.dart';
import 'services/token_storage_service.dart';

void main() {
  runApp(const LockboxApp());
}

class LockboxApp extends StatelessWidget {
  const LockboxApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<ApiService>(
          create: (_) => ApiService(onTokensRefreshed: (access, refresh) => TokenStorageService().saveTokens(access, refresh)),
          dispose: (_, api) => api.dispose(),
        ),
        Provider<TokenStorageService>(
          create: (_) => TokenStorageService(),
        ),
        Provider<BiometricService>(
          create: (_) => BiometricService(),
        ),
        Provider<VaultRepository>(
          create: (_) => VaultRepository(),
        ),
        ChangeNotifierProvider<AuthController>(
          create: (context) => AuthController(
            api: context.read<ApiService>(),
            tokenStorage: context.read<TokenStorageService>(),
            biometric: context.read<BiometricService>(),
            vault: context.read<VaultRepository>(),
          )..restoreSession(),
        ),
      ],
      child: MaterialApp(
        title: 'Lockbox',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF6366F1),
            brightness: Brightness.dark,
          ),
          useMaterial3: true,
        ),
        home: const _AuthGate(),
      ),
    );
  }
}

class _AuthGate extends StatefulWidget {
  const _AuthGate();

  @override
  State<_AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<_AuthGate> {
  late final LockboxLifecycleObserver _lifecycleObserver;

  @override
  void initState() {
    super.initState();
    _lifecycleObserver = LockboxLifecycleObserver(
      onLock: () => context.read<AuthController>().lock(),
    );
    WidgetsBinding.instance.addObserver(_lifecycleObserver);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(_lifecycleObserver);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();

    final Widget child;
    if (!auth.isAuthenticated) {
      child = const LoginScreen();
    } else if (auth.isLocked) {
      child = const BiometricLockScreen();
    } else {
      child = const VaultScreen();
    }

    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      child: child,
    );
  }
}