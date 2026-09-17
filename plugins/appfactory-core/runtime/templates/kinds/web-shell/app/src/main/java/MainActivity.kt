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
 * launchMode="singleTask": a deep link must reach the ONE existing MainActivity via
 * onNewIntent, never spin up a second instance with its own WebView and page. The
 * earlier singleTop only reused the activity when it was already on top of the SAME
 * task; observed on the phone 2026-09-17, the first link after a cold start created
 * a fresh page (its received-links list lost the cold-start link) while later links
 * reached it -- a second WebView, with the first possibly still running.
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
        // Only on a fresh start: a recreated activity (rotation, process restore) still
        // carries the launch intent, and delivering it again would repeat the link.
        if (savedInstanceState == null) deliverIntent(intent)
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

    /**
     * Queues a VIEW deep link for the page's window.__sagNative.onIntent(uri). It is
     * delivered now if a loaded page exists, otherwise by WebShellScreen's
     * onPageFinished -- see [{{APPLICATION_ID}}.bridge.PendingLinks] for the
     * cold start this used to lose.
     */
    private fun deliverIntent(intent: Intent?) {
        val uri = intent?.data?.toString() ?: return
        NativeBridge.pendingLinks.add(uri)
        NativeBridge.flushLinks()
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
