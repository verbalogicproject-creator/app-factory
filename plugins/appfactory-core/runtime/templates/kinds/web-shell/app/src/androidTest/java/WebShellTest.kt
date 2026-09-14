package {{APPLICATION_ID}}

import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import {{APPLICATION_ID}}.bridge.NativeBridge
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The rung that answers "does the web shell actually work end to end" -- and the only one
 * that can, because every cheaper rung is compatible with a blank screen.
 *
 * Three separate bugs reached a green ladder and a white rectangle before these assertions
 * existed: an asset handler mounted below the bundle root, a shell with no way to report a
 * page failure, and a WebView measured AT_MOST so every viewport unit resolved to 0. None
 * of them failed a Gradle task. All three are covered below.
 *
 * THE ASSERTIONS HERE ARE BUNDLE-AGNOSTIC ON PURPOSE. An earlier version asserted the test
 * fixture's <title> and the globals the fixture happens to set, so the first real project
 * generated from this template failed its own instrumented test on the first run -- with
 * nothing wrong with the app. A generated test that cannot pass is worse than no test: it
 * teaches the reader to ignore the suite. The title now comes from the bundle that was
 * scaffolded, and the fixture-only checks are skipped when the fixture is not in use.
 */
@RunWith(AndroidJUnit4::class)
class WebShellTest {

    @Test
    fun pageLoadsAndHealthReportsItOverHttp() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            waitForPageLoad()

            // evaluateJavascript's result is JSON-encoded, so a string comes back quoted.
            assertEquals("\"$EXPECTED_TITLE\"", evaluateJs(scenario, "document.title"))

            val (status, body) = httpGetWithRetry(sag("/__sag/health"))
            assertEquals(200, status)
            val health = JSONObject(body)
            assertTrue("expected pageLoaded:true in $body", health.getBoolean("pageLoaded"))

            // The general white-screen guard: pageLoaded only says navigation finished.
            if (health.getInt("pageFailures") != 0) {
                val (_, failures) = httpGet(sag("/__sag/diagnostics?failures=true"))
                throw AssertionError("the page reported failures: $failures")
            }
        }
    }

    @Test
    fun theBundleRendersIntoANonZeroBox() {
        ActivityScenario.launch(MainActivity::class.java).use {
            waitForPageLoad()
            val dom = JSONObject(httpGetWithRetry(sag("/__sag/dom")).second)
            val page = dom.getJSONObject("page")
            val host = dom.getJSONObject("host")

            assertTrue("no mount element in the page", page.getBoolean("mountPresent"))
            assertTrue(
                "the bundle mounted nothing: ${page.getInt("mountHtmlLength")} chars of HTML",
                page.getInt("mountChildren") > 0,
            )

            // The layout regression, stated directly. The WebView was once measured
            // AT_MOST, which made every viewport unit -- including 100% -- resolve to 0,
            // so a correct page laid out into a box of no height.
            assertTrue("the hosting View has no height: ${host.getInt("height")}", host.getInt("height") > 0)
            val vh = page.getJSONObject("units").getDouble("100vh")
            assertTrue("100vh resolved to $vh -- the WebView has no usable viewport", vh > 0)
            assertTrue(
                "the page laid out into zero height: scrollHeight ${page.getInt("bodyScrollHeight")}",
                page.getInt("bodyScrollHeight") > 0,
            )
        }
    }

    /**
     * Fixture-only. tests/data/web references its JS and CSS by ABSOLUTE, hashed paths the
     * way a bundler does, so these two catch a wrongly-mounted asset handler specifically.
     * A real bundle is covered by pageFailures and the render assertions above instead.
     */
    @Test
    fun fixtureAbsoluteAssetPathsResolve() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            waitForPageLoad()
            val marker = evaluateJs(scenario, "typeof window.__bundleAssetsResolved")
            assumeTrue("not the test fixture; skipping its bundle-specific checks", marker == "\"boolean\"")

            assertEquals(
                "the fixture's absolute-path script did not run -- asset handler mount point?",
                "true",
                evaluateJs(scenario, "window.__bundleAssetsResolved === true"),
            )
            assertEquals(
                "the fixture's absolute-path stylesheet did not apply",
                "\"rgb(0, 128, 64)\"",
                evaluateJs(scenario, "getComputedStyle(document.getElementById('status')).color"),
            )
        }
    }

    /** Runs [script] in the page and returns evaluateJavascript's raw, JSON-encoded result. */
    private fun evaluateJs(scenario: ActivityScenario<MainActivity>, script: String): String? {
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

    private fun sag(path: String) = "http://127.0.0.1:${BuildConfig.SAG_PORT}$path"

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
        /** Substituted by scaffold.py from the scaffolded bundle's own index.html. */
        const val EXPECTED_TITLE = "{{WEB_TITLE}}"
    }
}
