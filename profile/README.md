# LegacyDroid

**LegacyDroid** is a custom Android ROM project based on Android 14.

## Getting Started

### 1. Initialize the source

```bash
repo init -u https://github.com/LegacyDroid/android_manifest.git \
    -b legacydroid-14 \
    --git-lfs
```

### 2. Sync the source

```bash
repo sync
```

Depending on your connection and hardware, the initial sync may take a while.

## Build Preparation

### Magisk

The ROM requires the latest Magisk APK at:

```text
vendor/aosproot/magisk.apk
```

Download the latest Magisk APK and place it there before building.

### LuminaAI Live2D

LuminaAI requires additional vendor assets.

Follow the setup instructions provided by:

```text
packages/apps/LuminaAI/live2d/get_vendor.sh
```

Run the script and follow it tutorial before starting the build.

## Building

After syncing and completing the required vendor setup, follow the device-specific build instructions for your target device.

---

## Source

Manifest:

https://github.com/LegacyDroid/android_manifest

Branch:

```text
legacydroid-14
```

## License

Individual components of LegacyDroid may be distributed under their respective licenses.
See the individual repositories for licensing information.
