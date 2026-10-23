#!/bin/bash

# Wrapper to start all services from repo root (copies logic from scripts/start_all_services.sh)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Delegate to original script
exec bash "$PROJECT_ROOT/scripts/start_all_services.sh" "$@"
