package {{APPLICATION_ID}}.bridge

/**
 * Deep links waiting for a page that can receive them.
 *
 * A link that cold-starts the app arrives in MainActivity.onCreate, before the WebView
 * exists and long before the bundle has installed window.__sagNative. Delivering it
 * then was a silent no-op: observed on the phone 2026-09-17, `v1acceptance://cold/start2`
 * launched the app and the page's received-intents list stayed empty, while the same
 * link sent to an already-running app arrived. So every link is queued, and the queue
 * is drained only into a WebView whose page has finished loading.
 *
 * No Android classes, so PendingLinksTest covers it on the JVM.
 */
class PendingLinks {
    private val queue = ArrayDeque<String>()

    @Synchronized
    fun add(uri: String) {
        queue.addLast(uri)
    }

    /** Everything queued, oldest first, leaving the queue empty. */
    @Synchronized
    fun drain(): List<String> {
        val all = queue.toList()
        queue.clear()
        return all
    }

    companion object {
        /**
         * [uri] as a single-quoted JS string literal. Backslash first, then the quote
         * that delimits it -- reversing the order would double-escape. Line terminators
         * are escaped too: a raw one ends a JS string literal mid-way.
         */
        fun jsString(uri: String): String = "'" + uri
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace(" ", "\\u2028")
            .replace(" ", "\\u2029") + "'"
    }
}
