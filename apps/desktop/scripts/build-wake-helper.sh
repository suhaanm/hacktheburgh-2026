#!/bin/bash
# Builds the "Hey Knack" listener into apps/desktop/resources/knack-wake (arm64, macOS 13+). Compile only: this script never runs the binary.
# The usage strings are embedded in the binary (a command-line tool has no Info.plist of its own). The binary is not committed.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
src="$here/native/knack-wake"
out="${1:-$here/resources/knack-wake}"
mkdir -p "$(dirname "$out")"
swiftc -O -swift-version 5 -target arm64-apple-macos13.0 \
  "$src/Matcher.swift" "$src/main.swift" \
  -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker "$src/Info.plist" \
  -o "$out"
echo "built $out"
