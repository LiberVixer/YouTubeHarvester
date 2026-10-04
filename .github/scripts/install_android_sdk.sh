#!/usr/bin/env bash
set -euo pipefail

sdk_root="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [[ -z "$sdk_root" ]]; then
  echo 'ANDROID_HOME or ANDROID_SDK_ROOT must point to the Android SDK' >&2
  exit 1
fi

sdkmanager="$sdk_root/cmdline-tools/latest/bin/sdkmanager"
if [[ ! -x "$sdkmanager" ]]; then
  sdkmanager=''
  for candidate in "$sdk_root"/cmdline-tools/*/bin/sdkmanager; do
    if [[ -x "$candidate" ]]; then
      sdkmanager="$candidate"
      break
    fi
  done
fi
if [[ -z "$sdkmanager" ]]; then
  echo "Android command-line tools were not found in $sdk_root" >&2
  exit 1
fi

if [[ -n "${GITHUB_PATH:-}" ]]; then
  printf '%s\n' "$(dirname "$sdkmanager")" >> "$GITHUB_PATH"
fi
"$sdkmanager" "$@"
