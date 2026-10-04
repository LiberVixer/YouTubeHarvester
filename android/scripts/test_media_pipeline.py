import base64
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "app/src/main/res/raw/ytdlp"))
from yt_dlp import YoutubeDL

spec = importlib.util.spec_from_file_location("harvest_tracks", ROOT / "app/src/main/res/raw/harvest_tracks.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MediaPipelineTest(unittest.TestCase):
    def test_language_tags_cover_non_priority_languages_and_regions(self):
        for language, expected in {'de': 'deu', 'pt-BR': 'por', 'it': 'ita', 'ko': 'kor',
                                   'nl': 'nld', 'en_US': 'eng', 'yue': 'yue', 'xx': 'und'}.items():
            with self.subTest(language=language):
                self.assertEqual(expected, module.iso_language(language))

    def test_combined_fallback_keeps_selected_audio_for_explicit_mapping(self):
        formats = [dict(format_id='251', url='https://example.invalid/es', ext='webm', vcodec='none', acodec='opus'),
                   dict(format_id='18', url='https://example.invalid/en', ext='mp4', vcodec='avc1', acodec='mp4a', height=720)]
        with YoutubeDL({'quiet': True, 'allow_multiple_audio_streams': True}) as ydl:
            selected = list(ydl.build_format_selector('bv[height<=1080]+251/b[height<=1080]+251')(
                {'formats': formats, 'incomplete_formats': False}))[0]
        self.assertEqual([1], module.selected_audio_indices(selected, [{'format_id': '251'}]))

    def test_subtitle_download_requires_a_final_nonempty_file_and_no_explicit_failure(self):
        for success, contents, expected in [(None, b'WEBVTT\n', True), (True, b'WEBVTT\n', True),
                                            (False, b'WEBVTT\n', False), (None, None, False),
                                            (True, None, False), (None, b'', False)]:
            with self.subTest(success=success, contents=contents), tempfile.TemporaryDirectory() as directory:
                def download(filename, track, subtitle):
                    if contents is not None:
                        Path(filename).write_bytes(contents)
                    else:
                        Path(filename + '.part').write_bytes(b'partial')
                    return success, True

                settings = base64.urlsafe_b64encode(b'{}').decode()
                info = {'automatic_captions': {'en': [{'ext': 'vtt', 'url': 'https://example.invalid/en'}]}}
                with YoutubeDL({'quiet': True}) as ydl, patch.object(ydl, 'dl', side_effect=download):
                    processor = module.HarvestTracksPP(ydl, settings)
                    if expected:
                        self.assertTrue(processor._subtitle(info, 'auto:en', Path(directory), 0).is_file())
                    else:
                        with self.assertRaises(module.PostProcessingError):
                            processor._subtitle(info, 'auto:en', Path(directory), 0)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Host ffmpeg required')
    def test_real_mux_keeps_manual_and_auto_subtitles_and_selected_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=160x90:rate=10',
                            '-f', 'lavfi', '-i', 'sine=frequency=440', '-f', 'lavfi', '-i', 'sine=frequency=880',
                            '-t', '1', '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:v', 'mpeg4',
                            '-c:a', 'aac', str(source)], check=True)
            settings = {'audio': [{'format_id': 'es', 'language': 'es', 'name': 'Spanish'}],
                        'subtitles': ['manual:en', 'auto:en', 'manual:de', 'auto:fr']}
            encoded = base64.urlsafe_b64encode(json.dumps(settings).encode()).decode()
            vtt = lambda text: [{'ext': 'vtt', 'data': f'WEBVTT\n\n00:00:00.000 --> 00:00:00.900\n{text}\n'}]
            segment = Path(directory) / 'automatic.vtt'
            segment.write_text(vtt('automatic')[0]['data'])
            playlist = Path(directory) / 'automatic.m3u8'
            playlist.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXT-X-MEDIA-SEQUENCE:0\n'
                                f'#EXTINF:1.0,\n{segment.as_uri()}\n#EXT-X-ENDLIST\n')
            info = {'filepath': str(source), 'ext': 'mkv', 'id': 'test',
                    'requested_formats': [{'format_id': 'en', 'vcodec': 'mpeg4', 'acodec': 'aac'},
                                          {'format_id': 'es', 'vcodec': 'none', 'acodec': 'aac'}],
                    'subtitles': {'en': vtt('manual'), 'de': vtt('Deutsch')},
                    'automatic_captions': {'en': [{'ext': 'vtt', 'protocol': 'm3u8_native', 'url': playlist.as_uri()}]}}
            with YoutubeDL({'quiet': True, 'enable_file_urls': True, 'ffmpeg_location': shutil.which('ffmpeg')}) as ydl:
                processor = module.HarvestTracksPP(ydl, encoded)
                _, output = processor.run(info)
                metadata = processor.get_metadata_object(output['filepath'])
            report = json.loads((Path(directory) / 'final-media.json').read_text())
            self.assertEqual('90p', report['resolution'])
            self.assertEqual(['manual:en', 'auto:en', 'manual:de'], report['selections'])
            audio = [s for s in metadata['streams'] if s['codec_type'] == 'audio']
            captions = [s for s in metadata['streams'] if s['codec_type'] == 'subtitle']
            self.assertEqual(1, len(audio))
            self.assertEqual('spa', audio[0]['tags']['language'])
            self.assertEqual(3, len(captions))
            self.assertEqual('deu', captions[2]['tags']['language'])
            self.assertEqual(['en (manual)', 'en (automatic)', 'de (manual)'], report['subtitles'])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'Host ffmpeg required')
    def test_bundled_plugin_loads_through_real_ytdlp_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=160x90:rate=10',
                            '-f', 'lavfi', '-i', 'sine=frequency=440',
                            '-t', '0.2', '-c:v', 'mpeg4', '-c:a', 'aac', str(source)], check=True)
            plugin = root / 'plugins/yth/yt_dlp_plugins/postprocessor/harvest_tracks.py'
            plugin.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / 'app/src/main/res/raw/harvest_tracks.py', plugin)
            metadata = root / 'info.json'
            metadata.write_text(json.dumps({'id': 'fixture', 'title': 'Fixture', 'ext': 'mkv',
                'url': source.as_uri(), 'webpage_url': source.as_uri(), 'extractor': 'generic', 'extractor_key': 'Generic',
                'format_id': 'original', 'vcodec': 'mpeg4', 'acodec': 'aac', 'height': 90,
                'subtitles': {'en': [{'ext': 'vtt', 'data': 'WEBVTT\n\n00:00:00.000 --> 00:00:00.150\nOriginal\n'}]},
                'automatic_captions': {'en': [{'ext': 'vtt', 'data': 'WEBVTT\n\n00:00:00.000 --> 00:00:00.150\nAutomatic\n'}]}}))
            settings = {'audio': [{'format_id': 'original', 'language': 'en', 'name': 'Original'}],
                        'subtitles': ['manual:en', 'auto:en']}
            options = base64.urlsafe_b64encode(json.dumps(settings).encode()).decode()
            result = subprocess.run([sys.executable, str(ROOT / 'app/src/main/res/raw/ytdlp'),
                '--ignore-config', '--enable-file-urls', '--load-info-json', str(metadata),
                '--no-plugin-dirs', '--plugin-dirs', str(root / 'plugins'),
                '--use-postprocessor', f'HarvestTracks:when=after_move;settings={options}',
                '-o', str(root / 'downloaded.%(ext)s')], text=True, capture_output=True)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            report = json.loads((root / 'final-media.json').read_text())
            self.assertEqual('90p', report['resolution'])
            self.assertEqual(['manual:en', 'auto:en'], report['selections'])
            self.assertEqual(['Original'], report['audio'])
            self.assertTrue(Path(report['path']).is_file())
            self.assertFalse((root / 'downloaded.mkv').exists())


if __name__ == '__main__':
    unittest.main()
