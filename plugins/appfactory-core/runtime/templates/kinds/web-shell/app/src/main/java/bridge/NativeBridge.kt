package {{APPLICATION_ID}}.bridge

import android.content.Context
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebView
import java.io.File
import kotlinx.coroutines.CompletableDeferred
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * The page-facing half of the command/observe channel.
 *
 * Registered on the WebView as `AndroidBridge` (see WebShellScreen). The page's
 * own `window.__sagNative` half lives in the web bundle, not here -- this object
 * only has to agree with it on shape:
 *
 *   AndroidBridge.postResult('{"id":..,"result":..}')   answers a command this
 *                                                        bridge (via CommandServer)
 *                                                        delivered by id
 *   AndroidBridge.observe('{...}')                       one JSON audio-observation
 *                                                        event per call
 *
 * A plain `object`, not a class: WebView.addJavascriptInterface needs exactly one
 * instance, and CommandServer needs the SAME instance to register pending replies
 * against -- two instances would each hold half the correlation map and a reply
 * would never resolve the request that produced it.
 *
 * WebView invokes @JavascriptInterface methods on a background thread (the
 * opposite of View.evaluateJavascript, which must be called from the main
 * thread) -- see CommandServer's use of Handler(Looper.getMainLooper()). The
 * pending map is a ConcurrentHashMap for exactly that reason.
 */
object NativeBridge {

    private const val TAG = "NativeBridge"
    private val json = Json { ignoreUnknownKeys = true }
    // The actual id-matching/timeout logic lives in PendingReplies, which imports
    // no Android classes at all, so PendingRepliesTest can exercise it as an
    // ordinary JVM unit test. This object only owns the Android-facing surface
    // around it (the WebView, the JS interface methods, the filesDir write).
    private val replies = PendingReplies()

    /** Set while WebShellScreen's WebView is alive; null once it is torn down. */
    @Volatile
    var webView: WebView? = null

    /** Flipped by WebShellScreen's WebViewClient.onPageFinished; read by GET /__sag/health. */
    @Volatile
    var pageLoaded: Boolean = false

    /**
     * Set once, by ShellForegroundService.onCreate(), so observe() has a filesDir
     * to write into without every JS call needing a Context argument the page has
     * no natural way to supply.
     */
    @Volatile
    var appContext: Context? = null

    /** Called by CommandServer before delivering a command; the id keys the reply. */
    fun register(id: String): CompletableDeferred<JsonElement> = replies.register(id)

    /** Drops a registration nobody will ever answer (e.g. after CommandServer's timeout). */
    fun cancel(id: String) = replies.cancel(id)

    @JavascriptInterface
    fun postResult(payload: String) {
        runCatching {
            val obj = json.parseToJsonElement(payload).jsonObject
            val id = obj["id"]?.jsonPrimitive?.content ?: return@runCatching
            val result = obj["result"] ?: JsonNull
            replies.resolve(id, result)
        }.onFailure { Log.w(TAG, "malformed postResult payload: $payload", it) }
    }

    @JavascriptInterface
    fun observe(payload: String) {
        val ctx = appContext ?: run {
            Log.w(TAG, "observe() before appContext was set; dropping one event")
            return
        }
        runCatching {
            val dir = File(ctx.filesDir, "sag").apply { mkdirs() }
            File(dir, "audio-observed.jsonl").appendText(payload.trim() + "\n")
        }.onFailure { Log.w(TAG, "failed to persist observation", it) }
    }

    @JavascriptInterface
    fun log(message: String) {
        Log.d(TAG, message)
    }
}
