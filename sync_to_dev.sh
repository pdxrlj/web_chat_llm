#!/bin/bash

LOCAL_DIR="F:/code/web_chat_new"
REMOTE_DIR="ipaiserver2:/root/chat_web_project/"

rclone copy "$LOCAL_DIR" "$REMOTE_DIR" \
  --exclude '.venv/**' \
  --exclude '.git/**' \
  --exclude '__pycache__/**' \
  --exclude 'node_modules/**' \
  --exclude '*.egg-info/**' \
  --exclude '*.pyc' \
  --exclude 'sync_watch.py' \
  --exclude 'sync_to_dev.sh' \
  --exclude '.pytest_cache/**' \
  --links \
  -v
