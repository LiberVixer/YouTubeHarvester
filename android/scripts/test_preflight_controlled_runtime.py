import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from preflight_controlled_runtime import check_hooks, download_sources, read_recipe, validate_extension_recipe, validate_paths, validate_recipes


LOCK = Path(__file__).resolve().parents[1] / "native/runtime-build-lock.json"
X265_HOOK = r'''
termux_step_pre_configure() {
    local v=$(sed -En 's/^.*set\(X265_BUILD ([0-9]+).*$/\1/p' source/CMakeLists.txt)
    if [ "$v" != 215 ]; then termux_error_exit "SOVERSION guard check failed."; fi
    if [ "$TERMUX_ARCH" = arm ] || [ "$TERMUX_ARCH" = i686 ]; then
        TERMUX_PKG_EXTRA_CONFIGURE_ARGS="-DENABLE_ASSEMBLY=OFF"
    fi
    TERMUX_PKG_SRCDIR="$TERMUX_PKG_SRCDIR/source"
    sed -i -e 's/CMP0025 OLD/CMP0025 NEW/' -e 's/CMP0054 OLD/CMP0054 NEW/' \
        -e "s/@TERMUX_CLANG_TARGET_${TERMUX_ARCH^^}@/--target=${CCTERMUX_HOST_PLATFORM}/" \
        "$TERMUX_PKG_SRCDIR/CMakeLists.txt"
    LDFLAGS+=" -landroid-posix-semaphore"
}
'''
UNBOUND_HOOK = r'''
termux_step_pre_configure() {
    sed -i 's/\$function/\$action/' "$TERMUX_PKG_SRCDIR/libunbound/python/libunbound.i"
}
'''


