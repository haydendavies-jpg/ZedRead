# Epson ePOS2 SDK setup

The Android POS app's printer discovery/printing feature has a generic,
brand-agnostic driver framework (`app/src/main/java/com/zedread/pos/printing/driver/`)
with Epson receipt printers as the first concrete implementation
(`app/src/epson/java/com/zedread/pos/printing/epson/EpsonPrinterDriver.kt` — note
this lives under `src/epson/`, not the usual `src/main/`, see below for why).

That Epson driver is written against Epson's own **ePOS2 Android SDK**
(`com.epson.epos2.*`) — a proprietary SDK distributed by Epson under their own
developer-portal EULA. It is **not** on Maven Central and cannot be fetched
automatically; you need to add it yourself before the app will build.

The SDK download (e.g. `ePOS_SDK_Android_v2.37.0a`) is a large bundle mostly
made of documentation and samples you don't need to copy anywhere. Only two
things from it matter for this project:

| From the SDK download | Copy to |
|---|---|
| `ePOS2.jar` | `app/libs/ePOS2.jar` |
| `arm64-v8a/`, `armeabi-v7a/`, `x86/`, `x86_64/` folders (native `.so` libs) | `app/src/main/jniLibs/<same folder name>/` |

Everything else in the download — `ePOS_SDK_Android_um_*` (the user manual
PDFs), `ePOS_SDK_Android_Migration_Guide_*`, `ePOS_SDK_Sample_Android`,
`ePOSEasySelect.jar` (an optional printer-picker widget this project doesn't
use — we have our own Printers screen), `EULA.*`, `README.*`, `NOTICE`,
`JSON_Spec*`, `OPOS_CCOs*` (a Windows-only driver installer), and the
`SB-H50`/`TM-DT_Peripherals` docs — is reference material or unrelated
platforms, not needed to build this app.

## Steps

1. Go to Epson's developer portal (search "Epson ePOS SDK for Android" —
   typically under Epson's Connect/POS SDK developer site) and accept the
   SDK's license agreement to download it.
2. Unzip the download. Copy `ePOS2.jar` into `app/libs/` (the directory
   already exists with a `.gitkeep`; drop the real jar alongside it).
3. Copy each of the four ABI folders (`arm64-v8a`, `armeabi-v7a`, `x86`,
   `x86_64`) into `app/src/main/jniLibs/`, keeping the same folder names, so
   you end up with e.g. `app/src/main/jniLibs/arm64-v8a/*.so`
   (`app/src/main/jniLibs/` already exists with a `.gitkeep`).
4. Re-sync Gradle. `app/build.gradle.kts` already declares
   `implementation(fileTree(mapOf("dir" to "libs", "include" to listOf("*.jar", "*.aar"))))`,
   which picks up `ePOS2.jar` in `app/libs/` automatically — no further build
   file edits are needed. `app/src/main/jniLibs/` is AGP's own default
   location for native libraries, so no build file changes are needed for
   those either.
5. Both `app/libs/*.jar` and `app/src/main/jniLibs/**/*.so` are gitignored —
   this proprietary SDK should never be committed to this repository. Every
   developer/CI machine that needs to build the app needs its own copy
   placed the same way.

## What happens without it (nothing breaks)

`app/build.gradle.kts` detects whether a `.jar`/`.aar` file exists in
`app/libs/` (`epsonSdkAvailable`). The Epson driver and its Hilt binding
(`EpsonPrinterDriver.kt`/`EpsonPrinterModule.kt`) live under
`app/src/epson/java/` instead of the default `app/src/main/java/` — a
directory Gradle never scans on its own — and that directory is only added
as a source root when `epsonSdkAvailable` is true. When the SDK is absent,
neither Kotlin nor KSP (Hilt's annotation processor) ever sees those files at
all, rather than leaving them in to fail the whole module's build — Kotlin
compiles a module as one unit, so one file failing to resolve
`com.epson.epos2.*` imports would fail every other file's compilation too,
not just its own. With the SDK absent, the app builds and runs normally with
just the generic Bluetooth/network drivers registered (see
`GenericNetworkPrinterDriver`/`GenericBluetoothPrinterDriver`); dropping
`ePOS2.jar` into `app/libs/` and rebuilding flips `epsonSdkAvailable` to
`true` automatically, compiling in the Epson driver with no other code
changes needed. (The native `.so` libraries in `jniLibs/` aren't part of this
check — they're only consulted at runtime by `ePOS2.jar`'s own code, so their
absence can't fail a build, only a device run once the jar is present.)

## Permission decisions already made

- `BLUETOOTH_SCAN` is declared with `android:usesPermissionFlags="neverForLocation"`
  — the app never derives physical location from a Bluetooth scan, only a
  device's identity/address, so this waives the API 31+ location-permission
  requirement instead of also requesting it on modern devices.
- `ACCESS_FINE_LOCATION` (`android:maxSdkVersion="30"`) is still declared for
  API < 31, where classic Bluetooth discovery — and Epson's own SDK on those
  levels — requires it regardless of the flag above.
- `PrintersScreen`'s discovery dialog requests `ACCESS_FINE_LOCATION` at
  runtime on API < 31 before starting a scan (the first runtime permission
  request in this app). If you're testing on an older device and discovery
  silently finds nothing, check that permission was actually granted.

## Verifying against real hardware

Once the SDK is in place and the app builds:

1. Open **Settings → Printers** on the device, tap **+** to discover.
2. On a real Epson network printer on the same LAN/subnet, confirm it shows
   up with the correct MAC/IP within a few seconds, and that **Add** saves it
   (enabled by default).
3. Toggle it off/on and restart the app — the enabled state should persist.
4. Change the printer's IP (renew its DHCP lease, or move it to a different
   access point), then complete a sale and tap **Print receipt** on the Done
   screen — it should still print via the automatic re-discover-by-MAC retry,
   and the saved row's IP should update (visible as the row's subtitle on the
   Printers screen).
5. Power the printer off and try **Test print** — it should fail cleanly
   (a message on the Printers screen), not crash the app.
6. Repeat with a second, non-Epson network printer (any raw ESC/POS printer
   listening on TCP port 9100) — it can't be *discovered* yet (see the open
   gap noted in `GenericNetworkPrinterDriver`'s KDoc), but can still be
   verified end-to-end once a row for it exists in the `saved_printers` table.
