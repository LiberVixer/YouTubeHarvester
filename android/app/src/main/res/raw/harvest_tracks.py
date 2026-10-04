"""Bundled yt-dlp postprocessor: explicit tracks and verified publication metadata."""
import base64
import json
import os
from pathlib import Path

from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from yt_dlp.utils import ISO639Utils, PostProcessingError


def iso_language(language):
    root = language.lower().replace('_', '-').split('-')[0]
    if len(root) == 3:
        return root
    return ISO639Utils.short2long(root) or 'und'


def selected_audio_indices(info, selections):
    formats = info.get('requested_formats') or [info]
    audio = [f for f in formats if f.get('acodec') not in (None, 'none')]
    indices = []
    for selected in selections:
        index = next((n for n, f in enumerate(audio) if f.get('format_id') == selected['format_id']), None)
        if index is None:
            raise PostProcessingError('Selected audio format is absent from the downloaded file')
        indices.append(index)
    return indices


class HarvestTracksPP(FFmpegPostProcessor):
    def __init__(self, downloader=None, settings=''):
        super().__init__(downloader)
        self.settings = json.loads(base64.urlsafe_b64decode(settings))

    def _subtitle(self, info, selection, directory, index):
        mode, language = selection.split(':', 1)
        tracks = (info.get('automatic_captions') if mode == 'auto' else info.get('subtitles')) or {}
        candidates = tracks.get(language) or []
        candidates = [s for s in candidates if s.get('ext') in ('vtt', 'srt', 'ttml')]
        if not candidates:
            return None
        track = next((s for s in reversed(candidates) if s.get('ext') == 'vtt'), candidates[-1]).copy()
        path = directory / f'yth-subtitle-{index}.{track["ext"]}'
        if track.get('data') is not None:
            path.write_text(track['data'], encoding='utf-8')
        else:
            track['http_headers'] = {**(info.get('http_headers') or {}), **(track.get('http_headers') or {})}
            success, _ = self._downloader.dl(str(path), track, subtitle=True)
            # HLS WebVTT may return None after successfully writing the final file.
            if success is False:
                raise PostProcessingError('Selected subtitle download failed')
        if not path.is_file() or path.stat().st_size == 0:
            raise PostProcessingError('Selected subtitle file is missing or empty')
        return path

    def run(self, info):
        source = Path(info['filepath'])
        audio = self.settings.get('audio', [])
        subtitles = self.settings.get('subtitles', [])
        inputs = [source]
        delivered = []
        for index, selection in enumerate(subtitles):
            try:
                path = self._subtitle(info, selection, source.parent, index)
            except Exception as error:
                # Report the omission; never substitute manual/auto or a different language.
                self.report_warning(f'Subtitle {selection} unavailable: {type(error).__name__}')
                continue
            if path is not None:
                inputs.append(path)
                delivered.append(selection)
            else:
                self.report_warning(f'Subtitle {selection} is no longer available')

        delete = []
        self.to_screen('Verifying and mapping selected tracks')
        if audio or delivered:
            target = source.with_name(source.stem + '.tracks.mkv')
            options = ['-map', '0:v:0']
            if audio:
                for n in selected_audio_indices(info, audio):
                    options += ['-map', f'0:a:{n}']
            else:
                options += ['-map', '0:a?']
            for n in range(len(delivered)):
                options += ['-map', f'{n + 1}:0']
            options += ['-map_metadata', '0', '-map_chapters', '0', '-c', 'copy']
            if delivered:
                options += ['-c:s', 'srt']
            for n, track in enumerate(audio):
                options += [f'-metadata:s:a:{n}', f'language={iso_language(track["language"])}',
                            f'-metadata:s:a:{n}', f'title={track.get("name") or track["language"]}']
            for n, selection in enumerate(delivered):
                mode, language = selection.split(':', 1)
                title = language + (' (automatic)' if mode == 'auto' else ' (manual)')
                options += [f'-metadata:s:s:{n}', f'language={iso_language(language)}',
                            f'-metadata:s:s:{n}', f'title={title}']
            self.run_ffmpeg_multiple_files([str(p) for p in inputs], str(target), options)
            delete = [str(p) for p in inputs]
            info['filepath'] = str(target)
            info['ext'] = 'mkv'
        else:
            target = source

        metadata = self.get_metadata_object(str(target))
        streams = metadata.get('streams') or []
        video = next((s for s in streams if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
        if not video or not video.get('height'):
            raise PostProcessingError('The output has no verified video stream')
        audios = [s for s in streams if s.get('codec_type') == 'audio']
        captions = [s for s in streams if s.get('codec_type') == 'subtitle']
        if audio and len(audios) != len(audio):
            raise PostProcessingError('Output audio count differs from the selection')
        if len(captions) != len(delivered):
            raise PostProcessingError('Output subtitle count differs from the selection')
        labels = lambda tracks: [s.get('tags', {}).get('title') or s.get('tags', {}).get('language') or 'und' for s in tracks]
        result = {'path': str(target), 'resolution': f'{video["height"]}p',
                  'audio': labels(audios), 'subtitles': labels(captions), 'selections': delivered}
        path = source.parent / 'final-media.json'
        temporary = path.with_suffix('.json.tmp')
        with temporary.open('w', encoding='utf-8') as file:
            json.dump(result, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        return delete, info
