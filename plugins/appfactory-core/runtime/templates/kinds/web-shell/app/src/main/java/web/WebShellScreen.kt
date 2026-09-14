package {{APPLICATION_ID}}.web

import android.annotation.SuppressLint
import android.content.Context
import android.util.Log
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
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
import {{APPLICATION_ID}}.bridge.PageLog

private const val TAG = "WebShell"

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
                        // WITHOUT THIS THE PAGE HAS NO HEIGHT. AndroidView gives a
                        // factory-created View WRAP_CONTENT layout params, so the WebView
                        // is measured AT_MOST: it asks the content how tall it wants to
                        // be, the content answers with a viewport-relative height, and the
                        // viewport is not established yet -- so every viewport unit,
                        // including 100% and 100vh, resolves to 0. The page renders
                        // perfectly into a box of zero height: correct DOM, clean console,
                        // green ladder, blank screen.
                        //
                        // Measured on the device that had it: 100vh, 100dvh, 100svh,
                        // 100lvh and 100% all returned 0 while window.innerHeight said
                        // 793. Found already solved in verbalogix-companion's
                        // EngineWebView.kt, which has set these three since it was written.
                        layoutParams = ViewGroup.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.MATCH_PARENT,
                        )
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        // Honour the bundle's <meta name="viewport">. Left at the default
                        // false, the tag is ignored and the page is laid out against the
                        // WebView's own width instead of device-width.
                        settings.useWideViewPort = true
                        settings.loadWithOverviewMode = true
                        // The whole point of this shell is a page that plays audio on
                        // its own, driven by commands rather than a human tapping
                        // "play" first.
                        settings.mediaPlaybackRequiresUserGesture = false
                        addJavascriptInterface(NativeBridge, "AndroidBridge")
                        // Without this the page fails silently: a 404'd module script, a
                        // missing stylesheet and an uncaught TypeError all render the same
                        // blank screen and none of them reach logcat on their own.
                        webChromeClient = object : WebChromeClient() {
                            override fun onConsoleMessage(message: ConsoleMessage): Boolean {
                                val kind = when (message.messageLevel()) {
                                    ConsoleMessage.MessageLevel.ERROR -> PageLog.Kind.ERROR
                                    ConsoleMessage.MessageLevel.WARNING -> PageLog.Kind.WARN
                                    else -> PageLog.Kind.LOG
                                }
                                NativeBridge.pageLog.add(
                                    PageLog.Entry(
                                        kind,
                                        message.message(),
                                        message.sourceId(),
                                        message.lineNumber(),
                                    ),
                                )
                                Log.println(
                                    if (kind.isFailure) Log.ERROR else Log.DEBUG,
                                    TAG,
                                    "console:${kind.wire} ${message.message()}" +
                                        " (${message.sourceId()}:${message.lineNumber()})",
                                )
                                return true
                            }
                        }
                        webViewClient = object : WebViewClient() {
                            override fun shouldInterceptRequest(
                                view: WebView,
                                request: WebResourceRequest,
                            ): WebResourceResponse? = assetLoader.shouldInterceptRequest(request.url)

                            override fun onReceivedError(
                                view: WebView,
                                request: WebResourceRequest,
                                error: WebResourceError,
                            ) {
                                super.onReceivedError(view, request, error)
                                record(PageLog.Kind.RESOURCE, "${error.errorCode} ${error.description}", request)
                            }

                            override fun onReceivedHttpError(
                                view: WebView,
                                request: WebResourceRequest,
                                errorResponse: WebResourceResponse,
                            ) {
                                super.onReceivedHttpError(view, request, errorResponse)
                                record(PageLog.Kind.HTTP, "HTTP ${errorResponse.statusCode}", request)
                            }

                            private fun record(
                                kind: PageLog.Kind,
                                what: String,
                                request: WebResourceRequest,
                            ) {
                                val url = request.url.toString()
                                // Browsers request /favicon.ico unprompted, whether or not
                                // the bundle ships one, so counting it as a failure would
                                // make pageFailures non-zero for every correct page and
                                // retire the assertion that depends on it. Recorded, not
                                // counted -- the information is still there to read.
                                val actual =
                                    if (request.url.path == "/favicon.ico") PageLog.Kind.LOG else kind
                                val scope = if (request.isForMainFrame) "main-frame" else "subresource"
                                NativeBridge.pageLog.add(PageLog.Entry(actual, "$what ($scope)", url))
                                Log.println(
                                    if (actual.isFailure) Log.ERROR else Log.DEBUG,
                                    TAG,
                                    "${actual.wire}: $what for $url",
                                )
                            }

                            /** Fires even when every script and stylesheet on the page
                             * 404'd, so this is "navigation finished", not "page works". */
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
