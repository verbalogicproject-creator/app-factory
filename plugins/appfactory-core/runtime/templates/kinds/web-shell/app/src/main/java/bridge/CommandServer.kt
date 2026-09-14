package {{APPLICATION_ID}}.bridge

import android.content.Context
import android.os.Handler
import android.os.Looper
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.call
import io.ktor.server.cio.CIO
import io.ktor.server.engine.EmbeddedServer
import io.ktor.server.engine.embeddedServer
import io.ktor.server.request.receiveText
import io.ktor.server.response.respondText
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.routing.routing
import java.io.File
import java.util.UUID
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import {{APPLICATION_ID}}.BuildConfig

/**
 * The 127.0.0.1-only HTTP half of the command/observe channel.
 *
 *   POST /__sag/command   body: a SynthCommand JSON object, or a JSON array of them.
 *                          Forwards each to the page via NativeBridge/evaluateJavascript,
 *                          waits up to 3s for the matching AndroidBridge.postResult(id),
 *                          and returns it. A single command that times out responds 504
 *                          {"error":"no page answered"}; inside a batch the same shape is
 *                          embedded per-item instead (a batch response is always 200,
 *                          since one HTTP status cannot describe N independent outcomes).
 *   GET  /__sag/observe    ?tail=N -> the last N JSONL lines of
 *                          filesDir/sag/audio-observed.jsonl, as a JSON array.
 *   GET  /__sag/health     {"pkg","version","sha","pageLoaded","pageFailures"}.
 *   GET  /__sag/diagnostics  ?failures=true -> what the page reported: console messages,
 *                            failed resource loads, HTTP errors. A blank WebView is
 *                            otherwise indistinguishable from a working one from out here.
 *   GET  /__sag/dom        what the page actually RENDERED -- readyState, the mount
 *                            element's child count, the head of its innerHTML, the
 *                            computed body background. Needs nothing from the page, so it
 *                            works against a bundle that has never heard of this shell.
 *
 * BINDS 127.0.0.1 ONLY, deliberately, never 0.0.0.0: this exists for a local
 * harness (adb forward, or a process on the same device) to drive the page, not
 * for another device on the same network to reach in. See
 * res/xml/network_security_config.xml, which permits cleartext for 127.0.0.1 and
 * localhost only -- the other half of the same boundary.
 */
