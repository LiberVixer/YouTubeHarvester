import io
import struct
import unittest
import zipfile
from elf_alignment import inspect_native


class ElfAlignmentTest(unittest.TestCase):
    def elf(self, alignment):
        data = bytearray(120)
        data[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<Q', data, 32, 64)
        struct.pack_into('<HH', data, 54, 56, 1)
        struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 0, 0, 0, 120, 120, alignment)
        return data

    def test_aligned_elf(self):
        self.assertEqual(1, inspect_native(self.elf(16384), 'lib.so'))

    def test_rejects_unaligned_library_inside_runtime_archive(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('usr/lib/libwebp.so', self.elf(4096))
        with self.assertRaisesRegex(ValueError, 'libwebp.so'):
            inspect_native(buffer.getvalue(), 'libffmpeg.zip.so')
