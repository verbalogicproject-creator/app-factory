android {
    namespace = "com.example.native"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.example.native"
        minSdk = 28
        targetSdk = 36
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }
}
