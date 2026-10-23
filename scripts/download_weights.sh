#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
WEIGHTS_DIR="$ROOT_DIR/weights"

mkdir -p "$WEIGHTS_DIR"

TARGET="$WEIGHTS_DIR/model.pt"

if [ -f "$TARGET" ]; then
    echo "Weights file already exists at: $TARGET"
    exit 0
fi

echo "Downloading UI element detection model (OmniParser v2 icon_detect)..."
URL="https://huggingface.co/microsoft/OmniParser-v2.0/resolve/main/icon_detect/model.pt"

if command -v curl >/dev/null 2>&1; then
    curl -L "$URL" -o "$TARGET"
elif command -v wget >/dev/null 2>&1; then
    wget -O "$TARGET" "$URL"
else
    echo "Error: Neither curl nor wget found. Please download manually from: $URL"
    exit 1
fi

echo "Successfully downloaded weights to: $TARGET"
