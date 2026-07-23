plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.hilt)
    alias(libs.plugins.ksp)
}

// Epson ePOS2 SDK — proprietary, NOT on Maven Central (Epson gates it behind their own
// developer-portal EULA, so it can't be resolved from a repository or bundled in this
// repo — see pos-android/PRINTER_SDK_SETUP.md). It ships as a plain ePOS2.jar (not an
// AAR) plus per-ABI native .so libraries. CI never has any of this either, so the
// Epson-specific source (EpsonPrinterDriver.kt/EpsonPrinterModule.kt, which import
// com.epson.epos2.*) lives in src/epson/java/ instead of the default src/main/java/ —
// a directory Gradle never scans on its own — and is only added as a source root below
// when the jar is present. Kotlin (and KSP, for the Hilt binding) never sees those
// files at all otherwise, rather than being left to fail the whole module's build —
// Kotlin compiles a module as one unit, so one file failing to resolve its imports
// fails every other file's compilation too, not just its own. Once a developer adds
// ePOS2.jar to app/libs/, this flips to true automatically and the Epson driver is
// included with no other code changes needed.
val epsonSdkAvailable = fileTree("libs") { include("*.jar", "*.aar") }.files.isNotEmpty()

android {
    namespace = "com.zedread.pos"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.zedread.pos"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // API base URL baked in at build time — override in local.properties for staging
        // Trailing slash required by Retrofit for relative URL resolution.
        buildConfigField("String", "API_BASE_URL", "\"https://pos-backend-production-c3d3.up.railway.app/\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    sourceSets {
        getByName("main") {
            if (epsonSdkAvailable) {
                java.srcDir("src/epson/java")
            }
        }
    }
}

dependencies {
    // Core
    implementation(libs.androidx.core.ktx)
    implementation(libs.lifecycle.runtime.ktx)
    implementation(libs.lifecycle.runtime.compose)
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.coroutines.android)

    // Compose
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons)
    implementation(libs.compose.activity)
    implementation(libs.compose.navigation)
    implementation(libs.compose.hilt.navigation)
    debugImplementation(libs.compose.ui.tooling)

    // Hilt
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)

    // Room
    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)

    // Retrofit + Moshi
    implementation(libs.retrofit)
    implementation(libs.retrofit.moshi)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.moshi)
    ksp(libs.moshi.codegen)

    // DataStore
    implementation(libs.datastore.preferences)

    // Image loading
    implementation(libs.coil.compose)

    // WorkManager (offline write-queue — Android POS Phase 2)
    implementation(libs.work.runtime.ktx)
    implementation(libs.hilt.work)
    ksp(libs.hilt.work.compiler)

    // Epson ePOS2 SDK — see the epsonSdkAvailable comment above. fileTree reads the
    // local filesystem directly, so this does NOT need a repository entry in
    // settings.gradle.kts. Only added when ePOS2.jar is actually present.
    if (epsonSdkAvailable) {
        implementation(fileTree(mapOf("dir" to "libs", "include" to listOf("*.jar", "*.aar"))))
    }

    // Test
    testImplementation(libs.junit)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.mockito.core)
    androidTestImplementation(libs.androidx.test.ext)
    androidTestImplementation(libs.room.testing)
}
