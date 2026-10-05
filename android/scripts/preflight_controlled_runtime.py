"""Fail early on regressions already encountered in the controlled runtime build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


PACKAGES = ("ncurses", "libx11", "liblzo", "libgraphite", "libunbound",
            "texinfo", "libsoxr", "giflib", "libx265")
FIELDS = ("version", "depends", "configure", "urls", "hashes")
RECIPE_QUERY = r'''
set -e
source "$1"
printf '%s\0' "$TERMUX_PKG_VERSION" "${TERMUX_PKG_DEPENDS-}" "${TERMUX_PKG_EXTRA_CONFIGURE_ARGS-}"
printf '%s\0' "${#TERMUX_PKG_SRCURL[@]}" "${TERMUX_PKG_SRCURL[@]}" "${TERMUX_PKG_SHA256[@]}"
'''


def read_recipe(repo, package, arch, prefix):
    env = {**os.environ, "TERMUX_ARCH": arch, "TERMUX_PREFIX": prefix,
           "TERMUX_SCRIPTDIR": str(repo), "TERMUX_PKG_EXTRA_CONFIGURE_ARGS": ""}
    result = subprocess.check_output(
        ["bash", "-c", RECIPE_QUERY, "preflight", str(repo / "packages" / package / "build.sh")],
        env=env, timeout=30).decode().split("\0")[:-1]
    count = int(result[3])
    if not count or len(result) != 4 + count * 2:
        raise ValueError(f"{package}: source URL/checksum array mismatch")
    return dict(zip(FIELDS, [*result[:3], result[4:4 + count], result[4 + count:]]))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_paths(repo, lock):
    properties = (repo / "scripts/properties.sh").read_text()
    data_dir = str(Path(lock["prefix"]).parent)
    for assignment in (f'TERMUX_APP__DATA_DIR="{data_dir}"', 'TERMUX__ROOTFS_SUBDIR=""',
                       'TERMUX__ROOTFS="$TERMUX_APP__DATA_DIR"'):
        require(assignment in properties.splitlines(), f"Runtime path override missing: {assignment}")
    toolchain = (repo / "scripts/build/toolchain/termux_setup_toolchain_28c.sh").read_text()
    require("-Wl,-z,max-page-size=16384" in toolchain, "16 KB ELF linker flag missing")


def validate_recipes(recipes, lock):
    overrides = lock["recipeOverrides"]
    require(lock["cmakePolicyVersionMinimum"] == "3.5", "CMake policy floor changed")
    require(lock["builderHostPython"] == "3.12", "Builder Python must match pinned recipes")
    require(len(recipes["ncurses"]["urls"]) == 2, "ncurses: unrelated terminfo sources returned")
    for name in ("libx11", "libunbound"):
        recipe = recipes[name]
        require("libandroid-shmem" in recipe["depends"].split(", "), f"{name}: shared-memory dependency missing")
        require("LIBS=-landroid-shmem" in recipe["configure"].split(), f"{name}: shared-memory linking missing")
    for name in ("libgraphite", "libsoxr"):
        require("-DCMAKE_POLICY_VERSION_MINIMUM=3.5" in recipes[name]["configure"].split(),
                f"{name}: CMake compatibility missing")
    require("--with-pyunbound" in recipes["libunbound"]["configure"].split(),
            "libunbound: Python bindings disabled")
    expected = (
        ("liblzo", 0, "https://www.oberhumer.com/opensource/lzo/download/lzo-2.10.tar.gz", "liblzoArchiveSha256"),
        ("texinfo", 1, "https://snapshot.debian.org/archive/debian/20250119T025721Z/pool/main/t/texinfo/texinfo_7.2-2.debian.tar.xz", "texinfoDebianArchiveSha256"),
        ("giflib", 0, "https://snapshot.debian.org/archive/debian/20240226T213049Z/pool/main/g/giflib/giflib_5.2.2.orig.tar.gz", "giflibArchiveSha256"),
    )
    sources = []
    for name, index, url, key in expected:
        require(len(recipes[name]["urls"]) > index, f"{name}: source missing")
        require(recipes[name]["urls"][index] == url, f"{name}: verified source URL changed")
        require(recipes[name]["hashes"][index] == overrides[key], f"{name}: locked checksum changed")
        sources.append({"package": name, "url": url, "sha256": overrides[key]})
    return sources


def validate_extension_recipe(recipe, lock):
    require(recipe["version"] == lock["pycryptodomexVersion"], "PyCryptodomex version differs from extension lock")
    require(recipe["urls"] == ["https://github.com/Legrandin/pycryptodome/archive/refs/tags/v" + lock["pycryptodomexVersion"] + "x.tar.gz"],
            "PyCryptodomex producing source changed")
    require(recipe["hashes"] == [lock["pycryptodomexSourceSha256"]], "PyCryptodomex source checksum changed")


def check_hooks(repo, arch):
    # Exercise the real recipe hooks on small source fixtures, without cross-compiling.
    with tempfile.TemporaryDirectory(prefix="yth-runtime-hooks-") as directory:
        root = Path(directory)
        source = root / "source"
        source.mkdir()
        cmake = source / "CMakeLists.txt"
        cmake.write_text("set(X265_BUILD 215)\ncmake_policy(SET CMP0025 OLD)\n"
                         "cmake_policy(SET CMP0054 OLD)\n@TERMUX_CLANG_TARGET_" + arch.upper() + "@\n")
        script = r'''
set -e
termux_error_exit() { printf '%s\n' "$*" >&2; exit 1; }
source "$1/packages/libx265/build.sh"
cd "$2"
termux_step_pre_configure
printf '%s\0' "$TERMUX_PKG_EXTRA_CONFIGURE_ARGS" "$LDFLAGS"
'''
        env = {**os.environ, "TERMUX_ARCH": arch, "TERMUX_PKG_SRCDIR": str(root),
               "TERMUX_ON_DEVICE_BUILD": "false", "CCTERMUX_HOST_PLATFORM": "preflight-target",
               "TERMUX_PKG_EXTRA_CONFIGURE_ARGS": "", "LDFLAGS": ""}
        flags, linker, _ = subprocess.check_output(
            ["bash", "-c", script, "preflight", str(repo), str(root)],
            env=env, timeout=30).decode().split("\0")
        text = cmake.read_text()
        for policy in ("CMP0025", "CMP0054"):
            require(f"cmake_policy(SET {policy} NEW)" in text and f"{policy} OLD" not in text,
                    f"libx265/{arch}: removed OLD policy remains")
        require("--target=preflight-target" in text, f"libx265/{arch}: compiler target lost")
        require(("-DENABLE_ASSEMBLY=OFF" in flags.split()) == (arch in ("arm", "i686")),
                f"libx265/{arch}: assembly guard changed")
        require("-landroid-posix-semaphore" in linker.split(), f"libx265/{arch}: semaphore linking lost")
        cmake.write_text(text.replace("X265_BUILD 215", "X265_BUILD 216"))
        rejected = subprocess.run(["bash", "-c", script, "preflight", str(repo), str(root)],
                                  env=env, capture_output=True, timeout=30)
        require(rejected.returncode != 0 and b"SOVERSION guard check failed" in rejected.stderr,
                f"libx265/{arch}: SOVERSION guard lost")

        swig = root / "libunbound" / "python" / "libunbound.i"
        swig.parent.mkdir(parents=True)
        swig.write_text("%exception { $function }\n")
        subprocess.run(["bash", "-ec", 'source "$1/packages/libunbound/build.sh"; termux_step_pre_configure',
                        "preflight", str(repo)], env=env, check=True, timeout=30)
        require("$action" in swig.read_text() and "$function" not in swig.read_text(),
                f"libunbound/{arch}: unsupported SWIG placeholder remains")


def download_sources(repo, sources, folder):
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yth-runtime-download-") as directory:
        for source in sources:
            destination = folder / source["package"] / "cache" / source["url"].rsplit("/", 1)[1]
            destination.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["bash", str(repo / "scripts/build/termux_download.sh"),
                            source["url"], str(destination), source["sha256"]], check=True,
                           env={**os.environ, "TERMUX_PKG_TMPDIR": directory,
                                "TERMUX_PKG_NAME": source["package"], "TERMUX_QUIET_BUILD": "true"},
                           timeout=600)
            with destination.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            require(actual == source["sha256"], f"{source['package']}: preflight checksum mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download-sources", action="store_true")
    parser.add_argument("--extensions-lock", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    lock = json.loads(args.lock.read_text())
    validate_paths(repo, lock)
    sources = None
    for package in PACKAGES:
        subprocess.run(["bash", "-n", str(repo / "packages" / package / "build.sh")], check=True)
    architectures = list(lock["architectures"].values())
    require(set(architectures) == {"aarch64", "arm", "i686", "x86_64"}, "Architecture matrix changed")
    for arch in architectures:
        recipes = {package: read_recipe(repo, package, arch, lock["prefix"]) for package in PACKAGES}
        sources = validate_recipes(recipes, lock)
        if args.extensions_lock:
            extensions = json.loads(args.extensions_lock.read_text())
            require(extensions["termuxCommit"] == lock["termuxCommit"] and
                    extensions["pythonVersion"] == lock["pythonVersion"], "Extension build base changed")
            validate_extension_recipe(read_recipe(repo, "python-pycryptodomex", arch, lock["prefix"]), extensions)
        check_hooks(repo, arch)
    if args.download_sources:
        download_sources(repo, sources, args.output / "preflight-sources")
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"architectures": architectures, "recipeChecksPassed": True,
              "sourceDownloadsVerified": args.download_sources, "sources": sources,
              "publicReleaseReady": False}
    (args.output / "preflight.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
