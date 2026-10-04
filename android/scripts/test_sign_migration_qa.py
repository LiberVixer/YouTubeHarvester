import hashlib
from contextlib import redirect_stdout
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from sign_migration_qa import check_test_manifest, main, sign_one, unlock_keystore
from verify_apk import MIGRATION_PACKAGE


class MigrationSigningTest(unittest.TestCase):
    def invoke(self, output, tty=True):
        command = ['sign_migration_qa', '--app', 'app', '--tests', 'tests', '--build-tools', 'tools',
                   '--keytool', 'keytool', '--keystore', 'key', '--output-dir', str(output),
                   '--certificate', '0' * 64, '--version', 'test', '--version-code', '1']
        with patch('sys.argv', command), patch('sys.stdin.isatty', return_value=tty), \
                patch('sign_migration_qa.getpass.getpass') as prompt, redirect_stdout(io.StringIO()):
            self.assertEqual(1, main())
            prompt.assert_not_called()

    def test_existing_directory_and_dangling_symlink_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'output'
            output.mkdir()
            marker = output / 'keep'
            marker.write_text('original')
            self.invoke(output)
            self.assertEqual('original', marker.read_text())
            link = Path(root) / 'link'
            link.symlink_to(Path(root) / 'absent')
            self.invoke(link)
            self.assertTrue(link.is_symlink())

    def test_noninteractive_password_input_is_refused_before_any_file_creation(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'output'
            self.invoke(output, tty=False)
            self.assertFalse(output.exists())

    def test_test_apk_cannot_target_public_beta_or_be_debuggable(self):
        root = ET.fromstring('<manifest><application/><instrumentation/></manifest>')
        root.set('package', MIGRATION_PACKAGE + '.test')
        instrument = root.find('instrumentation')
        instrument.set('name', 'androidx.test.runner.AndroidJUnitRunner')
        instrument.set('targetPackage', MIGRATION_PACKAGE)
        check_test_manifest(root)
        instrument.set('targetPackage', MIGRATION_PACKAGE.removesuffix('.migrationqa'))
        with self.assertRaises(ValueError):
            check_test_manifest(root)
        instrument.set('targetPackage', MIGRATION_PACKAGE)
        root.find('application').set('debuggable', 'true')
        with self.assertRaises(ValueError):
            check_test_manifest(root)

    def test_password_uses_only_pipe_not_args_or_environment(self):
        password = 'QA-only-not-a-real-signing-password'
        with patch('sign_migration_qa.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
            sign_one(Path('app'), Path('out'), Path('tools'), Path('key'), 'alias', password)
        args, kwargs = run.call_args
        self.assertNotIn(password, args[0])
        self.assertNotIn('env', kwargs)
        self.assertEqual((password + '\n' + password + '\n').encode(), kwargs['input'])
        self.assertIn('--debuggable-apk-permitted', args[0])
        self.assertIn('false', args[0])

    def test_unlock_checks_independently_pinned_certificate(self):
        password = 'QA-only-not-a-real-signing-password'
        cert = b'QA-public-certificate'
        with patch('sign_migration_qa.getpass.getpass', return_value=password), \
                patch('sign_migration_qa.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=cert)) as run:
            result = unlock_keystore(Path('keytool'), Path('key'), 'alias', hashlib.sha256(cert).hexdigest())
            self.assertEqual(password, result)
            self.assertNotIn(password, run.call_args.args[0])
            with self.assertRaises(ValueError):
                unlock_keystore(Path('keytool'), Path('key'), 'alias', '0' * 64)


if __name__ == '__main__':
    unittest.main()
