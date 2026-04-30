#!/bin/bash
set -e

DEST="simonhans@raspberrypi:/mnt/serverdrive/coding/questbook"

rsync -av --checksum \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='campaigns/' \
  --exclude='users.json' \
  --exclude='invites.json' \
  --exclude='*.egg-info/' \
  . "$DEST"

ssh simonhans@raspberrypi "find /mnt/serverdrive/coding/questbook -name '*.pyc' -delete && sudo systemctl restart questbook"

echo "Deployed and restarted."
