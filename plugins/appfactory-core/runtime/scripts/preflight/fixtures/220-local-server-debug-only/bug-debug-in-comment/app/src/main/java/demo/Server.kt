package demo
import io.ktor.server.cio.CIO
import io.ktor.server.engine.embeddedServer
class Server {
    // TODO gate on BuildConfig.DEBUG before shipping
    fun start() {
        embeddedServer(CIO, host = "127.0.0.1", port = 8765) {}.start(wait = false)
    }
}