class CommandServer(
    // NOT named `context`: inside Ktor's `routing { get { ... } }` lambdas the receiver
    // already provides a `context` (the call's PipelineContext), which silently shadows a
    // constructor property of that name. The symptom is "Unresolved reference 'filesDir'"
    // pointing at a line that looks obviously correct. Only a compiler finds this.
    private val appContext: Context,
    private val port: Int = BuildConfig.SAG_PORT,
) {
    private val json = Json { ignoreUnknownKeys = true }
    // evaluateJavascript MUST run on the main thread; Ktor/CIO runs route handlers
    // on its own dispatcher, so the actual JS call is posted across rather than
    // invoked directly.
    private val mainHandler = Handler(Looper.getMainLooper())
    // EmbeddedServer, not ApplicationEngine: Ktor 3 changed what embeddedServer()
    // returns, and the old type still exists, so the mismatch is a compile error
    // rather than anything subtler. The version it replaced (2.3.11) compiled and
    // then died at launch with NoSuchMethodError -- it was built against
    // kotlinx-coroutines 1.7/1.8 and this lattice forces 1.9, where the internal
    // class Ktor's event system reaches for was deleted. Gradle resolved that
    // conflict silently and nothing on the static side could see it.
    private var engine: EmbeddedServer<*, *>? = null

    fun start() {
        if (engine != null) return
        engine = embeddedServer(CIO, host = "127.0.0.1", port = port) {
            routing {
                post("/__sag/command") {
                    val bodyText = call.receiveText()
                    val element = runCatching { json.parseToJsonElement(bodyText) }.getOrNull()
                    if (element == null) {
                        call.respondText(
                            """{"error":"invalid json"}""",
                            ContentType.Application.Json,
                            HttpStatusCode.BadRequest,
                        )
                        return@post
                    }
                    if (element is JsonArray) {
                        val results = element.map { dispatchOne(it) }
                        call.respondText(JsonArray(results).toString(), ContentType.Application.Json)
                    } else {
                        val result = dispatchOne(element)
                        val timedOut = (result as? JsonObject)
                            ?.get("error")?.let { it as? JsonPrimitive }
                            ?.content == NO_ANSWER
                        call.respondText(
                            result.toString(),
                            ContentType.Application.Json,
                            if (timedOut) HttpStatusCode.GatewayTimeout else HttpStatusCode.OK,
                        )
                    }
                }
                get("/__sag/observe") {
                    val tail = call.request.queryParameters["tail"]?.toIntOrNull()?.coerceAtLeast(0) ?: 50
                    val file = File(appContext.filesDir, "sag/audio-observed.jsonl")
                    val lines = if (file.isFile) file.readLines().takeLast(tail) else emptyList()
                    call.respondText("[" + lines.joinToString(",") + "]", ContentType.Application.Json)
                }
                get("/__sag/health") {
                    val body = buildJsonObject {
                        put("pkg", appContext.packageName)
                        put("version", BuildConfig.VERSION_NAME)
                        put("sha", BuildConfig.GIT_SHA)
                        put("pageLoaded", NativeBridge.pageLoaded)
                        // pageLoaded is true for a page whose every asset 404'd. This is
                        // the number that says whether it actually works.
                        put("pageFailures", NativeBridge.pageLog.failures().size)
                    }
                    call.respondText(body.toString(), ContentType.Application.Json)
                }
                get("/__sag/diagnostics") {
                    val onlyFailures = call.request.queryParameters["failures"] == "true"
                    val entries = NativeBridge.pageLog.let {
                        if (onlyFailures) it.failures() else it.snapshot()
                    }
                    val body = buildJsonArray {
                        entries.forEach { e ->
                            add(
                                buildJsonObject {
                                    put("kind", e.kind.wire)
                                    put("message", e.message)
                                    put("source", e.source ?: "")
                                    put("line", e.line ?: -1)
                                },
                            )
                        }
                    }
                    call.respondText(body.toString(), ContentType.Application.Json)
                }
                get("/__sag/dom") {
                    // Interpolated into a JS string literal below, so it is restricted
                    // to an identifier rather than escaped -- a smaller thing to get right.
                    val mount = call.request.queryParameters["mount"]
                        ?.takeIf { it.isNotEmpty() && it.all { c -> c.isLetterOrDigit() || c == '_' || c == '-' } }
                        ?: "root"
                    val result = evaluateInPage(domProbe(mount))
                    call.respondText(result ?: "null", ContentType.Application.Json)
                }
            }
        }.also { it.start(wait = false) }
    }

    fun stop() {
        engine?.stop(gracePeriodMillis = 200, timeoutMillis = 1000)
        engine = null
    }

    /**
     * Evaluates [script] in the page and returns evaluateJavascript's JSON-encoded result.
     *
     * Unlike [dispatchOne] this asks nothing of the page -- no __sagNative, no bridge, no
     * cooperation of any kind -- which is the whole point when the page itself is the
     * suspect. A bundle that has never heard of this shell still answers.
     */
    private suspend fun evaluateInPage(script: String): String? {
        val done = CompletableDeferred<String?>()
        mainHandler.post {
            val webView = NativeBridge.webView
            if (webView == null) {
                done.complete(null)
            } else {
                webView.evaluateJavascript(script) { value -> done.complete(value) }
            }
        }
        return withTimeoutOrNull(3_000) { done.await() }
    }

    /**
     * Answers "did anything render", which is the question a blank screen actually poses.
     * onPageFinished, a 200 on every asset and an empty console are all compatible with a
     * page that mounted nothing.
     */
    private fun domProbe(mountId: String): String = """
        (function () {
          var mount = document.getElementById(${'"'}$mountId${'"'});
          var body = document.body;
          return {
            readyState: document.readyState,
            title: document.title,
            url: location.href,
            mountId: ${'"'}$mountId${'"'},
            mountPresent: !!mount,
            mountChildren: mount ? mount.childElementCount : -1,
            mountHtmlLength: mount ? mount.innerHTML.length : -1,
            mountHtmlHead: mount ? mount.innerHTML.slice(0, 400) : "",
            bodyChildren: body ? body.childElementCount : -1,
            bodyBackground: body ? getComputedStyle(body).backgroundColor : "",
            bodyScrollHeight: body ? body.scrollHeight : -1,
            viewport: window.innerWidth + "x" + window.innerHeight,
            scripts: Array.prototype.map.call(document.scripts, function (s) {
              return (s.src || "inline") + (s.type ? " [" + s.type + "]" : "");
            }),
            stylesheets: document.styleSheets.length
          };
        })()
    """.trimIndent()

    /** Delivers one command, correlates the reply by id, and times out at 3s. */
    private suspend fun dispatchOne(command: JsonElement): JsonElement {
        val id = UUID.randomUUID().toString()
        val deferred = NativeBridge.register(id)
        val envelope = buildJsonObject {
            put("id", id)
            put("command", command)
        }
        mainHandler.post {
            // U+2028/U+2029 are valid inside a JSON string but were invalid inside a
            // JS string literal before ES2019 -- stripped defensively since the
            // command payload is caller-controlled and this is not parsed as JSON by
            // the WebView, it is evaluated as a JS expression.
            val js = envelope.toString().replace(" ", "").replace(" ", "")
            NativeBridge.webView?.evaluateJavascript(
                "window.__sagNative && window.__sagNative.deliver($js)",
                null,
            )
        }
        val result = withTimeoutOrNull(3_000) { deferred.await() }
        if (result == null) {
            NativeBridge.cancel(id)
            return buildJsonObject { put("error", NO_ANSWER) }
        }
        return result
    }

    private companion object {
        const val NO_ANSWER = "no page answered"
    }
}
