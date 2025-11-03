#!/usr/bin/env bash
set -e

# Install FFmpeg and Python deps
apt-get update && apt-get install -y ffmpeg
pip install -r requirements.txt

# Write the cookies to a file (if provided)
if [ ! -z "$COOKIE_FILE_CONTENTS" ]; then
  echo "$COOKIE_FILE_CONTENTS" > /app/cookies.txt
  echo "✅ Cookie file written to /app/cookies.txt"
else
  echo "⚠️ COOKIE_FILE_CONTENTS not set — YouTube auth may fail."
fi
