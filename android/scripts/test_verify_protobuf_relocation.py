import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from verify_protobuf_relocation import verify


class RelocationTests(unittest.TestCase):
    def test_invalid_asm_tools_rejected(self):
        with self.assertRaises(ValueError):
            verify(Path("missing"), Path("missing"), Path("missing"), [Path("asm-9.9.jar")] * 3)

    def test_changed_instructions_and_extra_classes_rejected(self):
        java = Path(os.environ.get("JAVA_HOME", ""))
        jars = [Path(p) for p in os.environ.get("YTH_ASM_CLASSPATH", "").split(":") if p]
        if not (java / "bin/javac").is_file() or len(jars) != 3:
            self.skipTest("JDK and YTH_ASM_CLASSPATH are required for the bytecode fixture")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def build(package, value, name):
                folder = root / name
                folder.mkdir()
                source = folder / "Example.java"
                source.write_text('package ' + package + '; public class Example {'
                                  ' public String value() { return "' + value + '"; }}')
                subprocess.run([str(java / "bin/javac"), "-d", str(folder), str(source)],
                               check=True, capture_output=True)
                jar = root / (name + ".jar")
                with zipfile.ZipFile(jar, "w") as archive:
                    for path in folder.rglob("*.class"):
                        archive.write(path, path.relative_to(folder))
                return jar

            original = build("com.google.protobuf", "com.google.protobuf.Example", "original")
            relocated = build("androidx.datastore.preferences.protobuf",
                              "androidx.datastore.preferences.protobuf.Example", "relocated")
            self.assertEqual(verify(original, relocated, java, jars)["bytecodeAndMetadataMatches"], 1)
            changed = build("androidx.datastore.preferences.protobuf", "changed", "changed")
            with self.assertRaises(subprocess.CalledProcessError):
                verify(original, changed, java, jars)
            with zipfile.ZipFile(relocated, "a") as archive:
                archive.writestr("Extra.class", b"not part of the original library")
            with self.assertRaises(subprocess.CalledProcessError):
                verify(original, relocated, java, jars)


if __name__ == "__main__":
    unittest.main()
