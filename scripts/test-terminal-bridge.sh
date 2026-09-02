#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
wine_bin="${UURB_WINE_BIN:-/opt/wine-stable/bin/wine}"
wineserver_bin="${UURB_WINESERVER_BIN:-/opt/wine-stable/bin/wineserver}"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-terminal-test.XXXXXX")"
wine_prefix="$temporary_dir/prefix"
ready_file="$temporary_dir/terminal.port"
bridge_pid=""

cleanup() {
    local status=$?

    trap - EXIT INT TERM HUP
    if [[ -n "$bridge_pid" ]] && kill -0 "$bridge_pid" 2>/dev/null; then
        kill "$bridge_pid" 2>/dev/null || true
        wait "$bridge_pid" 2>/dev/null || true
    fi
    if [[ -x "$wineserver_bin" && -d "$wine_prefix" ]]; then
        WINEPREFIX="$wine_prefix" "$wineserver_bin" -k >/dev/null 2>&1 || true
        WINEPREFIX="$wine_prefix" "$wineserver_bin" -w >/dev/null 2>&1 || true
    fi
    if ((status == 0)); then
        rm -rf -- "$temporary_dir"
    else
        printf 'terminal bridge test artifacts preserved at %s\n' \
            "$temporary_dir" >&2
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

for executable in "$wine_bin" "$repo_dir/build/compat/uu-terminal-bridge" \
    "$repo_dir/build/compat/uu-terminal-proxy.exe"; do
    [[ -x "$executable" ]] || {
        printf 'missing terminal bridge test executable: %s\n' "$executable" >&2
        exit 1
    }
done

WINEPREFIX="$wine_prefix" WINEDEBUG=-all DISPLAY= \
    "$wine_bin" wineboot -u >/dev/null 2>&1

token="$(openssl rand -hex 32)"
UURB_TERMINAL_BRIDGE_TOKEN="$token" \
    "$repo_dir/build/compat/uu-terminal-bridge" \
    --ready-file "$ready_file" \
    >"$temporary_dir/bridge.stdout" 2>"$temporary_dir/bridge.stderr" &
bridge_pid=$!
for _ in {1..100}; do
    if [[ -s "$ready_file" ]] && kill -0 "$bridge_pid" 2>/dev/null; then
        break
    fi
    sleep 0.05
done
[[ -s "$ready_file" ]] || {
    printf 'native terminal bridge did not publish its loopback port\n' >&2
    exit 1
}
port="$(<"$ready_file")"
[[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] || {
    printf 'native terminal bridge published an invalid port\n' >&2
    exit 1
}

set +e
printf 'exit\n' | env \
    WINEPREFIX="$wine_prefix" WINEDEBUG=-all DISPLAY= \
    UURB_TERMINAL_BRIDGE_PORT="$port" \
    UURB_TERMINAL_BRIDGE_TOKEN="$(printf '%064d' 0)" \
    timeout 10 "$wine_bin" \
    "$repo_dir/build/compat/uu-terminal-proxy.exe" \
    >"$temporary_dir/rejected.stdout" 2>"$temporary_dir/rejected.stderr"
rejected_status=$?
set -e
if ((rejected_status == 0)) ||
   ! grep -q 'rejected authentication' "$temporary_dir/rejected.stderr"; then
    printf 'invalid terminal token was not rejected explicitly\n' >&2
    exit 1
fi

commands=$'printf "UURB_NATIVE_SHELL_OK\\n"\nprintf "UURB_UNICODE_你好\\n"\nprintf "UURB_CWD=%s\\n" "$PWD"\nstty size\nexit\n'
printf '%s' "$commands" | env \
    WINEPREFIX="$wine_prefix" WINEDEBUG=-all DISPLAY= \
    UURB_TERMINAL_BRIDGE_PORT="$port" \
    UURB_TERMINAL_BRIDGE_TOKEN="$token" \
    timeout 20 "$wine_bin" \
    "$repo_dir/build/compat/uu-terminal-proxy.exe" \
    >"$temporary_dir/accepted.stdout" 2>"$temporary_dir/accepted.stderr"

python3 - "$temporary_dir/accepted.stdout" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
text = re.sub(r"\x1b\].*?(?:\x07|\x1b\\)", "", text, flags=re.DOTALL)
text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text).replace("\r", "")
required = (
    "UURB_NATIVE_SHELL_OK",
    "UURB_UNICODE_你好",
    "UURB_CWD=/home/",
    "24 80",
)
missing = [marker for marker in required if marker not in text]
if missing:
    raise SystemExit("missing terminal markers: " + ", ".join(missing))
PY

if [[ -s "$temporary_dir/accepted.stderr" ]]; then
    printf 'terminal proxy emitted unexpected stderr\n' >&2
    exit 1
fi

printf 'terminal-bridge=authenticated native-shell=exact unicode=exact resize=24x80\n'
