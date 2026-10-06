package com.example.lockbox_mobile

import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterFragmentActivity

class MainActivity: FlutterFragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Bloquea capturas de pantalla y grabación de la app (FLAG_SECURE).
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
    }
}