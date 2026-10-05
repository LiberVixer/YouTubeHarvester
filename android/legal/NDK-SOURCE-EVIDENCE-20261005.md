# NDK Source Evidence

The controlled runtime uses Android NDK `28.2.13676358` (r28c), archive SHA256
`dfb20d396df28ca02a8c708314b814a4d961dc9074f9a161932746f815aa552f`.
Its LLVM metadata identifies Android toolchain build `13624864`, LLVM base
`3b5e7c83a6e226d5bd7ed2e9b67449b64812074c` and the following producing trees:

- LLVM manifest commit: `97a699bf4812a18fb657c2779f5296a4ab2694d2`.
- Android LLVM builder: `e727bfb014bd436f581a66a450c939a6983a1fc3`.

Official source archives were downloaded and retained under
`android/build/ndk-sources-28c`. Checksums:

| Archive | SHA256 |
| --- | --- |
| llvm-project-97a699bf.tar.gz | 4a1754e2205ba9a18c8ab62a6352280df872dfcf44a4c51d6ef0e0b848c6a998 |
| llvm_android-e727bfb.tar.gz | 4247557fe143da44ab6562bf9299a419822444fdfb38dd8315c055f6db51dc61 |
| ndk-build-metadata.tar.gz | 40435d84c53d40979e31b956a7c2784318cc80d0dca92c316a5b9b232cae9f3a |

All 51 patches recorded by the bundled `clang_source_info.md` applied with
`git apply --check` and `git apply`, in `patches/PATCHES.json` order, to the
manifest LLVM tree. Two embedded metadata links omit the `cherry/` directory;
their exact filenames are resolved through the pinned patch manifest, not a
different upstream revision. The source/builder archives retain LLVM license
files and Android build scripts, including `DeviceLibcxxBuilder` flags. NDK
NOTICE, source.properties, BUILD_INFO, AndroidVersion.txt, clang_source_info.md
and manifest_13624864.xml are retained in the metadata archive.

Each packaged `libc++_shared.so` has the same build ID as the corresponding
library in the pinned local NDK:

| Architecture | Build ID |
| --- | --- |
| aarch64 | 7befe631535aa853c4f4ac1293e49dcea34c9b6e |
| arm | 8e97299dcad91f08b141d2c086167c461c289a3f |
| i686 | 23aee02e98404fd08c1e4b689ccd5ef7ea84f25f |
| x86_64 | 0f8f9b5a33c8898dc08ae1688f9b1d3d10ff68ab |

Build ID agreement is provenance evidence, not byte-for-byte reproduction of
NDK libraries or independent approval of the final corresponding-source set.
The final source bundle must include these source archives, their metadata and
notices, the producing runtime recipes and the exact APK package mapping.
The publication gate remains enabled.

Official archive URLs:

- https://android.googlesource.com/toolchain/llvm-project/+archive/97a699bf4812a18fb657c2779f5296a4ab2694d2.tar.gz
- https://android.googlesource.com/toolchain/llvm_android/+archive/e727bfb014bd436f581a66a450c939a6983a1fc3.tar.gz
