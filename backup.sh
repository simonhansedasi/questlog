#!/bin/bash
# Campaign backup — rsync to a single destination; only changed files are written.
set -euo pipefail

SRC=/mnt/serverdrive/coding/rippleforge/campaigns
DEST=/mnt/serverdrive/coding/rippleforge/backups/latest

mkdir -p "$DEST"
rsync -a --delete "$SRC/" "$DEST/"
echo "$(date -Iseconds) backup ok" >> /mnt/serverdrive/coding/rippleforge/backups/backup.log
