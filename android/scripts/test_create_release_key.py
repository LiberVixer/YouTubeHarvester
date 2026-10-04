"""Signing-key safety checks; never use these test passwords for real releases."""
from contextlib import redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch

from create_release_key import main


class CreateReleaseKeyTest(unittest.TestCase):
    def invoke(self, key, passwords, runner=None):
        with patch('sys.argv', ['create_release_key', '--keystore', str(key)]), \
                patch('create_release_key.getpass.getpass', side_effect=passwords), \
                patch('create_release_key.subprocess.run', side_effect=runner) as run:
            output = io.StringIO()
            previous = os.umask(0o022)
            try:
                with redirect_stdout(output):
                    main()
            finally:
                os.umask(previous)
            return output.getvalue(), run

    def test_existing_key_and_certificate_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            key = Path(root) / 'release.p12'
            for path in (key, key.with_suffix('.cert.pem')):
                path.write_text('keep')
                with self.assertRaises(SystemExit):
                    self.invoke(key, [])
                self.assertEqual('keep', path.read_text())
                path.unlink()

    def test_dangling_key_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as root:
            key = Path(root) / 'release.p12'
            key.symlink_to(Path(root) / 'absent')
            with self.assertRaises(SystemExit):
                self.invoke(key, [])
            self.assertTrue(key.is_symlink())

    def test_bad_password_does_not_create_output_directory(self):
        with tempfile.TemporaryDirectory() as root:
            key = Path(root) / 'new' / 'release.p12'
            for values in (['short'], ['qa-password-12-plus', 'different-confirmation']):
                with self.assertRaises(SystemExit):
                    self.invoke(key, values)
                self.assertFalse(key.parent.exists())

    def test_private_permissions_export_and_public_fingerprint(self):
        with tempfile.TemporaryDirectory() as root:
            key = Path(root) / 'new' / 'release.p12'
            cert = key.with_suffix('.cert.pem')
            der = b'unit-test-public-certificate'
            password = 'qa-password-never-use-for-release'

            def runner(command, **kwargs):
                self.assertNotIn(password, command)
                self.assertTrue(kwargs['check'])
                self.assertEqual(password, kwargs['env']['YTH_KEY_PASSWORD'])
                if '-genkeypair' in command:
                    key.write_bytes(b'unit-test-key')
                else:
                    self.assertIn('-exportcert', command)
                    cert.write_text(ssl.DER_cert_to_PEM_cert(der))

            output, run = self.invoke(key, [password, password], runner)
            self.assertEqual(2, run.call_count)
            self.assertEqual(0o700, key.parent.stat().st_mode & 0o777)
            for path in (key, cert):
                self.assertEqual(0o600, path.stat().st_mode & 0o777)
            self.assertIn(hashlib.sha256(der).hexdigest(), output)
            self.assertNotIn(password, output)


if __name__ == '__main__':
    unittest.main()
