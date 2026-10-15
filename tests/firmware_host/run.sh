#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
fw="$here/../../firmware/ARS_remote_v3_15"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for scenario in main power; do
    g++ -std=c++17 -Wall -Wextra -I"$here/stubs" -I"$fw" "$here/$scenario.cpp" "$fw/ars_ble.cpp" "$fw/display.cpp" "$fw/status_led.cpp" "$fw/keypad.cpp" -o "$tmp/$scenario"
    "$tmp/$scenario"
done
