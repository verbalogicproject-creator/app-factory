android {
    namespace = "com.example.native"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.example.native"
        minSdk = 28
        targetSdk = 36
    }

    // TODO: enable jniLibs { useLegacyPackaging = true } once we verify the
    // startup path still finds the backends. A comment is not a setting.
}