class RuntimePreflightTest(unittest.TestCase):
    def setUp(self):
        self.lock = json.loads(LOCK.read_text())
        overrides = self.lock["recipeOverrides"]
        self.recipes = {
            "ncurses": {"urls": ["ncurses", "rxvt"]},
            "libx11": {"depends": "libandroid-shmem, libxcb", "configure": "LIBS=-landroid-shmem"},
            "libunbound": {"depends": "libevent, libandroid-shmem", "configure": "LIBS=-landroid-shmem --with-pyunbound"},
            "libgraphite": {"configure": "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"},
            "libsoxr": {"configure": "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"},
            "liblzo": {"urls": ["https://www.oberhumer.com/opensource/lzo/download/lzo-2.10.tar.gz"],
                       "hashes": [overrides["liblzoArchiveSha256"]]},
            "texinfo": {"urls": ["gnu", "https://snapshot.debian.org/archive/debian/20250119T025721Z/pool/main/t/texinfo/texinfo_7.2-2.debian.tar.xz"],
                        "hashes": ["unused", overrides["texinfoDebianArchiveSha256"]]},
            "giflib": {"urls": ["https://snapshot.debian.org/archive/debian/20240226T213049Z/pool/main/g/giflib/giflib_5.2.2.orig.tar.gz"],
                       "hashes": [overrides["giflibArchiveSha256"]]},
        }

    def test_valid_overrides_return_three_checked_sources(self):
        self.assertEqual(3, len(validate_recipes(self.recipes, self.lock)))

    def test_native_extension_source_is_locked(self):
        lock = json.loads(LOCK.with_name("python-extensions-lock.json").read_text())
        recipe = {"version": "3.23.0", "urls": ["https://github.com/Legrandin/pycryptodome/archive/refs/tags/v3.23.0x.tar.gz"],
                  "hashes": [lock["pycryptodomexSourceSha256"]]}
        validate_extension_recipe(recipe, lock)
        for field, value in (("version", "3.22.0"), ("urls", ["https://example.org/unreviewed.tar.gz"]), ("hashes", ["0" * 64])):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_extension_recipe({**recipe, field: value}, lock)

    def test_runtime_path_and_alignment_regressions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            properties = repo / "scripts/properties.sh"
            properties.parent.mkdir(parents=True)
            text = ('TERMUX_APP__DATA_DIR="/data/data/com.liberivixer.youtubeharvester"\n'
                    'TERMUX__ROOTFS_SUBDIR=""\nTERMUX__ROOTFS="$TERMUX_APP__DATA_DIR"\n')
            properties.write_text(text)
            toolchain = repo / "scripts/build/toolchain/termux_setup_toolchain_28c.sh"
            toolchain.parent.mkdir(parents=True)
            toolchain.write_text('LDFLAGS="-Wl,-z,max-page-size=16384"\n')
            validate_paths(repo, self.lock)
            for previous, broken in (("com.liberivixer.youtubeharvester", "com.termux"),
                                     ('SUBDIR=""', 'SUBDIR="files"'),
                                     ('ROOTFS="$TERMUX_APP__DATA_DIR"', 'ROOTFS="$TERMUX_APP__DATA_DIR/files"')):
                with self.subTest(previous=previous):
                    properties.write_text(text.replace(previous, broken))
                    with self.assertRaises(ValueError):
                        validate_paths(repo, self.lock)
            properties.write_text(text)
            toolchain.write_text('LDFLAGS=""\n')
            with self.assertRaises(ValueError):
                validate_paths(repo, self.lock)

    def test_rejects_regressions_in_each_previous_failure(self):
        regressions = (
            ("ncurses", "urls", ["ncurses", "rxvt", "foot"]),
            ("libx11", "depends", "libxcb"),
            ("libx11", "configure", ""),
            ("libunbound", "depends", "libevent"),
            ("libunbound", "configure", "LIBS=-landroid-shmem"),
            ("libunbound", "configure", "--with-pyunbound"),
            ("libgraphite", "configure", ""),
            ("libsoxr", "configure", ""),
            ("liblzo", "urls", ["https://fossies.org/linux/misc/lzo-2.10.tar.xz"]),
            ("texinfo", "urls", ["gnu", "https://deb.debian.org/debian/pool/main/t/texinfo/texinfo_7.2-2.debian.tar.xz"]),
            ("giflib", "urls", ["https://downloads.sourceforge.net/project/giflib/giflib-5.2.2.tar.gz"]),
            ("giflib", "hashes", ["0" * 64]),
        )
        for package, field, value in regressions:
            with self.subTest(package=package, field=field):
                recipes = copy.deepcopy(self.recipes)
                recipes[package][field] = value
                with self.assertRaises(ValueError):
                    validate_recipes(recipes, self.lock)

    def test_rejects_changed_cmake_and_host_python(self):
        for field, value in (("cmakePolicyVersionMinimum", "3.0"), ("builderHostPython", "3.10")):
            with self.subTest(field=field):
                lock = {**self.lock, field: value}
                with self.assertRaises(ValueError):
                    validate_recipes(self.recipes, lock)

    def test_reads_real_bash_arrays_and_architecture_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            recipe = repo / "packages/test/build.sh"
            recipe.parent.mkdir(parents=True)
            recipe.write_text('TERMUX_PKG_VERSION=1\nTERMUX_PKG_SRCURL=("$TERMUX_ARCH/a" "$TERMUX_PREFIX/b")\n'
                              'TERMUX_PKG_SHA256=(one two)\n')
            for arch in self.lock["architectures"].values():
                result = read_recipe(repo, "test", arch, "/runtime/usr")
                self.assertEqual([arch + "/a", "/runtime/usr/b"], result["urls"])
                self.assertEqual(["one", "two"], result["hashes"])

    def test_mismatched_source_arrays_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            recipe = repo / "packages/test/build.sh"
            recipe.parent.mkdir(parents=True)
            recipe.write_text('TERMUX_PKG_VERSION=1\nTERMUX_PKG_SRCURL=(a b)\nTERMUX_PKG_SHA256=(one)\n')
            with self.assertRaises(ValueError):
                read_recipe(repo, "test", "arm", "/runtime/usr")

    def hook_fixture(self, root, x265=X265_HOOK, unbound=UNBOUND_HOOK):
        for name, text in (("libx265", x265), ("libunbound", unbound)):
            recipe = root / "packages" / name / "build.sh"
            recipe.parent.mkdir(parents=True, exist_ok=True)
            recipe.write_text(text)

    def test_hook_guards_for_all_architectures(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.hook_fixture(repo)
            for arch in self.lock["architectures"].values():
                with self.subTest(arch=arch):
                    check_hooks(repo, arch)

    def test_hook_regressions_are_rejected(self):
        cases = (
            (X265_HOOK.replace("CMP0025 NEW", "CMP0025 OLD"), UNBOUND_HOOK),
            (X265_HOOK.replace("CMP0054 NEW", "CMP0054 OLD"), UNBOUND_HOOK),
            (X265_HOOK.replace("-DENABLE_ASSEMBLY=OFF", ""), UNBOUND_HOOK),
            (X265_HOOK.replace("-landroid-posix-semaphore", ""), UNBOUND_HOOK),
            (X265_HOOK.replace('if [ "$v" != 215 ]', 'if false'), UNBOUND_HOOK),
            (X265_HOOK, UNBOUND_HOOK.replace(r"\$action", r"\$function")),
        )
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            for index, (x265, unbound) in enumerate(cases):
                with self.subTest(case=index):
                    self.hook_fixture(repo, x265, unbound)
                    with self.assertRaises(ValueError):
                        check_hooks(repo, "arm")

    def test_download_verifies_bytes_and_uses_termux_cache_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "scripts/build/termux_download.sh"
            script.parent.mkdir(parents=True)
            script.write_text('set -e\ncp "$1" "$2"\n')
            archive = root / "source.tar.gz"
            archive.write_bytes(b"verified source")
            source = {"package": "giflib", "url": str(archive),
                      "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
            download_sources(root, [source], root / "cache")
            self.assertEqual(archive.read_bytes(), (root / "cache/giflib/cache/source.tar.gz").read_bytes())
            with self.assertRaises(ValueError):
                download_sources(root, [{**source, "sha256": "0" * 64}], root / "cache")
