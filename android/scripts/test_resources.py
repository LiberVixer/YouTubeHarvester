from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

RES = Path(__file__).resolve().parents[1] / 'app/src/main/res'


class TranslationResourcesTest(unittest.TestCase):
    def test_top_bar_uses_application_version_without_beta_label(self):
        source = RES.parent / 'java/com/liberivixer/youtubeharvester/ui/Components.kt'
        text = source.read_text(encoding='utf-8')
        self.assertIn('BuildConfig.VERSION_NAME', text)
        self.assertNotIn('R.string.beta', text)

    def test_all_ten_locales_have_matching_keys_and_format_arguments(self):
        files = sorted(RES.glob('values*/strings.xml'))
        self.assertEqual(10, len(files))
        base = ET.parse(RES / 'values/strings.xml').getroot()
        required = {e.attrib['name']: ''.join(e.itertext()) for e in base if e.get('translatable') != 'false'}
        # Plural categories differ by language and may repeat the same numbered argument.
        placeholders = lambda text: sorted(set(re.findall(r'(?<!%)%(\d+\$)?([sdf])', text)))
        for file in files:
            entries = list(ET.parse(file).getroot())
            values = {e.attrib['name']: ''.join(e.itertext()) for e in entries}
            self.assertEqual(len(entries), len(values), f'Duplicate resource in {file}')
            self.assertTrue(required.keys() <= values.keys(), f'Missing keys in {file}: {required.keys() - values.keys()}')
            for key, value in required.items():
                self.assertEqual(placeholders(value), placeholders(values[key]), f'{file.parent.name}/{key}')


if __name__ == '__main__':
    unittest.main()
