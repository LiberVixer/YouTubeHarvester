import java.util.Properties
import java.security.MessageDigest

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.devtools.ksp")
    id("androidx.room")
}

val ytDlp = Properties().apply {
    rootProject.file("runtime.properties").inputStream().use { load(it) }
}

val upstreamFfmpeg = configurations.create("upstreamFfmpeg") { isTransitive = false }
val upstreamLibrary = configurations.create("upstreamLibrary") { isTransitive = false }
val patchedLibrary = layout.buildDirectory.file("runtime/library-0.18.1-quickjs-2026-06-04.aar")
val prepareLibrary = tasks.register<Exec>("prepareLibrary") {
    inputs.files(upstreamLibrary)
    inputs.file(rootProject.file("native/quickjs-2026-06-04-16k.zip"))
    inputs.file(rootProject.file("scripts/patch_quickjs.py"))
    inputs.file(rootProject.file("scripts/rebuild_quickjs.py"))
    outputs.file(patchedLibrary)
    doFirst {
        commandLine("python3", rootProject.file("scripts/patch_quickjs.py"),
            "--upstream", upstreamLibrary.singleFile,
            "--replacements", rootProject.file("native/quickjs-2026-06-04-16k.zip"),
            "--output", patchedLibrary.get().asFile,
            "--sha256", "1d12127c7fdbaafa64fe01ad1b1380179c777d9e6c4abe8b8b912e88074a10df")
    }
}
val patchedFfmpeg = layout.buildDirectory.file("runtime/ffmpeg-0.18.1-16k.aar")
val prepareFfmpeg = tasks.register<Exec>("prepareFfmpeg") {
    inputs.files(upstreamFfmpeg)
    inputs.file(rootProject.file("native/webp-1.6.0-16k.zip"))
    inputs.file(rootProject.file("scripts/patch_ffmpeg.py"))
    outputs.file(patchedFfmpeg)
    doFirst {
        commandLine("python3", rootProject.file("scripts/patch_ffmpeg.py"),
            "--upstream", upstreamFfmpeg.singleFile,
            "--replacements", rootProject.file("native/webp-1.6.0-16k.zip"),
            "--output", patchedFfmpeg.get().asFile,
            "--sha256", "cc5adfc8ac62b4213f044c931f55d4275a4c3f69e24240a19ef8a93c7a477162")
    }
}

android {
    namespace = "com.liberivixer.youtubeharvester"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.liberivixer.youtubeharvester"
        minSdk = 26
        targetSdk = 37
        versionCode = 120100
        versionName = "1.2.1"
        buildConfigField("String", "YTDLP_VERSION", "\"${ytDlp.getProperty("version")}\"")
        buildConfigField("String", "YTDLP_SHA256", "\"${ytDlp.getProperty("sha256")}\"")

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables.useSupportLibrary = true
    }

    signingConfigs {
        val keyPath = providers.environmentVariable("YTH_ANDROID_KEYSTORE").orNull
        if (!keyPath.isNullOrBlank()) {
            create("release") {
                storeFile = file(keyPath)
                storePassword = providers.environmentVariable("YTH_ANDROID_STORE_PASSWORD").get()
                keyAlias = providers.environmentVariable("YTH_ANDROID_KEY_ALIAS").get()
                keyPassword = providers.environmentVariable("YTH_ANDROID_KEY_PASSWORD").get()
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isDebuggable = false
            isMinifyEnabled = true
            isShrinkResources = true
            signingConfig = signingConfigs.findByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    // Private beta update only; retain the tester certificate without deleting app data.
    buildTypes.create("legacyBeta") {
        initWith(buildTypes.getByName("release"))
        signingConfig = signingConfigs.getByName("debug")
        matchingFallbacks += "release"
    }

    // Documentation capture has its own UID and never opens tester databases.
    buildTypes.create("screenshots") {
        initWith(buildTypes.getByName("debug"))
        applicationIdSuffix = ".screenshots"
        versionNameSuffix = ""
        matchingFallbacks += "debug"
    }

    // Isolated non-debuggable target; shared test API keeps are QA-only.
    buildTypes.create("migrationQa") {
        initWith(buildTypes.getByName("release"))
        applicationIdSuffix = ".migrationqa"
        versionNameSuffix = "-migration-qa"
        signingConfig = null
        matchingFallbacks += "release"
        proguardFile("migration-qa-app.pro")
        testProguardFile("migration-qa-test.pro")
    }
    val requestedTestBuild = providers.gradleProperty("ythTestBuildType").orElse("debug").get()
    require(requestedTestBuild in setOf("debug", "migrationQa", "screenshots"))
    testBuildType = requestedTestBuild
    if (requestedTestBuild == "migrationQa") {
        sourceSets.getByName("androidTest").manifest.srcFile("src/migrationQaAndroidTest/AndroidManifest.xml")
    }

    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "armeabi-v7a", "x86", "x86_64")
            isUniversalApk = false
        }
    }

    bundle {
        language {
            enableSplit = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
        jniLibs.useLegacyPackaging = true
        jniLibs.keepDebugSymbols += "**/*.zip.so"
    }

    room {
        schemaDirectory("$projectDir/schemas")
    }
}

