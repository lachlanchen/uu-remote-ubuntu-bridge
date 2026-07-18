#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${1:-$repo_dir/build/compat}"
cc="${MINGW_CC:-x86_64-w64-mingw32-gcc}"
strip="${MINGW_STRIP:-x86_64-w64-mingw32-strip}"
winegcc="${WINEGCC:-/opt/wine-stable/bin/winegcc}"
host_cc="${HOST_CC:-gcc}"
host_strip="${HOST_STRIP:-strip}"
common=(-std=c11 -O2 -Wall -Wextra -Werror)

for command in "$cc" "$strip" "$winegcc" "$host_cc" "$host_strip"; do
    if ! command -v "$command" >/dev/null 2>&1; then
        printf 'missing build tool: %s\n' "$command" >&2
        exit 1
    fi
done

mkdir -p "$output_dir"

"$cc" "${common[@]}" -shared \
    -o "$output_dir/uu-input-bridge.dll" \
    "$repo_dir/src/uu_input_bridge.c" -luser32
"$cc" "${common[@]}" -municode -mwindows \
    -o "$output_dir/uu-input-broker.exe" \
    "$repo_dir/src/uu_input_broker.c" -luser32 -lws2_32
"$cc" "${common[@]}" -municode \
    -o "$output_dir/uu-injector.exe" \
    "$repo_dir/src/uu_injector.c"
"$cc" "${common[@]}" -municode \
    -o "$output_dir/uu-service-control.exe" \
    "$repo_dir/src/uu_service_control.c" -ladvapi32
"$cc" "${common[@]}" -mwindows \
    -o "$output_dir/uu-healthd-stub.exe" \
    "$repo_dir/src/winlogon.c"
"$cc" "${common[@]}" -shared \
    -o "$output_dir/winpr-sspi-shim.dll" \
    "$repo_dir/src/winpr_sspi_shim.c"
"$host_cc" "${common[@]}" -fPIC -shared \
    -o "$output_dir/uu-network-filter.so" \
    "$repo_dir/src/uu_network_filter.c" -ldl -pthread
"$host_cc" "${common[@]}" -I "$repo_dir/src" \
    -o "$output_dir/uu-x11-input" \
    "$repo_dir/src/uu_x11_input.c" -ldl

"$strip" \
    "$output_dir/uu-input-bridge.dll" \
    "$output_dir/uu-input-broker.exe" \
    "$output_dir/uu-injector.exe" \
    "$output_dir/uu-service-control.exe" \
    "$output_dir/uu-healthd-stub.exe" \
    "$output_dir/winpr-sspi-shim.dll"
"$host_strip" \
    "$output_dir/uu-network-filter.so" \
    "$output_dir/uu-x11-input"

rm -f "$output_dir/winlogon.exe" "$output_dir/winlogon.exe.so"
"$winegcc" -O2 -mwindows -o "$output_dir/winlogon.exe" \
    "$repo_dir/src/winlogon.c"
"$host_strip" "$output_dir/winlogon.exe.so"

printf 'compatibility tools built in %s\n' "$output_dir"
