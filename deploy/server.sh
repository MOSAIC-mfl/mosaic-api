#!/usr/bin/env bash
# Run the live MOSAIC API on a Linux server with a conda (miniforge) environment.
#
#   deploy/server.sh install    install the pinned dependencies and this package into the environment
#   deploy/server.sh harvest    read every source and update state/snapshot.json
#   deploy/server.sh restart    (re)start the API on $MOSAIC_API_PORT and wait until /health answers
#   deploy/server.sh stop       stop it
#   deploy/server.sh status     is it running, and what /health says
#
# Jenkins (Jenkinsfile) runs install, harvest and restart over SSH after updating the code; the same
# commands can be run by hand on the server. Settings (environment variables, with their defaults):
#
#   MOSAIC_API_HOME    /opt/mosaic-api                 the clone of MOSAIC-mfl/mosaic-api
#   MOSAIC_API_PORT    4201
#   MOSAIC_API_BIND    0.0.0.0                         address uvicorn listens on
#   MOSAIC_API_CONFIG  $MOSAIC_API_HOME/config/mosaic-api.server.yaml
#   CONDA_ENV          mosaic-api                      name (or path) of the conda environment
#   CONDA_SH           first found of /opt/miniforge3, /opt/conda, ~/miniforge3, ~/miniconda3
#                      (etc/profile.d/conda.sh)
set -euo pipefail

HOME_DIR="${MOSAIC_API_HOME:-/opt/mosaic-api}"
PORT="${MOSAIC_API_PORT:-4201}"
BIND="${MOSAIC_API_BIND:-0.0.0.0}"
CONFIG="${MOSAIC_API_CONFIG:-$HOME_DIR/config/mosaic-api.server.yaml}"
ENV_NAME="${CONDA_ENV:-mosaic-api}"
LOG_DIR="$HOME_DIR/logs"
PID_FILE="$HOME_DIR/state/api.pid"

activate() {
    local sh="${CONDA_SH:-}"
    if [ -z "$sh" ]; then
        for base in /opt/miniforge3 /opt/conda "$HOME/miniforge3" "$HOME/miniconda3"; do
            if [ -f "$base/etc/profile.d/conda.sh" ]; then sh="$base/etc/profile.d/conda.sh"; break; fi
        done
    fi
    if [ -z "$sh" ] || [ ! -f "$sh" ]; then
        echo "conda.sh not found: set CONDA_SH to <miniforge>/etc/profile.d/conda.sh" >&2
        exit 1
    fi
    # shellcheck disable=SC1090
    source "$sh"
    set +u  # conda's activate scripts read unset variables
    conda activate "$ENV_NAME"
    set -u
    echo "Python: $(python --version 2>&1) at $(command -v python)"
}

health() {
    python - "$PORT" <<'EOF'
import json, sys, urllib.request
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/health", timeout=3) as r:
        print(json.dumps(json.load(r)))
except Exception as exc:  # noqa: BLE001
    print(f"no answer: {exc}")
    sys.exit(1)
EOF
}

running_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid="$(cat "$PID_FILE")"
        if kill -0 "$pid" 2>/dev/null; then echo "$pid"; return 0; fi
    fi
    return 1
}

stop() {
    local pid
    if pid="$(running_pid)"; then
        echo "Stopping the API (pid $pid)"
        kill "$pid" || true
        for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    # anything else still holding the port (e.g. started by hand)
    if command -v fuser >/dev/null; then fuser -k "$PORT/tcp" 2>/dev/null || true; fi
}

cd "$HOME_DIR"
mkdir -p "$LOG_DIR" "$HOME_DIR/state"

case "${1:-}" in
    install)
        activate
        python -m pip install --quiet --upgrade pip
        python -m pip install --quiet -r deploy/requirements-server.txt
        python -m pip install --quiet --no-deps -e .
        python -m mosaic_api --config "$CONFIG" --help >/dev/null
        echo "Installed mosaic-api $(git rev-parse --short HEAD)"
        ;;
    harvest)
        activate
        # 0 every source read; 2 some failed and kept their previous records; 1 all failed
        set +e
        python -m mosaic_api --config "$CONFIG" harvest 2>&1 | tee -a "$LOG_DIR/harvest.log"
        code=${PIPESTATUS[0]}
        set -e
        echo "HARVEST_EXIT=$code"
        if [ "$code" -ne 0 ] && [ ! -f "$HOME_DIR/state/snapshot.json" ]; then
            echo "No snapshot yet: the API cannot start without harvested data" >&2
            exit 1
        fi
        ;;
    restart)
        activate
        stop
        echo "Starting the API on $BIND:$PORT"
        MOSAIC_API_CONFIG="$CONFIG" nohup setsid python -m mosaic_api --config "$CONFIG" serve \
            --host "$BIND" --port "$PORT" > "$LOG_DIR/api.log" 2>&1 < /dev/null &
        echo $! > "$PID_FILE"
        for _ in $(seq 1 30); do
            if health >/dev/null 2>&1; then
                echo "API up (pid $(cat "$PID_FILE")): $(health)"
                exit 0
            fi
            if ! running_pid >/dev/null; then break; fi
            sleep 1
        done
        echo "The API did not answer on port $PORT. Last lines of $LOG_DIR/api.log:" >&2
        tail -n 40 "$LOG_DIR/api.log" >&2 || true
        exit 1
        ;;
    stop)
        stop
        ;;
    status)
        activate >/dev/null
        if pid="$(running_pid)"; then echo "running (pid $pid)"; else echo "not running (no pid file)"; fi
        health
        ;;
    *)
        sed -n '2,20p' "$0"
        exit 2
        ;;
esac
