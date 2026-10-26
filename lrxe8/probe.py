from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
from itertools import zip_longest
import json
from pathlib import Path
import re
import threading

from .core import MediaError, find_tool, run


def probe(path: Path, cancel: threading.Event) -> dict:
    text = run([find_tool('ffprobe'), '-v', 'error', '-show_streams', '-show_format',
                '-show_chapters', '-of', 'json', str(path)], cancel, timeout=60)
    data = json.loads(text)
    videos = [s for s in data.get('streams', []) if s.get('codec_type') == 'video'
              and not s.get('disposition', {}).get('attached_pic')]
    if len(videos) != 1:
        raise MediaError('Bu sürüm tam olarak bir ana video akışı bekliyor; diğer içerikler korunmak üzere atlandı.')
    video = videos[0]
    if min(video.get('width', 0), video.get('height', 0)) < 16:
        raise MediaError('Video boyutu okunamadı veya geçersiz.')
    if video.get('field_order', 'unknown') not in {'unknown', 'progressive'}:
        raise MediaError('Taramalı video için alan zamanlamasını koruyan yol henüz doğrulanmadı; orijinal korundu.')
    duration = video.get('duration') or data.get('format', {}).get('duration')
    try:
        duration = float(duration)
        tb = Fraction(video['time_base'])
        if duration <= 0 or tb <= 0:
            raise ValueError()
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        raise MediaError('Kaynağın süresi veya zaman tabanı güvenilir biçimde okunamadı')
    data['video'] = video
    data['duration'] = duration
    # Static HDR can live in coded-frame SEI instead of stream metadata.
    # Inspect initial decoded frames and keep those locations explicit.
    if hdr(video):
        first = json.loads(run([find_tool('ffprobe'), '-v', 'error', '-select_streams', str(video['index']),
            '-read_intervals', '%+#8', '-show_frames', '-show_entries', 'frame_side_data', '-of', 'json', str(path)], cancel, timeout=60))
        video['frame_side_data'] = [side for frame in first.get('frames', []) for side in frame.get('side_data_list', [])]
    return data


SEMI_PLANAR = {'nv12': (8, '420'), 'nv21': (8, '420'), 'nv16': (8, '422'), 'nv24': (8, '444'),
               'p010': (10, '420'), 'p012': (12, '420'), 'p016': (16, '420'),
               'p210': (10, '422'), 'p212': (12, '422'), 'p216': (16, '422'),
               'p410': (10, '444'), 'p412': (12, '444'), 'p416': (16, '444')}


def pixel_properties(name: str):
    base = re.sub(r'(le|be)$', '', name or '')
    if base in SEMI_PLANAR:
        return (*SEMI_PLANAR[base], False)
    match = re.match(r'(yuvj?|yuva)(420|422|444)p(?:(\d+)(?:msb)?(le|be))?$', name or '')
    if match:
        return (int(match[3] or 8), match[2], match[1] == 'yuva')
    return (None, name, 'a' in (name or ''))


def same_or_deeper(source: str, output: str):
    """Output may carry more precision (8-bit source -> 10-bit AV1/HEVC), never less,
    and must keep chroma subsampling and alpha exactly."""
    a, b = pixel_properties(source), pixel_properties(output)
    if a[0] is None or b[0] is None:
        return a == b
    return b[1:] == a[1:] and b[0] >= a[0]


def hdr(video: dict):
    return video.get('color_transfer') in {'smpte2084', 'arib-std-b67'}


def important_side_data(stream: dict):
    return [s for s in stream.get('side_data_list', []) if any(name in s.get('side_data_type', '').lower()
            for name in ('mastering', 'content light', 'dovi', 'hdr', 'display matrix'))]


HDR_FIELDS = ('red_x', 'red_y', 'green_x', 'green_y', 'blue_x', 'blue_y', 'white_point_x',
              'white_point_y', 'min_luminance', 'max_luminance', 'max_content', 'max_average')


