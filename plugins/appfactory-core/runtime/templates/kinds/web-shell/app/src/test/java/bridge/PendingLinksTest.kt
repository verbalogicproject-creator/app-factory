package {{APPLICATION_ID}}.bridge

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PendingLinksTest {

    @Test
    fun `links queued before the page is ready are all delivered, in order`() {
        val links = PendingLinks()
        links.add("myapp://a")
        links.add("myapp://b")
        assertEquals(listOf("myapp://a", "myapp://b"), links.drain())
    }

    @Test
    fun `a drained link is not delivered twice`() {
        val links = PendingLinks()
        links.add("myapp://a")
        links.drain()
        assertTrue(links.drain().isEmpty())
    }

    @Test
    fun `js string escapes backslash before quote`() {
        assertEquals("'a\\\\\\'b'", PendingLinks.jsString("a\\'b"))
    }

    @Test
    fun `js string cannot be terminated by a line break`() {
        assertEquals("'a\\nb\\rc\\u2028d\\u2029e'", PendingLinks.jsString("a\nb\rc d e"))
    }

    @Test
    fun `plain deep link passes through unchanged`() {
        assertEquals("'myapp://open/x?y=1'", PendingLinks.jsString("myapp://open/x?y=1"))
    }
}