val bundledYtDlp = layout.projectDirectory.file("src/main/res/raw/ytdlp")
val verifyBundledRuntime = tasks.register("verifyBundledRuntime") {
    inputs.file(bundledYtDlp)
    inputs.property("sha256", ytDlp.getProperty("sha256"))
    doLast {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(bundledYtDlp.asFile.readBytes()).joinToString("") { "%02x".format(it) }
        check(digest == ytDlp.getProperty("sha256")) { "Bundled yt-dlp SHA-256 mismatch" }
    }
}
tasks.named("preBuild").configure { dependsOn(verifyBundledRuntime) }

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.09.00")

    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.core:core-ktx:1.19.1")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.11.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.11.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.datastore:datastore-preferences:1.2.1")
    implementation("androidx.room:room-runtime:2.8.5")
    implementation("androidx.room:room-ktx:2.8.5")
    implementation("androidx.work:work-runtime:2.12.0")
    implementation("io.coil-kt.coil3:coil-compose:3.6.3")
    implementation("io.coil-kt.coil3:coil-network-okhttp:3.6.3")
    add(upstreamLibrary.name, "io.github.junkfood02.youtubedl-android:library:0.18.1")
    implementation(files(patchedLibrary).builtBy(prepareLibrary))
    // File AARs do not carry their Maven transitive dependency graph.
    implementation("io.github.junkfood02.youtubedl-android:common:0.18.1")
    implementation("androidx.appcompat:appcompat:1.8.0")
    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("org.apache.commons:commons-compress:1.28.0")
    implementation("commons-io:commons-io:2.22.0")
    add(upstreamFfmpeg.name, "io.github.junkfood02.youtubedl-android:ffmpeg:0.18.1")
    implementation(files(patchedFfmpeg).builtBy(prepareFfmpeg))
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.22.3"))
    constraints {
        implementation("org.apache.commons:commons-compress:1.28.0") { because("Replace vulnerable runtime archive extraction dependency") }
        implementation("commons-io:commons-io:2.22.0")
    }
    ksp("androidx.room:room-compiler:2.8.5")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20260814")
    testImplementation("androidx.room:room-testing:2.8.5")
    androidTestImplementation("androidx.room:room-testing:2.8.5")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    // Room's migration test serializers must share the app classloader's runtime.
    debugImplementation(platform("org.jetbrains.kotlinx:kotlinx-serialization-bom:1.11.0"))
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
    add("screenshotsImplementation", "androidx.compose.ui:ui-test-manifest")
    add("screenshotsImplementation", platform("org.jetbrains.kotlinx:kotlinx-serialization-bom:1.11.0"))
}
