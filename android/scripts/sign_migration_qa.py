"""Sign isolated non-debuggable migration QA APKs, never a public release."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from verify_apk import MIGRATION_PACKAGE, check_certificate, check_manifest, parse_tree, verify


def manifest(apk, build_tools):
    return parse_tree(subprocess.check_output([
        str(build_tools / 'aapt2'), 'dump', 'xmltree', '--file', 'AndroidManifest.xml', str(apk)
    ], text=True))


def check_test_manifest(root):
    if root.get('package') != MIGRATION_PACKAGE + '.test':
        raise ValueError('Unexpected test package')
    instruments = root.findall('instrumentation')
    if len(instruments) != 1 or instruments[0].get('targetPackage') != MIGRATION_PACKAGE or \
            instruments[0].get('name') != 'androidx.test.runner.AndroidJUnitRunner':
        raise ValueError('Tests must target only the isolated migration package')
    app = root.find('application')
    if app is None or app.get('debuggable', 'false') != 'false':
        raise ValueError('Do not sign debuggable tests with the permanent key')


def unlock_keystore(keytool, keystore, alias, certificate):
    for _ in range(3):
        password = getpass.getpass('Permanent Android signing-key password (hidden): ')
        if len(password) < 12 or '\n' in password or '\r' in password:
            print('Password not accepted; try again.')
            continue
        result = subprocess.run([str(keytool), '-exportcert', '-keystore', str(keystore),
            '-storetype', 'PKCS12', '-alias', alias, '-storepass:file', '/dev/stdin'],
            input=(password + '\n').encode(), capture_output=True)
        if result.returncode == 0:
            if hashlib.sha256(result.stdout).hexdigest() != certificate:
                raise ValueError('Keystore certificate differs from the independently approved identity')
            return password
        print('Cannot unlock the signing key; try again.')
    raise ValueError('Signing key was not unlocked')


def sign_one(source, target, build_tools, keystore, alias, password):
    command = [str(build_tools / 'apksigner'), 'sign', '--ks', str(keystore), '--ks-type', 'PKCS12',
        '--ks-key-alias', alias, '--ks-pass', 'stdin', '--key-pass', 'stdin',
        '--debuggable-apk-permitted', 'false', '--v4-signing-enabled', 'false',
        '--alignment-preserved', 'true', '--in', str(source), '--out', str(target)]
    result = subprocess.run(command, input=(password + '\n' + password + '\n').encode(), capture_output=True)
    if result.returncode != 0:
        raise ValueError('APK signing failed; no passwords or signer diagnostics are logged')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('app', 'tests', 'build-tools', 'keytool', 'keystore', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--alias', default='yth-android')
    parser.add_argument('--certificate', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--version-code', type=int, required=True)
    parser.add_argument('--wait', action='store_true')
    args = parser.parse_args()
    try:
        if not sys.stdin.isatty():
            raise ValueError('Use a local interactive terminal; never provide this password through chat')
        if os.path.lexists(args.output_dir):
            raise ValueError('Output directory already exists; refusing to overwrite')
        if not args.keystore.is_file() or args.keystore.is_symlink() or args.keystore.stat().st_mode & 0o077:
            raise ValueError('Keystore must be a private regular file')
        if not all(p.is_file() for p in (args.app, args.tests, args.keytool)):
            raise ValueError('Required build/keytool files are missing')
        check_manifest(manifest(args.app, args.build_tools), args.version, args.version_code, migration_qa=True)
        check_test_manifest(manifest(args.tests, args.build_tools))
        password = unlock_keystore(args.keytool, args.keystore, args.alias, args.certificate.lower())
        args.output_dir.mkdir(mode=0o700)
        try:
            with tempfile.TemporaryDirectory(prefix='sign-', dir=args.output_dir) as temporary:
                temporary = Path(temporary)
                app, tests = temporary / 'migrationqa-x86_64.apk', temporary / 'migrationqa-tests.apk'
                sign_one(args.app, app, args.build_tools, args.keystore, args.alias, password)
                sign_one(args.tests, tests, args.build_tools, args.keystore, args.alias, password)
                password = None
                report = verify(app, args.build_tools, args.version, args.version_code,
                                args.certificate.lower(), migration_qa=True)
                output = subprocess.check_output([str(args.build_tools / 'apksigner'), 'verify', '--verbose',
                    '--print-certs', str(tests)], text=True)
                check_certificate(output, args.certificate.lower())
                check_test_manifest(manifest(tests, args.build_tools))
                artifacts = []
                for source in (app, tests):
                    target = args.output_dir / source.name
                    with target.open('xb') as out, source.open('rb') as inp:
                        os.chmod(target, 0o600)
                        shutil.copyfileobj(inp, out)
                    artifacts.append({'file': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
                report.update(artifacts=artifacts, isolatedMigrationQa=True, publicRelease=False)
                with (args.output_dir / 'verified.json').open('x') as out:
                    json.dump(report, out, indent=2)
                    out.write('\n')
        finally:
            password = None
        print('QA APKs signed and verified. This is NOT a public release.')
    except (ValueError, OSError, subprocess.SubprocessError):
        print('Signing not completed. No key/password changes were made.')
        if args.wait:
            input('Press Enter to close this window. ')
        return 1
    if args.wait:
        input('Press Enter to close this window. ')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
