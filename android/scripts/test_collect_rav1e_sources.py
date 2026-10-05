import unittest

from collect_rav1e_sources import registry_packages


class CargoSourceTests(unittest.TestCase):
    def lock(self, source, checksum):
        return ('[[package]]\nname="crate"\nversion="1.0"\nsource="' + source +
                '"\nchecksum="' + checksum + '"\n').encode()

    def test_only_locked_registry_sources_accepted(self):
        source = "registry+https://github.com/rust-lang/crates.io-index"
        self.assertEqual(len(registry_packages(self.lock(source, "a" * 64))), 1)
        with self.assertRaises(ValueError):
            registry_packages(self.lock(source, "bad"))
        with self.assertRaises(ValueError):
            registry_packages(self.lock("git+https://example.com/repo", "a" * 64))

    def test_local_target_is_not_downloaded(self):
        self.assertEqual(registry_packages(b'[[package]]\nname="rav1e"\nversion="0.7.1"\n'), [])


if __name__ == "__main__":
    unittest.main()
