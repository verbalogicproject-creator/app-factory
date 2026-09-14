package {{APPLICATION_ID}}.bridge

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * PageLog imports nothing from Android, so the bounding and the failure classification --
 * the two things that decide whether a blank page is diagnosable -- are covered here
 * rather than on a device.
 */
class PageLogTest {

    @Test
    fun keepsEntriesInOrder() {
        val log = PageLog()
        log.add(PageLog.Entry(PageLog.Kind.LOG, "first"))
        log.add(PageLog.Entry(PageLog.Kind.ERROR, "second"))
        assertEquals(listOf("first", "second"), log.snapshot().map { it.message })
    }

    @Test
    fun dropsOldestBeyondCapacity() {
        val log = PageLog(capacity = 3)
        (1..5).forEach { log.add(PageLog.Entry(PageLog.Kind.LOG, "m$it")) }
        assertEquals(listOf("m3", "m4", "m5"), log.snapshot().map { it.message })
    }

    @Test
    fun capacityIsNeverExceeded() {
        val log = PageLog(capacity = 2)
        (1..50).forEach { log.add(PageLog.Entry(PageLog.Kind.ERROR, "m$it")) }
        assertEquals(2, log.snapshot().size)
    }

    @Test
    fun onlyFailuresCountAsFailures() {
        val log = PageLog()
        log.add(PageLog.Entry(PageLog.Kind.LOG, "chatter"))
        log.add(PageLog.Entry(PageLog.Kind.WARN, "deprecation"))
        log.add(PageLog.Entry(PageLog.Kind.ERROR, "TypeError"))
        log.add(PageLog.Entry(PageLog.Kind.RESOURCE, "net::ERR_FAILED"))
        log.add(PageLog.Entry(PageLog.Kind.HTTP, "HTTP 404"))
        assertEquals(
            listOf("TypeError", "net::ERR_FAILED", "HTTP 404"),
            log.failures().map { it.message },
        )
    }

    @Test
    fun consoleNoiseIsKeptButNotCounted() {
        // A page that logs on every frame must not make /__sag/health report failures,
        // or the one number a test can assert stops meaning anything.
        val log = PageLog()
        repeat(100) { log.add(PageLog.Entry(PageLog.Kind.LOG, "frame $it")) }
        assertTrue(log.failures().isEmpty())
        assertEquals(100, log.snapshot().size)
    }

    @Test
    fun snapshotIsACopy() {
        val log = PageLog()
        log.add(PageLog.Entry(PageLog.Kind.LOG, "one"))
        val before = log.snapshot()
        log.add(PageLog.Entry(PageLog.Kind.LOG, "two"))
        assertEquals(1, before.size)
    }

    @Test
    fun clearEmptiesIt() {
        val log = PageLog()
        log.add(PageLog.Entry(PageLog.Kind.ERROR, "boom"))
        log.clear()
        assertTrue(log.snapshot().isEmpty())
    }

    @Test
    fun everyKindDeclaresItsWireName() {
        assertEquals(
            listOf("log", "warn", "error", "resource", "http"),
            PageLog.Kind.entries.map { it.wire },
        )
    }
}
