package {{APPLICATION_ID}}.web

import android.annotation.SuppressLint
import android.content.Context
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
 * Serves app/src/main/assets/web/ as though it were the site root.
 *
 * The bundle is kept under assets/web/ rather than at the assets root so it cannot
 * collide with anything else the app ships in assets. But a bundler emits ABSOLUTE
 * URLs -- a default `vite build` writes `<script src="/assets/index-<hash>.js">` -- and
 * the browser resolves those against the ORIGIN, not against the page. Mounting the
 * handler at "/assets/web/" meant such a request arrived as "/assets/index-<hash>.js",
 * which mapped to android_asset/index-<hash>.js, which does not exist. 404, blank page,
 * and every static check still green, because nothing static ever looks at the page.
 *
 * Mounting at "/" makes the URL root the BUNDLE root, so an absolute /assets/... path
 * resolves and so does a relative one. That covers Vite, Next export, Astro, SvelteKit
 * and CRA without touching any of their configs -- which matters, because Nuxt cannot
 * emit a relative base at all (a Nitro limitation), so a per-framework base-path
 * strategy would have had no answer there.
 *
 * WebViewAssetLoader strips the registered prefix before calling a handler
 * (PathMatcher.getSuffixPath), so mounted at "/" this receives "assets/index-<hash>.js"
 * and prepends the bundle directory itself.
 */
private class BundleRootPathHandler(context: Context) : WebViewAssetLoader.PathHandler {
    private val assets = WebViewAssetLoader.AssetsPathHandler(context)

    override fun handle(path: String): WebResourceResponse? = assets.handle(BUNDLE_DIR + path)

    private companion object {
        /** Kept in step with scaffold.py's copytree target and sync-web.sh's DEST. */
        const val BUNDLE_DIR = "web/"
    }
}

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
 * The page is served over https://appassets.androidplatform.net/ rather than as a
 * file:// URL: a file:// origin cannot run window.fetch against same-origin resources
 * the way a real page can. See [BundleRootPathHandler] for why it is mounted at the
 * root.
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
                        .addPathHandler("/", BundleRootPathHandler(ctx))
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
                        loadUrl("https://appassets.androidplatform.net/index.html")
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
