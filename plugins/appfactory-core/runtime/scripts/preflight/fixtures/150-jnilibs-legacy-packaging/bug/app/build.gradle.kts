android {
    namespace = "com.example.native"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.example.native"
        minSdk = 28
        targetSdk = 36
    }

    // Packaging block absent -- the .so files ship in the APK but AGP does not
    // extract them at install time, so any directory-scanning loader finds
    // nothing at runtime.
}
