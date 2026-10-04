"""Stage hash-pinned desktop media tools without modifying system packages."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

TOOLS = {
    "linux": {
        "ffmpeg": (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-01-13-06/ffmpeg-n9.0.2-22-g46d8f462ee-linux64-gpl-9.0.tar.xz",
            "a6170faecf757381ad0338d7a6ba26e97c2ebe2b9c1568633421e15d1ed436a9",
            ("ffmpeg", "ffprobe")),
        "deno": (
            "https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-unknown-linux-gnu.zip",
            "c6527f24f4b16031d3ae4fa9f658d5f11534c8d84ce7dc8502420280919c3490",
            ("deno",)),
    },
    "windows": {
        "ffmpeg": (
            "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip",
            "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba",
            ("ffmpeg.exe", "ffprobe.exe")),
        "deno": (
            "https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-pc-windows-msvc.zip",
            "a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238",
            ("deno.exe",)),
    },
}


def unpack(archive, directory, wanted):
    found = set()
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                name = Path(entry.filename).name
                if name not in wanted:
                    continue
                if name in found or entry.file_size > 400 * 1024 * 1024:
                    raise ValueError("Unexpected tool archive entry")
                with source.open(entry) as inp, (directory / name).open('xb') as out:
                    shutil.copyfileobj(inp, out)
                found.add(name)
    else:
        with tarfile.open(archive) as source:
            for entry in source:
                name = Path(entry.name).name
                if name not in wanted:
                    continue
                if name in found or not entry.isfile() or entry.size > 400 * 1024 * 1024:
                    raise ValueError("Unexpected tool archive entry")
                with source.extractfile(entry) as inp, (directory / name).open('xb') as out:
                    shutil.copyfileobj(inp, out)
                found.add(name)
    if found != set(wanted):
        raise ValueError("Required executables absent")
    for name in wanted:
        (directory / name).chmod(0o755)


def fetch(platform, output, cache):
    cache.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    for tool, (url, expected, names) in TOOLS[platform].items():
        target = output / tool
        if target.exists() or target.is_symlink():
            raise ValueError(f"Refusing to overwrite {target}")
        archive = cache / (expected + ('.zip' if url.endswith('.zip') else '.tar.xz'))
        if not archive.exists():
            temporary = archive.with_suffix(archive.suffix + '.part')
            subprocess.run(['curl', '-fLSs', '--retry', '4', '--connect-timeout', '20',
                            '--max-time', '1200', url, '-o', str(temporary)], check=True)
            with temporary.open('rb') as inp:
                actual = hashlib.file_digest(inp, 'sha256').hexdigest()
            if actual != expected:
                temporary.unlink()
                raise ValueError("Downloaded archive SHA-256 mismatch")
            temporary.replace(archive)
        with archive.open('rb') as inp:
            if hashlib.file_digest(inp, 'sha256').hexdigest() != expected:
                raise ValueError("Cached archive SHA-256 mismatch")
        with tempfile.TemporaryDirectory(prefix=tool + '-', dir=output) as staging:
            staging = Path(staging)
            unpack(archive, staging, names)
            if platform == 'linux':
                result = subprocess.run([str(staging / names[0]), '-version' if tool == 'ffmpeg' else '--version'],
                                        capture_output=True, text=True, check=True)
                line = result.stdout.splitlines()[0]
                if not line.startswith('ffmpeg version n9.0.2' if tool == 'ffmpeg' else 'deno 2.9.7'):
                    raise ValueError("Unexpected executable version")
                print(line, flush=True)
            staging.rename(target)
        print(f"Verified {platform} {tool}: {expected}", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=TOOLS, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=Path('dist/component-cache'))
    args = parser.parse_args()
    fetch(args.platform, args.output, args.cache)
