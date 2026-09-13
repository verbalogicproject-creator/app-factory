package {{APPLICATION_ID}}

import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import {{APPLICATION_ID}}.bridge.NativeBridge
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The rung that answers "does the web shell actually work end to end": page
 * loads, JS runs, and the loopback HTTP surface a harness would actually drive
 * reports the page as up. Run against the test bundle at tests/data/web/
 * (scaffold.py --kind web-shell --web-dir tests/data/web), whose index.html sets
 * <title>SAG Web Shell Test Bundle</title> for exactly this assertion.
 */
@RunWith(AndroidJUnit4::class)
class WebShellTest {

    @Test
    fun pageLoadsAndHealthReportsItOverHttp() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            waitForPageLoad()

            val titleLatch = CountDownLatch(1)
            var title: String? = null
            scenario.onActivity {
                NativeBridge.webView?.evaluateJavascript("document.title") { value ->
                    // evaluateJavascript's callback value is JSON-quoted.
                    title = value?.trim('"')
                    titleLatch.countDown()
                }
            }
            assertTrue("document.title callback never fired", titleLatch.await(10, TimeUnit.SECONDS))
            assertEquals(EXPECTED_TITLE, title)

            val (status, body) = httpGetWithRetry("http://127.0.0.1:${BuildConfig.SAG_PORT}/__sag/health")
            assertEquals(200, status)
            assertTrue("expected pageLoaded:true in $body", body.contains("\"pageLoaded\":true"))
        }
    }

    private fun waitForPageLoad(timeoutMs: Long = 15_000) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (!NativeBridge.pageLoaded && System.currentTimeMillis() < deadline) {
            Thread.sleep(100)
        }
        assertTrue("page never finished loading within ${timeoutMs}ms", NativeBridge.pageLoaded)
    }

    /** The foreground service (and its embedded server) starts asynchronously from
     * MainActivity.onCreate(), so the first connection attempt can race it losing. */
    private fun httpGetWithRetry(url: String, attempts: Int = 20, delayMs: Long = 250): Pair<Int, String> {
        var lastError: Exception? = null
        repeat(attempts) {
            try {
                return httpGet(url)
            } catch (e: java.io.IOException) {
                lastError = e
                Thread.sleep(delayMs)
            }
        }
        throw lastError ?: IllegalStateException("unreachable")
    }

    private fun httpGet(url: String): Pair<Int, String> {
        val conn = URL(url).openConnection() as HttpURLConnection
        return try {
            conn.connectTimeout = 5_000
            conn.readTimeout = 5_000
            val code = conn.responseCode
            val stream = if (code < 400) conn.inputStream else conn.errorStream
            code to (stream?.bufferedReader()?.readText() ?: "")
        } finally {
            conn.disconnect()
        }
    }

    private companion object {
        const val EXPECTED_TITLE = "SAG Web Shell Test Bundle"
    }
}
