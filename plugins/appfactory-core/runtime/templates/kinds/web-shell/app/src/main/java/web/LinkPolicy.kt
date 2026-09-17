package {{APPLICATION_ID}}.web

/**
 * Decides where a navigation the page asks for should go: stay in the WebView, leave
 * the app for the system (browser, dialer, mail, another app), or go nowhere.
 *
 * Pure -- no android.* types -- so every form below is pinned by a plain JVM unit test.
 * android.net.Uri is a stub on the JVM, which is why scheme and host are parsed by hand.
 *
 * Forms a page can use to leave, all of which arrive at shouldOverrideUrlLoading as a
 * main-frame navigation (multiple windows are off, so `target="_blank"` and
 * `window.open` navigate the main frame rather than opening a second WebView):
 *   <a href>, <a target="_blank">, location.href = ..., window.open(...)
 *
 * Not seen by this policy at all: POST form submissions (WebView never calls
 * shouldOverrideUrlLoading for POST) and fetch/XHR, which are not navigations.
 */
object LinkPolicy {

    enum class Route { STAY, EXTERNAL, BLOCK }

    const val APP_HOST = "appassets.androidplatform.net"

    private val SCHEME = Regex("^([a-zA-Z][a-zA-Z0-9+.-]*):")

    /** Schemes the WebView renders itself. */
    private val INTERNAL_SCHEMES = setOf("about", "data", "blob")

    /** Schemes that must never be handed to another app from page content. */
    private val BLOCKED_SCHEMES = setOf("javascript", "file", "content")

    fun route(url: String, isMainFrame: Boolean): Route {
        // An iframe navigating inside itself is the embed working, not the user leaving.
        if (!isMainFrame) return Route.STAY
        val scheme = SCHEME.find(url.trim())?.groupValues?.get(1)?.lowercase() ?: return Route.STAY
        return when (scheme) {
            in INTERNAL_SCHEMES -> Route.STAY
            in BLOCKED_SCHEMES -> Route.BLOCK
            "http", "https" -> if (host(url) == APP_HOST) Route.STAY else Route.EXTERNAL
            else -> Route.EXTERNAL
        }
    }

    /**
     * What to open when no app on the phone handles a link: its `browser_fallback_url`,
     * but only when that is an outside http(s) page. A fallback pointing back at the
     * bundle, or at another scheme (which could itself be unhandled, or blocked), is
     * dropped rather than followed.
     */
    fun fallbackTarget(fallback: String?): String? {
        if (fallback.isNullOrBlank()) return null
        val scheme = SCHEME.find(fallback.trim())?.groupValues?.get(1)?.lowercase()
        if (scheme != "http" && scheme != "https") return null
        return if (route(fallback, isMainFrame = true) == Route.EXTERNAL) fallback.trim() else null
    }

    /** Lowercased host of an http(s) URL, without userinfo or port; null if absent. */
    internal fun host(url: String): String? {
        val afterSlashes = url.trim().substringAfter("://", missingDelimiterValue = "")
        if (afterSlashes.isEmpty()) return null
        val authority = afterSlashes.takeWhile { it != '/' && it != '?' && it != '#' }
        val hostPort = authority.substringAfterLast('@')
        val host = if (hostPort.startsWith("[")) {
            hostPort.substringBefore(']') + "]"
        } else {
            hostPort.substringBefore(':')
        }
        return host.lowercase().ifEmpty { null }
    }
}
