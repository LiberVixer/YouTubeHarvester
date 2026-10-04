#!/usr/bin/env bash
set -euo pipefail

arch="${1:?Specify a Termux architecture}"
case "$arch" in aarch64|arm|i686|x86_64) ;; *) exit 2 ;; esac
repo="${2:?Specify the pinned Termux checkout}"
app="${3:?Specify the Harvester checkout}"
output="${4:?Specify an empty output directory}"
repo="$(realpath "$repo")"
app="$(realpath "$app")"
output="$(realpath -m "$output")"
lock="$app/android/native/runtime-build-lock.json"
commit="$(jq -r .termuxCommit "$lock")"
image="$(jq -r .builderImage "$lock")"
test "$(git -C "$repo" rev-parse HEAD)" = "$commit"
test -z "$(git -C "$repo" status --porcelain)"
test ! -e "$output"
mkdir -p "$output"
git -C "$repo" archive --format=tar.gz --output="$output/termux-recipes.tar.gz" HEAD
cp "$lock" "$app/android/native/termux-runtime.patch" "$output/"
git -C "$repo" apply --check "$app/android/native/termux-runtime.patch"
git -C "$repo" apply "$app/android/native/termux-runtime.patch"

# Source-build dependencies too: do not use Termux's prebuilt-dependency switch.
docker pull "$image"
docker image inspect "$image" > "$output/builder-image.json"
set +e
docker run --rm --init \
  --volume "$repo:/home/builder/termux-packages" \
  --volume "$output:/output" \
  --env "YTH_ARCH=$arch" \
  --env TERMUX_PKG_API_LEVEL=26 \
  --env TERMUX_PKG_MAKE_PROCESSES=2 \
  --env TERMUX_NDK_VERSION_NUM=28 \
  --env TERMUX_NDK_REVISION=c \
  --env NDK=/home/builder/lib/android-ndk-r28c \
  --env CI=true \
  --user root \
  "$image" bash -c '
    set -euo pipefail
    mkdir -p /data/data/com.liberivixer.youtubeharvester /data/data/.built-packages
    chown -R builder:builder /data/data/com.liberivixer.youtubeharvester /data/data/.built-packages /output
    cd /home/builder/termux-packages
    git config --global --add safe.directory /home/builder/termux-packages
    trap '\''tar --exclude="./_cache" --exclude="./*/build" --exclude="./*/host-build" \
      --exclude="./*/massage" --exclude="./*/package" --exclude="./*/tmp" \
      --exclude="./*/multilib-build" \
      -czf /output/runtime-source-worktrees.tar.gz -C /home/builder/.termux-build . \
      || echo "Source worktree collection incomplete" >&2'\'' EXIT
    if [[ ! -d "$NDK" ]]; then
      su -m builder -c "HOME=/home/builder ./scripts/setup-android-sdk.sh"
    fi
    su -m builder -c "HOME=/home/builder ./build-package.sh -a $YTH_ARCH -F -o /output/packages python ffmpeg ca-certificates"
  ' 2>&1 | tee "$output/build.log"
result="${PIPESTATUS[0]}"
set -e
printf '%s\n' "$result" > "$output/build-exit-code.txt"
python3 "$app/android/scripts/record_runtime_build.py" \
  --folder "$output" --architecture "$arch" --application "$app"
exit "$result"
