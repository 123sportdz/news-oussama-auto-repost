#!/bin/bash
# NEWS OUSSAMA auto-repost — one command
#   ./run.sh                  — process the queue once (draft mode)
#   ./run.sh --url <url>      — add a post URL and process it
#   ./run.sh --auto           — loop forever (scheduler, every N min)
#   ./run.sh --dashboard      — start the local web dashboard
set -e
cd "$(dirname "$0")"
case "${1:-}" in
  --auto)      exec python3 -m src.scheduler ;;
  --dashboard) exec python3 -m src.dashboard ;;
  *)           exec python3 monitor.py "$@" ;;
esac
