# Epson ePOS2 SDK setup

The Android POS app's printer discovery/printing feature has a generic,
brand-agnostic driver framework (`app/src/main/java/com/zedread/pos/printing/driver/`)
with Epson receipt printers as the first concrete implementation
(`app/src/main/java/com/zedread/pos/printing/epson/EpsonPrinterDriver.kt`).

That Epson driver is written against Epson's own **ePOS2 Android SDK**
(`com.epson.epos2.*`) — a proprietary AAR distributed by Epson under their own
developer-portal EULA. It is **not** on Maven Central and cannot be fetched
automatically; you need to add it yourself before the app will build.

## Steps

1. Go to Epson's developer portal (search "Epson ePOS SDK for Android" —
   typically under Epson's Connect/POS SDK developer site) and accept the
   SDK's license agreement to download it.
2. Unzip the download. Copy the SDK's AAR file(s) — typically named something
   like `ePOS2.aar` — into `app/libs/` in this project (the directory already
   exists with a `.gitkeep`; drop the real AAR(s) alongside it).
3. Re-sync Gradle. `app/build.gradle.kts` already declares
   `implementation(fileTree(mapOf("dir" to "libs", "include" to listOf("*.aar"))))`,
   which picks up any AAR placed in `app/libs/` automatically — no further
   build file edits are needed.
4. `app/libs/*.aar` is gitignored — the proprietary binary should never be
   committed to this repository. Every developer/CI machine that needs to
   build the app needs its own copy placed the same way.

## What breaks without it (expected, not a bug)

Until the AAR is present, exactly one file fails to compile:
`printing/epson/EpsonPrinterDriver.kt`, with unresolved `com.epson.epos2.*`
imports. Every other file in the printer feature (Room storage, the driver
abstraction, the generic Bluetooth/network drivers, the Printers screen, the
payment "Print receipt" wiring) has no dependency on the Epson SDK and builds
fine on its own.

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

Once the AAR is in place and the app builds:

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
