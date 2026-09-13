package {{APPLICATION_ID}}.bridge

import android.content.Context
import android.os.Handler
import android.os.Looper
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.call
import io.ktor.server.cio.CIO
import io.ktor.server.engine.ApplicationEngine
import io.ktor.server.engine.embeddedServer
import io.ktor.server.request.receiveText
import io.ktor.server.response.respondText
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.routing.routing
import java.io.File
import java.util.UUID
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
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
 *   GET  /__sag/health     {"pkg","version","sha","pageLoaded"}.
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
    private var engine: ApplicationEngine? = null

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
                    }
                    call.respondText(body.toString(), ContentType.Application.Json)
                }
            }
        }.also { it.start(wait = false) }
    }

    fun stop() {
        engine?.stop(gracePeriodMillis = 200, timeoutMillis = 1000)
        engine = null
    }

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
