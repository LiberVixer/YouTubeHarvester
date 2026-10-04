"""Inventory actual packaged runtime bytes, not a corresponding-source attestation."""
import argparse
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile


def elf_dependencies(data):
    with tempfile.NamedTemporaryFile() as binary:
        binary.write(data)
        binary.flush()
        output = subprocess.check_output(['readelf', '--dynamic', '--wide', binary.name],
                                         text=True, env={'LC_ALL': 'C', 'PATH': '/usr/bin:/bin'})
    return sorted(set(re.findall(r'\(NEEDED\).*\[([^\]]+)\]', output)))


def inventory(apk, inspect_elf=True, max_bytes=512 * 1024 * 1024):
    entries = []
    remaining = max_bytes

    def visit(data, name, depth):
        entry = {'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        if data.startswith(b'\x7fELF'):
            entry['kind'] = 'ELF'
            if inspect_elf:
                entry['needed'] = elf_dependencies(data)
        elif zipfile.is_zipfile(io.BytesIO(data)):
            entry['kind'] = 'ZIP'
            entries.append(entry)
            if depth >= 3:
                raise ValueError('Nested runtime depth exceeds limit')
            with zipfile.ZipFile(io.BytesIO(data)) as nested:
                walk(nested, name + '!', depth + 1)
            return
        else:
            entry['kind'] = 'file'
            if name.endswith(('/METADATA', '/PKG-INFO')):
                metadata = BytesParser().parsebytes(data, headersonly=True)
                entry['pythonMetadata'] = {key: metadata.get(key) for key in ('Name', 'Version', 'License')}
        entries.append(entry)

    def walk(archive, prefix, depth, top=False):
        nonlocal remaining
        names = set()
        for item in sorted(archive.infolist(), key=lambda i: i.filename):
            if item.filename in names:
                raise ValueError('Duplicate ZIP entry: ' + prefix + item.filename)
            names.add(item.filename)
            if item.is_dir() or (top and not item.filename.startswith('lib/')):
                continue
            if item.file_size > remaining:
                raise ValueError('Expanded runtime exceeds byte limit')
            remaining -= item.file_size
            visit(archive.read(item), prefix + item.filename, depth)

    with zipfile.ZipFile(apk) as archive:
        walk(archive, '', 0, top=True)
    with Path(apk).open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'apk': Path(apk).name, 'apkSha256': digest,
            'scope': 'lib/ and nested archives; excludes application DEX/resources',
            'correspondingSourcesVerified': False, 'entries': entries}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('apks', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = [inventory(apk) for apk in args.apks]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, indent=2) + '\n')
    for report in reports:
        print(json.dumps({'apk': report['apk'], 'sha256': report['apkSha256'],
                          'entries': len(report['entries']),
                          'elf': sum(e['kind'] == 'ELF' for e in report['entries']),
                          'pythonPackages': [e['pythonMetadata'] for e in report['entries']
                                             if 'pythonMetadata' in e]}))


if __name__ == '__main__':
    main()
