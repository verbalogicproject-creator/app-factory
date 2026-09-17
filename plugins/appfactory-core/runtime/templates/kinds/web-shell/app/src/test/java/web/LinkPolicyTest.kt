package {{APPLICATION_ID}}.web

import {{APPLICATION_ID}}.web.LinkPolicy.Route
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LinkPolicyTest {

    private fun main(url: String) = LinkPolicy.route(url, isMainFrame = true)

    @Test
    fun `the bundle's own pages stay in the app`() {
        assertEquals(Route.STAY, main("https://appassets.androidplatform.net/index.html"))
        assertEquals(Route.STAY, main("https://appassets.androidplatform.net/other#x"))
        assertEquals(Route.STAY, main("HTTPS://APPASSETS.androidplatform.net/"))
    }

    @Test
    fun `outside websites leave for the browser`() {
        assertEquals(Route.EXTERNAL, main("https://vite.dev/"))
        assertEquals(Route.EXTERNAL, main("http://example.com/a?b=c"))
        assertEquals(Route.EXTERNAL, main("https://github.com/vitejs/vite"))
    }

    @Test
    fun `a look-alike host is not the app`() {
        assertEquals(Route.EXTERNAL, main("https://appassets.androidplatform.net.evil.com/"))
        assertEquals(Route.EXTERNAL, main("https://appassets.androidplatform.net@evil.com/"))
        assertEquals(Route.EXTERNAL, main("https://evil.com/?appassets.androidplatform.net"))
    }

    @Test
    fun `other app schemes are handed to the system`() {
        for (url in listOf(
            "mailto:a@b.c", "tel:+123", "sms:123", "geo:0,0", "market://details?id=x",
            "intent://scan/#Intent;scheme=zxing;end", "myapp://open",
        )) {
            assertEquals(url, Route.EXTERNAL, main(url))
        }
    }

    @Test
    fun `webview-internal schemes stay`() {
        assertEquals(Route.STAY, main("about:blank"))
        assertEquals(Route.STAY, main("data:text/html,hi"))
        assertEquals(Route.STAY, main("blob:https://appassets.androidplatform.net/uuid"))
    }

    @Test
    fun `local-file and script schemes are blocked`() {
        assertEquals(Route.BLOCK, main("file:///sdcard/x"))
        assertEquals(Route.BLOCK, main("content://com.android.contacts/x"))
        assertEquals(Route.BLOCK, main("JavaScript:alert(1)"))
    }

    @Test
    fun `iframe navigations are never redirected`() {
        assertEquals(Route.STAY, LinkPolicy.route("https://vite.dev/", isMainFrame = false))
        assertEquals(Route.STAY, LinkPolicy.route("mailto:a@b.c", isMainFrame = false))
    }

    @Test
    fun `host parsing drops userinfo, port and ipv6 brackets survive`() {
        assertEquals("example.com", LinkPolicy.host("https://u:p@Example.com:8443/x"))
        assertEquals("[::1]", LinkPolicy.host("http://[::1]:8080/"))
        assertNull(LinkPolicy.host("mailto:a@b.c"))
    }

    @Test
    fun `an outside web fallback is followed`() {
        assertEquals("https://example.com/x", LinkPolicy.fallbackTarget("https://example.com/x"))
        assertEquals("http://example.com/", LinkPolicy.fallbackTarget(" http://example.com/ "))
    }

    @Test
    fun `a missing, internal or non-web fallback is dropped`() {
        assertNull(LinkPolicy.fallbackTarget(null))
        assertNull(LinkPolicy.fallbackTarget(""))
        assertNull(LinkPolicy.fallbackTarget("https://appassets.androidplatform.net/index.html"))
        assertNull(LinkPolicy.fallbackTarget("intent://x#Intent;end"))
        assertNull(LinkPolicy.fallbackTarget("market://details?id=x"))
        assertNull(LinkPolicy.fallbackTarget("javascript:alert(1)"))
        assertNull(LinkPolicy.fallbackTarget("file:///sdcard/x"))
    }
}
