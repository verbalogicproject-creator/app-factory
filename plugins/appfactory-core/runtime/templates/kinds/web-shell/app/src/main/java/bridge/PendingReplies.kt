package {{APPLICATION_ID}}.bridge

import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CompletableDeferred
import kotlinx.serialization.json.JsonElement

/**
 * The id-correlation half of the command channel, kept free of every Android
 * import on purpose: NativeBridge's actual @JavascriptInterface methods run on a
 * background thread inside a live WebView and cannot be unit-tested on a plain
 * JVM without Robolectric or a device, but the id-matching and timeout behaviour
 * this class owns has nothing to do with Android at all -- PendingRepliesTest
 * exercises it directly, with zero Android classes on its classpath.
 */
class PendingReplies {

    private val pending = ConcurrentHashMap<String, CompletableDeferred<JsonElement>>()

    /** Called before a command is delivered; the returned deferred resolves when
     * [resolve] is called with the same id, or never (the caller times it out). */
    fun register(id: String): CompletableDeferred<JsonElement> {
        val deferred = CompletableDeferred<JsonElement>()
        pending[id] = deferred
        return deferred
    }

    /**
     * Resolves the pending reply for [id], if one is registered.
     *
     * Returns false, rather than throwing, for an id that is unknown, already
     * resolved, or already cancelled -- a stale or duplicate reply from the page
     * is not a bug in the page, and NativeBridge.postResult treats it as a
     * message it can silently drop.
     */
    fun resolve(id: String, result: JsonElement): Boolean {
        val deferred = pending.remove(id) ?: return false
        return deferred.complete(result)
    }

    /** Drops a registration nobody will ever answer (e.g. after a timeout). */
    fun cancel(id: String) {
        pending.remove(id)
    }

    /** Test/diagnostic hook: how many replies are still outstanding. */
    val size: Int get() = pending.size
}