def static_hdr_fields(stream: dict):
    values = {}
    for side in stream.get('side_data_list', []) + stream.get('frame_side_data', []):
        if re.search(r'dovi|dolby vision|dynamic hdr|hdr dynamic|hdr10\+', side.get('side_data_type', ''), re.I):
            raise MediaError('Dinamik HDR/Dolby Vision metadata aktarımı doğrulanamıyor; orijinal korundu')
        for key in HDR_FIELDS:
            if key in side:
                value = Fraction(str(side[key]))
                # MaxCLL/MaxFALL zero means unspecified, not a zero-nit display.
                if key in {'max_content', 'max_average'} and value == 0:
                    continue
                if key in values and values[key] != value:
                    raise MediaError(f'Çelişen statik HDR metadata: {key}')
                values[key] = value
    return values


def frame_file(path: Path, metadata: dict, output: Path, cancel: threading.Event):
    run([find_tool('ffprobe'), '-v', 'error', '-select_streams', str(metadata['video']['index']),
         '-show_frames', '-show_entries', 'frame=pts,duration,pkt_duration,width,height,pix_fmt:frame_side_data',
         '-of', 'compact=p=0:nk=0', str(path)], cancel, stdout_path=output)


def frames(path: Path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if re.search(r'dovi|dolby vision|dynamic hdr|hdr dynamic|hdr10\+', line, re.I):
                raise MediaError('Dinamik HDR/Dolby Vision verisinin kayıpsız aktarımı bu sürümde doğrulanamıyor; orijinal korundu')
            fields = {key.rsplit(':', 1)[-1]: value for key, value in
                      (field.split('=', 1) for field in line.strip().split('|') if '=' in field)}
            if 'width' in fields:
                yield fields


def compare_timeline(a_path: Path, b_path: Path, a: dict, b: dict):
    atb, btb = Fraction(a['time_base']), Fraction(b['time_base'])
    # Permit only representational rounding. Never use a full-frame or percentage
    # duration tolerance that could hide dropped frames or cumulative VFR drift.
    tolerance = btb / 2
    first_a = first_b = last_a = last_b = end_a = end_b = None
    max_error = Fraction(0)
    count = 0
    a_hdr, b_hdr = static_hdr_fields(a), static_hdr_fields(b)
    for left, right in zip_longest(frames(a_path), frames(b_path)):
        if left is None or right is None:
            raise MediaError('Kare sayısı değişti')
        try:
            ap, bp = int(left['pts']) * atb, int(right['pts']) * btb
            ad = int(left.get('duration', left.get('pkt_duration', '0'))) * atb
            bd = int(right.get('duration', right.get('pkt_duration', '0'))) * btb
        except (KeyError, ValueError):
            raise MediaError('Eksik/geçersiz kare zaman damgası; zamanlama doğrulanamıyor')
        if ad <= 0 or bd <= 0:
            raise MediaError('Kare gösterim süresi eksik; tam zamanlama doğrulanamıyor')
        if btb > atb and btb >= ad / 10:
            raise MediaError('Çıktı zaman tabanı kare zamanlamasını koruyamayacak kadar kaba')
        if first_a is None:
            first_a, first_b = ap, bp
        if last_a is not None and (ap <= last_a or bp <= last_b):
            raise MediaError('Artmayan kare zaman damgası; sessiz zamanlama onarımı yapılmadı')
        for frame, stream in ((left, a), (right, b)):
            if (int(frame['width']), int(frame['height'])) != (a['width'], a['height']):
                raise MediaError('Bir karede çözünürlük değişti')
            if pixel_properties(frame['pix_fmt']) != pixel_properties(stream['pix_fmt']):
                raise MediaError('Bir karede bit derinliği/chroma/alpha değişti')
        if not same_or_deeper(left['pix_fmt'], right['pix_fmt']):
            raise MediaError('Bir karede bit derinliği/chroma/alpha azaldı')
        for key in HDR_FIELDS:
            def effective(frame, fallback):
                value = Fraction(frame[key]) if key in frame else fallback.get(key)
                if key in {'max_content', 'max_average'} and value == 0:
                    return fallback.get(key)
                return value
            av, bv = effective(left, a_hdr), effective(right, b_hdr)
            if av != bv:
                raise MediaError(f'Kare HDR metadata bilgisi korunmadı: {key}')
        error = abs((ap - first_a) - (bp - first_b))
        # With B-frame reordering a decoded frame's packet duration may describe
        # decoding-order spacing. Actual display intervals are successive PTS.
        # Compare every PTS, then the last display duration and the total span.
        if error > tolerance:
            raise MediaError(f'Kare {count}: zamanlama değişti ({float(error):.9f} sn)')
        max_error = max(max_error, error)
        last_a, last_b = ap, bp
        end_a, end_b = ap + ad, bp + bd
        count += 1
    if not count:
        raise MediaError('Video karesi yok')
    if abs((end_a - first_a) - (end_b - first_b)) > min(btb, ad / 10):
        raise MediaError('Video süresi değişti')
    try:
        afps, bfps = Fraction(a.get('avg_frame_rate', '0')), Fraction(b.get('avg_frame_rate', '0'))
        if afps > 0 and bfps > 0 and afps != bfps:
            raise MediaError('Ortalama kare hızı değişti')
    except (ValueError, ZeroDivisionError):
        pass
    return {'frames': count, 'max_timing_error_seconds': float(max_error),
            'source_duration': float(end_a - first_a), 'output_duration': float(end_b - first_b),
            'common_shift_seconds': float(first_b - first_a),
            'display_intervals': 'Every presentation timestamp compared; last-frame duration checked separately',
            'source_fps': a.get('avg_frame_rate'), 'output_fps': b.get('avg_frame_rate'),
            'source_time_base': str(atb), 'output_time_base': str(btb)}


def creation_time_equivalent(source, output):
    """Compare ISO dates without discarding differing or missing values.

    MOV/MP4 can expose the same creation time from both mvhd and mdta. FFprobe
    joins those values with ';'. Compare every value, with exact fractional
    seconds, instead of treating that redundant representation as data loss.
    """
    def instants(value):
        if not isinstance(value, str):
            return None
        result = set()
        for part in value.split(';'):
            match = re.fullmatch(r'(\d{4}-\d{2}-\d{2})[Tt ](\d{2}:\d{2}:\d{2})'
                                 r'(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})', part.strip())
            if not match:
                return None
            try:
                zone = '+00:00' if match[4] == 'Z' else match[4]
                moment = datetime.fromisoformat(f'{match[1]}T{match[2]}{zone}').astimezone(timezone.utc)
                fraction = Fraction('0.' + (match[3] or '0'))
                result.add((moment, fraction))
            except (ValueError, OverflowError):
                return None
        return result
    left, right = instants(source), instants(output)
    return left is not None and right is not None and len(left) == len(right) == 1 and left == right


def video_stream_checks(a: dict, b: dict):
    """Picture-level properties, usable on a few-frame capability encode as well."""
    if (a['width'], a['height']) != (b['width'], b['height']):
        raise MediaError('Kaynak çözünürlük değişti')
    if not same_or_deeper(a['pix_fmt'], b['pix_fmt']):
        raise MediaError(f"Bit derinliği, chroma örneklemesi veya alpha korunmadı: {a['pix_fmt']} → {b['pix_fmt']}")
    keys = ['sample_aspect_ratio', 'color_range', 'color_space', 'color_transfer', 'color_primaries']
    # H.264/HEVC/AV1 signal chroma siting only for 4:2:0; for 4:2:2/4:4:4 the
    # field is undefined in the output bitstream, so it cannot be compared.
    if pixel_properties(a['pix_fmt'])[1] == '420':
        keys.append('chroma_location')
    for key in keys:
        if a.get(key) not in (None, 'unknown', 'unspecified', 'N/A') and a.get(key) != b.get(key):
            raise MediaError(f'{key} korunmadı: {a.get(key)} → {b.get(key)}')
    if static_hdr_fields(a) != static_hdr_fields(b):
        raise MediaError('Statik HDR metadata bilgisi korunmadı')
    def display_metadata(stream):
        return [s for s in important_side_data(stream) if s.get('side_data_type') == 'Display Matrix']
    if display_metadata(a) != display_metadata(b):
        raise MediaError('Döndürme metadata bilgisi korunmadı')


def metadata_checks(source: dict, output: dict):
    video_stream_checks(source['video'], output['video'])
    a = source['video']
    ignore = {'encoder', 'major_brand', 'minor_version', 'compatible_brands', 'handler_name', 'vendor_id', 'duration', 'bps', 'number_of_frames', 'number_of_bytes', '_statistics_writing_app', '_statistics_writing_date_utc', '_statistics_tags'}
    def check_tags(left, right, context):
        destination = {k.lower(): v for k, v in right.get('tags', {}).items()}
        for key, value in left.get('tags', {}).items():
            actual = destination.get(key.lower())
            if key.lower() in ignore or actual == value:
                continue
            if key.lower() == 'creation_time' and creation_time_equivalent(value, actual):
                continue
            raise MediaError(f'Metadata korunmadı: {key} ({context}; kaynak={value!r}, çıktı={actual!r})')
    check_tags(source.get('format', {}), output.get('format', {}), 'dosya')
    if len(source['streams']) != len(output['streams']):
        raise MediaError('Akış sayısı değişti')
    for left, right in zip(source['streams'], output['streams']):
        if left['codec_type'] != right['codec_type']:
            raise MediaError('Akış türü değişti')
        check_tags(left, right, f"akış {left['index']}")
        if left.get('disposition', {}) != right.get('disposition', {}):
            raise MediaError('Akış disposition bilgisi değişti')
        if left['index'] != a['index']:
            for key in ('codec_name', 'channels', 'channel_layout', 'sample_rate', 'width', 'height'):
                if left.get(key) != right.get(key):
                    raise MediaError(f'Kopyalanan akış değişti: {key}')
    def chapters(data):
        return [(Fraction(c['start']) * Fraction(c['time_base']), Fraction(c['end']) * Fraction(c['time_base']), c.get('tags', {})) for c in data.get('chapters', [])]
    if chapters(source) != chapters(output):
        raise MediaError('Bölümler korunmadı')
    return {'dimensions': True, 'pixel_format': True, 'color_hdr': True, 'stream_metadata': True, 'chapters': True}


def validate_audio(source: Path, output: Path, metadata: dict, work: Path, cancel, shift: float):
    """Decode audio samples, not packet layout: remuxing may change packet boundaries."""
    checks = []
    for stream in metadata['streams']:
        if stream['codec_type'] != 'audio':
            continue
        digests = []
        for name, path in (('a', source), ('b', output)):
            digest = run([find_tool('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(path), '-map',
                          f"0:{stream['index']}", '-c:a', 'pcm_s32le', '-f', 'hash', '-hash', 'sha256', '-'], cancel)
            digests.append(digest.strip())
        if digests[0] != digests[1]:
            raise MediaError('Çözülmüş ses örnekleri değişti')
        checks.append({'stream': stream['index'], 'pcm_sha256': digests[0]})
    return checks


def validate_copied_streams(source: Path, output: Path, metadata: dict, cancel):
    hashes = []
    for stream in metadata['streams']:
        if stream['index'] == metadata['video']['index'] or stream['codec_type'] == 'attachment':
            continue
        values = []
        for path in (source, output):
            values.append(run([find_tool('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(path),
                '-map', f"0:{stream['index']}", '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], cancel).strip())
        if values[0] != values[1]:
            raise MediaError(f"Kopyalanan akış içeriği değişti: {stream['index']}")
        hashes.append({'stream': stream['index'], 'hash': values[0]})
    # Attachments are extradata; probe them with content hashes rather than packets.
    if any(s['codec_type'] == 'attachment' for s in metadata['streams']):
        values = []
        for path in (source, output):
            data = json.loads(run([find_tool('ffprobe'), '-v', 'error', '-select_streams', 't',
                '-show_streams', '-show_data_hash', 'sha256', '-of', 'json', str(path)], cancel))
            values.append([s.get('extradata_hash') for s in data.get('streams', [])])
        if not all(values[0]) or values[0] != values[1]:
            raise MediaError('Ek dosya içeriği doğrulanamadı')
    return hashes
