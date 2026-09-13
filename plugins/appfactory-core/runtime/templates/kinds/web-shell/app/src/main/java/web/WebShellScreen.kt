package {{APPLICATION_ID}}.web

import android.annotation.SuppressLint
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.webkit.WebViewAssetLoader
import {{APPLICATION_ID}}.bridge.NativeBridge

/**
 * Hosts the built web bundle (app/src/main/assets/web/, put there by
 * `scaffold.py --kind web-shell --web-dir` or later by `sync-web.sh`) inside a
 * WebView, wired to [NativeBridge] for the command/observe channel described in
 * bridge/NativeBridge.kt and bridge/CommandServer.kt.
 *
 * Kept inside Scaffold so the mandatory edge-to-edge insets (MainActivity calls
 * enableEdgeToEdge(); see preflight check 210) are actually consumed here -- a
 * raw, un-inset AndroidView filling the window would draw the page under the
 * status bar exactly like an un-inset Compose screen would.
 *
 * WebViewAssetLoader maps https://appassets.androidplatform.net/assets/web/ to the
 * assets/web/ the bundle was copied into, rather than loading a file:// URL: a
 * file:// origin cannot run window.fetch against same-origin resources the way a
 * real page can, and this keeps the bundle's own relative asset paths working
 * unmodified.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun WebShellScreen(modifier: Modifier = Modifier) {
    var currentWebView: WebView? = null
    Scaffold(modifier = modifier.fillMaxSize()) { inner ->
        Surface(modifier = Modifier.fillMaxSize()) {
            AndroidView(
                modifier = Modifier.fillMaxSize().padding(inner),
                factory = { ctx ->
                    val assetLoader = WebViewAssetLoader.Builder()
                        .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(ctx))
                        .build()
                    WebView(ctx).apply {
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        // The whole point of this shell is a page that plays audio on
                        // its own, driven by commands rather than a human tapping
                        // "play" first.
                        settings.mediaPlaybackRequiresUserGesture = false
                        addJavascriptInterface(NativeBridge, "AndroidBridge")
                        webViewClient = object : WebViewClient() {
                            override fun shouldInterceptRequest(
                                view: WebView,
                                request: WebResourceRequest,
                            ): WebResourceResponse? = assetLoader.shouldInterceptRequest(request.url)

                            override fun onPageFinished(view: WebView, url: String?) {
                                super.onPageFinished(view, url)
                                NativeBridge.pageLoaded = true
                            }
                        }
                        loadUrl("https://appassets.androidplatform.net/assets/web/index.html")
                    }
                },
                update = { webView ->
                    currentWebView = webView
                    NativeBridge.webView = webView
                },
            )
        }
    }
    DisposableEffect(Unit) {
        onDispose {
            if (NativeBridge.webView === currentWebView) {
                NativeBridge.webView = null
            }
        }
    }
}
