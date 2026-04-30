#!/bin/bash
set -e

DEST="simonhans@raspberrypi:/mnt/serverdrive/coding/rippleforge"

rsync -av --checksum \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='campaigns/' \
  --exclude='users.json' \
  --exclude='*.egg-info/' \
  . "$DEST"

ssh simonhans@raspberrypi "find /mnt/serverdrive/coding/rippleforge -name '*.pyc' -delete && sudo systemctl restart rippleforge"

echo "Deployed and restarted."
