#!/usr/bin/env sh
# Downloads the local Piper voice into the `speech_models` Docker volume.
# faster-whisper downloads its model automatically on first use (cached in the same volume via HF_HOME).
# Usage: docker compose run --rm backend sh /app/scripts/download_speech_models.sh
set -eu
VOICE_DIR=/models/piper
mkdir -p "$VOICE_DIR"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
for f in en_US-lessac-medium.onnx en_US-lessac-medium.onnx.json; do
  if [ ! -f "$VOICE_DIR/$f" ]; then
    echo "Downloading $f"
    curl -fsSL "$BASE/$f" -o "$VOICE_DIR/$f"
  fi
done
echo "Piper voice ready in $VOICE_DIR"
