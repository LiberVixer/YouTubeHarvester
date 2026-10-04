import unittest
from verify_apk import PACKAGE, MIGRATION_PACKAGE, check_certificate, check_manifest, parse_tree

MANIFEST = f'''  E: manifest (line=2)
    A: package="{PACKAGE}" (Raw: "{PACKAGE}")
    A: http://schemas.android.com/apk/res/android:versionName(0x1)="test"
    A: http://schemas.android.com/apk/res/android:versionCode(0x2)=123
      E: application (line=3)
        A: http://schemas.android.com/apk/res/android:allowBackup(0x3)=false
          E: activity (line=4)
            A: http://schemas.android.com/apk/res/android:name(0x4)="{PACKAGE}.MainActivity"
            A: http://schemas.android.com/apk/res/android:exported(0x5)=true
              E: intent-filter (line=5)
                  E: action (line=6)
                    A: http://schemas.android.com/apk/res/android:name(0x4)="android.intent.action.MAIN"
'''


class VerifyApkTest(unittest.TestCase):
    def test_migration_package_requires_explicit_mode_and_public_stays_fail_closed(self):
        root = parse_tree(MANIFEST)
        root.set("package", MIGRATION_PACKAGE)
        with self.assertRaises(ValueError):
            check_manifest(root, "test", 123)
        check_manifest(root, "test", 123, migration_qa=True)
        root.set("package", PACKAGE)
        with self.assertRaises(ValueError):
            check_manifest(root, "test", 123, migration_qa=True)

    def test_release_manifest(self):
        self.assertEqual([f"{PACKAGE}.MainActivity"], check_manifest(parse_tree(MANIFEST), "test", 123))

    def test_debug_and_wrong_version_rejected(self):
        root = parse_tree(MANIFEST)
        with self.assertRaises(ValueError):
            check_manifest(root, "test", 124)
        root.find("application").set("debuggable", "true")
        with self.assertRaises(ValueError):
            check_manifest(root, "test", 123)

    def test_exported_unknown_and_preview_rejected(self):
        for name in ("evil.Activity", "androidx.compose.ui.tooling.PreviewActivity"):
            root = parse_tree(MANIFEST)
            root.find("application/activity").set("name", name)
            with self.assertRaises(ValueError):
                check_manifest(root, "test", 123)

    def test_system_service_requires_its_permission(self):
        import xml.etree.ElementTree as ET
        root = parse_tree(MANIFEST)
        node = ET.SubElement(root.find("application"), "service", {
            "name": "androidx.work.impl.background.systemjob.SystemJobService", "exported": "true"
        })
        with self.assertRaises(ValueError):
            check_manifest(root, "test", 123)
        node.set("permission", "android.permission.BIND_JOB_SERVICE")
        check_manifest(root, "test", 123)

    def test_certificate_and_debug_identity(self):
        digest = "a" * 64
        output = f"Signer #1 certificate SHA-256 digest: {digest}\n"
        check_certificate(output, digest)
        with self.assertRaises(ValueError):
            check_certificate(output, "b" * 64)
        output += "Signer #1 certificate DN: CN=Android Debug, O=Android\n"
        with self.assertRaises(ValueError):
            check_certificate(output, digest)
        check_certificate(output, digest, allow_legacy=True)

    def test_unrecognized_manifest_rejected(self):
        with self.assertRaises(ValueError):
            parse_tree("unexpected tool output")


if __name__ == "__main__":
    unittest.main()
