# LegacyDroid Manifests

LegacyDroid provides curated Android source manifests and snippets for building a LineageOS 21 (Android 14) based custom ROM targeted at the x86_64 emulator (lineage_sdk_phone_x86_64). This repository contains the main repo manifest (default.xml) plus useful snippet manifests (e.g., Lineage and Pixel device groups) that make it easy to initialize and sync the full source tree.

## Quick start

Prerequisites
- repo tool (Android's repo)
- git and Git LFS
- Build host dependencies as listed by AOSP/LineageOS (Java, required packages). See https://source.android.com/setup/develop for details.

Initialize using the LegacyDroid manifest (branch: legacydroid-14)
```bash
repo init -u https://github.com/LegacyDroid/android_manifest.git -b legacydroid-14 --git-lfs
repo sync
