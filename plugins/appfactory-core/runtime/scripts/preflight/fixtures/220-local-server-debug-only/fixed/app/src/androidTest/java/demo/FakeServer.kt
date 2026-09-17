package demo
import java.net.ServerSocket
// Test-only listener: not shipped, so no gate is required.
class FakeServer { fun open() = ServerSocket(0) }
