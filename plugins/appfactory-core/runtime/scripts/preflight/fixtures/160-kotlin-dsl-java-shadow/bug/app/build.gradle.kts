import java.util.Properties

android {
    defaultConfig {
        // Fully-qualified reference to java.net.URI in a .kts script.
        // In a Kotlin DSL script `java` resolves to the Java plugin extension,
        // not the java.* package, so this line fails to compile with
        // "Unresolved reference 'net'".
        val issue = java.net.URI("https://example.com/issue")
    }
}
