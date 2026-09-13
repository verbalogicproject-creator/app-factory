package {{APPLICATION_ID}}.bridge

import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pure-JVM coverage for the id-correlation and timeout behaviour CommandServer
 * and NativeBridge share via [PendingReplies]. No Android class appears anywhere
 * in this file or in PendingReplies itself, so this runs as an ordinary unit test
 * -- no Robolectric, no emulator, no androidTest APK.
 */
class PendingRepliesTest {

    @Test
    fun `resolve delivers the result to the matching id only`() = runBlocking {
        val replies = PendingReplies()
        val a = replies.register("a")
        val b = replies.register("b")

        assertTrue(replies.resolve("a", JsonPrimitive("for-a")))

        assertEquals(JsonPrimitive("for-a"), a.await())
        assertFalse(b.isCompleted)
    }

    @Test
    fun `resolve for an unknown id is reported as not delivered, not thrown`() {
        val replies = PendingReplies()
        assertFalse(replies.resolve("never-registered", JsonPrimitive("x")))
    }

    @Test
    fun `an unanswered id times out rather than hanging forever`() = runBlocking {
        val replies = PendingReplies()
        val deferred = replies.register("slow")
        val result = withTimeoutOrNull(50) { deferred.await() }
        assertNull(result)
    }

    @Test
    fun `cancel drops a registration so a late reply is a no-op`() {
        val replies = PendingReplies()
        replies.register("late")
        replies.cancel("late")
        assertFalse(replies.resolve("late", JsonPrimitive("too-late")))
    }

    @Test
    fun `size reflects outstanding registrations`() {
        val replies = PendingReplies()
        replies.register("one")
        replies.register("two")
        assertEquals(2, replies.size)
        replies.resolve("one", JsonPrimitive(1))
        assertEquals(1, replies.size)
    }
}
