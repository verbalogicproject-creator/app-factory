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
 * loads, its ASSETS resolve, JS runs, and the loopback HTTP surface a harness would
 * actually drive reports the page as up. Run against the test bundle at tests/data/web/
 * (scaffold.py --kind web-shell --web-dir tests/data/web).
 *
 * The asset assertions are the load-bearing ones and they are newer than the rest.
 * document.title is read straight out of the HTML, so it is correct even when every
 * referenced script and stylesheet 404s -- which is exactly what happened while the
 * asset handler was mounted below the bundle root: a blank page that passed all 21
 * static checks and this test. The fixture therefore references its JS and CSS by
 * ABSOLUTE, hashed paths the way a bundler does, and the two assertions below fail if
 * either 404s.
 */
@RunWith(AndroidJUnit4::class)
class WebShellTest {

    @Test
    fun pageLoadsAndHealthReportsItOverHttp() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            waitForPageLoad()

            // evaluateJavascript's result is JSON-encoded, so a string comes back quoted.
            assertEquals("\"$EXPECTED_TITLE\"", evaluateJs(scenario, "document.title"))

            // Set by /assets/app-<hash>.js. Undefined if that absolute path did not resolve.
            assertEquals(
                "the bundle's absolute-path script did not run -- asset handler mount point?",
                "true",
                evaluateJs(scenario, "window.__bundleAssetsResolved === true"),
            )

            // Declared in /assets/style-<hash>.css. The UA default would be rgb(0, 0, 0).
            assertEquals(
                "the bundle's absolute-path stylesheet did not apply",
                "\"rgb(0, 128, 64)\"",
                evaluateJs(
                    scenario,
                    "getComputedStyle(document.getElementById('status')).color",
                ),
            )

            val (status, body) = httpGetWithRetry("http://127.0.0.1:${BuildConfig.SAG_PORT}/__sag/health")
            assertEquals(200, status)
            assertTrue("expected pageLoaded:true in $body", body.contains("\"pageLoaded\":true"))
        }
    }

    /** Runs [script] on the WebView's thread and returns evaluateJavascript's raw,
     * JSON-encoded result -- so a string comes back quoted. */
    private fun evaluateJs(
        scenario: ActivityScenario<MainActivity>,
        script: String,
    ): String? {
        val latch = CountDownLatch(1)
        var result: String? = null
        scenario.onActivity {
            NativeBridge.webView?.evaluateJavascript(script) { value ->
                result = value
                latch.countDown()
            }
        }
        assertTrue("evaluateJavascript callback never fired for: $script", latch.await(10, TimeUnit.SECONDS))
        return result
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
