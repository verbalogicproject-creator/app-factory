package {{APPLICATION_ID}}

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import {{APPLICATION_ID}}.bridge.NativeBridge
import {{APPLICATION_ID}}.service.ShellForegroundService
import {{APPLICATION_ID}}.ui.theme.{{APP_CLASS}}Theme
import {{APPLICATION_ID}}.web.WebShellScreen
import dagger.hilt.android.AndroidEntryPoint

/**
 * @AndroidEntryPoint is half of the Hilt contract that fails loudly; the other half
 * is @HiltAndroidApp on the Application class AND android:name in the manifest
 * pointing at it. See preflight check 060.
 *
 * launchMode="singleTop": a deep link arriving while the app is already the
 * foreground activity must reach onNewIntent, not spin up a second instance with
 * its own (empty) WebView.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    // POST_NOTIFICATIONS (API 33+) gates only the notification's visibility, never
    // whether the foreground service itself starts -- the conformance pattern here
    // is: ask once, and if denied, the app keeps working exactly as before. The
    // command server does not wait on this result.
    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* denial path: no-op, on purpose */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Edge-to-edge is mandatory and non-opt-out from targetSdk 35/36. See
        // preflight check 210 and WebShellScreen's Scaffold, which consumes the
        // insets this call causes content to be drawn under.
        enableEdgeToEdge()
        requestNotificationPermissionIfNeeded()
        ShellForegroundService.start(this)
        setContent {
            {{APP_CLASS}}Theme {
                WebShellScreen()
            }
        }
        deliverIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        deliverIntent(intent)
    }

    override fun onDestroy() {
        ShellForegroundService.stop(this)
        super.onDestroy()
    }

    /** Forwards a VIEW deep link to the page as window.__sagNative.onIntent(uri). */
    private fun deliverIntent(intent: Intent?) {
        val uri = intent?.data?.toString() ?: return
        // Single-quoted JS string literal: escape backslash first, then the quote
        // that delimits it, in that order -- reversing it would double-escape.
        val escaped = uri.replace("\\", "\\\\").replace("'", "\\'")
        NativeBridge.webView?.evaluateJavascript(
            "window.__sagNative && window.__sagNative.onIntent('$escaped')",
            null,
        )
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        val granted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
}
