from __future__ import annotations

import csv
from fractions import Fraction
import math
from pathlib import Path
import re
import threading
import time

from .core import MediaError, Cancelled, Options, find_tool, run
from .probe import (probe, hdr, pixel_properties, frame_file, compare_timeline, metadata_checks,
                    video_stream_checks, validate_audio, validate_copied_streams)

ENCODERS = {'av1_nvenc': 'av1', 'hevc_nvenc': 'hevc', 'h264_nvenc': 'h264',
            'libsvtav1': 'av1', 'libx265': 'hevc', 'libx264': 'h264'}
# Preference inside a codec family: hardware first, then the matching software encoder.
PLAN = {'auto': ['av1_nvenc', 'hevc_nvenc', 'libsvtav1', 'libx265', 'h264_nvenc', 'libx264'],
        'av1': ['av1_nvenc', 'libsvtav1'], 'hevc': ['hevc_nvenc', 'libx265'], 'h264': ['h264_nvenc', 'libx264']}
# Constant-quality scale per encoder: (best usable, worst searched, first guess, search step).
# Numbers are never assumed equivalent across encoders; each one is measured.
QSCALE = {'av1_nvenc': (10, 52, 26, 6), 'libsvtav1': (10, 52, 26, 6),
          'hevc_nvenc': (8, 40, 22, 4), 'libx265': (6, 36, 19, 4),
          'h264_nvenc': (8, 38, 20, 4), 'libx264': (6, 34, 17, 4)}
SAMPLE_MARGIN = {'vmaf_mean': .3, 'vmaf_low': .5}
# HEVC levels: (name, max luma picture size, max luma samples/s, high-tier max bit rate).
HEVC_LEVELS = [('4.1', 2228224, 133693440, 50e6), ('5', 8912896, 267386880, 100e6),
               ('5.1', 8912896, 534773760, 160e6), ('5.2', 8912896, 1069547520, 240e6),
               ('6', 35651584, 1069547520, 240e6), ('6.1', 35651584, 2139095040, 480e6),
               ('6.2', 35651584, 4278190080, 800e6)]


def hevc_level(video: dict, fps: float):
    """Lowest level for the picture size and frame rate (4.1 minimum), so a 4K60
    file says 5.1 instead of 6.2: players refuse levels they do not support."""
    pixels = video['width'] * video['height']
    for level in HEVC_LEVELS:
        if pixels <= level[1] and pixels * fps <= level[2]:
            return level
    return HEVC_LEVELS[-1]


class Progress:
    """Turns FFmpeg's -progress file into throttled percentage notifications."""

    def __init__(self, path: Path, total_frames: int, notify, label: str):
        self.path, self.total, self.notify, self.label = path, max(1, total_frames), notify, label
        self.last = 0.0
        path.unlink(missing_ok=True)

    def args(self):
        return ['-progress', str(self.path), '-stats_period', '1']

    def __call__(self):
        now = time.monotonic()
        if now - self.last < 1.5:
            return
        self.last = now
        try:
            with self.path.open('rb') as stream:
                stream.seek(max(0, self.path.stat().st_size - 2048))
                frames = re.findall(rb'frame=(\d+)', stream.read())
        except OSError:
            return
        if frames:
            self.notify(f'{self.label} · %{min(99, int(100 * int(frames[-1]) / self.total))}')


class Video:
    def __init__(self, options: Options, cancel: threading.Event, notify):
        self.options, self.cancel, self.notify = options, cancel, notify
        self.ffmpeg = find_tool('ffmpeg')
        self.ffprobe = find_tool('ffprobe')
        self.threads = options.worker_threads
        self.encoder_list = run([self.ffmpeg, '-hide_banner', '-encoders'], cancel, timeout=20)
        self.filters = run([self.ffmpeg, '-hide_banner', '-filters'], cancel, timeout=20)
        if 'libvmaf' not in self.filters:
            raise MediaError('Bu FFmpeg derlemesinde libvmaf yok; görüntü kalitesi doğrulanamaz.')
        self.failures = []
        self.hardware_allowed = True
        self.resize_budget = lambda ram, gpu: None
        self.formats = {}
        self.reference_cache = {}

    # ---------------------------------------------------------------- planning
    def plan(self, metadata: dict, suffix: str):
        names = []
        for encoder in PLAN[self.options.compatibility]:
            if suffix == '.mov' and ENCODERS[encoder] == 'av1':
                # FFmpeg refuses AV1 in QuickTime MOV; MOV sources stay MOV (HEVC/H.264).
                continue
            if suffix == '.webm' and ENCODERS[encoder] != 'av1':
                continue
            software = 'nvenc' not in encoder
            if software and not self.options.software:
                continue
            if not software and not self.hardware_allowed:
                continue
            if not re.search(r'\b' + encoder + r'\b', self.encoder_list):
                continue
            names.append(encoder)
        # 4:2:2 / 4:4:4 sources: put encoders that can keep the chroma layout first.
        chroma = pixel_properties(metadata['video']['pix_fmt'])[1]
        if chroma != '420':
            names.sort(key=lambda name: not self.target_format(name, metadata['video'], quiet=True))
        return names

    def supported_formats(self, encoder: str):
        if encoder not in self.formats:
            text = run([self.ffmpeg, '-hide_banner', '-h', f'encoder={encoder}'], self.cancel, timeout=20)
            match = re.search(r'Supported pixel formats: ([^\r\n]+)', text)
            self.formats[encoder] = match.group(1).split() if match else []
        return self.formats[encoder]

    def target_format(self, encoder: str, video: dict, quiet=False):
        """Same chroma/alpha as the source. AV1/HEVC get 10-bit even for 8-bit sources:
        the extra precision removes encoder banding in dark gradients and usually
        makes the file smaller at equal quality. H.264 stays at source depth for
        player compatibility."""
        depth, chroma, alpha = pixel_properties(video['pix_fmt'])
        if depth is None or alpha:
            if quiet:
                return None
            raise MediaError(f"{video['pix_fmt']} (alfa/özel piksel biçimi) için görüntüyü birebir koruyan bir video kodlama yolu yok")
        formats = self.supported_formats(encoder)
        depths = [max(depth, 10), depth] if ENCODERS[encoder] in {'av1', 'hevc'} else [depth]
        for wanted in dict.fromkeys(depths):
            matches = [fmt for fmt in formats if pixel_properties(fmt) == (wanted, chroma, False)
                       and 'msb' not in fmt and not fmt.endswith('be')]
            if video['pix_fmt'] in matches:
                return video['pix_fmt']
            # Prefer planar formats; NVENC takes p010/nv12 natively.
            matches.sort(key=lambda fmt: (('nvenc' in encoder) != fmt.startswith(('p0', 'nv')), fmt.startswith('yuvj'), fmt))
            if matches:
                return matches[0]
        if quiet:
            return None
        raise MediaError(f"{encoder}, {video['pix_fmt']} ({chroma}, {depth} bit) biçimini koruyamıyor")

    # ---------------------------------------------------------------- commands
    @staticmethod
    def source_video_bitrate(metadata: dict):
        video = metadata['video']
        try:
            if float(video.get('bit_rate') or 0) > 0:
                return float(video['bit_rate'])
            total = float(metadata.get('format', {}).get('bit_rate') or 0)
            others = sum(float(s.get('bit_rate') or 0) for s in metadata['streams'] if s['index'] != video['index'])
            if total > others:
                return total - others
        except (TypeError, ValueError):
            pass
        return 0.0

    def encode_options(self, encoder: str, quality: int, video: dict, metadata: dict | None = None):
        pixel = self.target_format(encoder, video)
        result = ['-pix_fmt', pixel]
        threads = str(self.threads)
        if 'nvenc' in encoder:
            # With -b:v 0 and no maxrate NVENC silently applies a level-derived
            # bitrate ceiling (~35 Mbit/s for 4K60 HEVC) and ignores lower CQ values.
            # Cap peaks at 1.5x the source instead: never needed above that.
            # Above the level's high-tier limit NVENC also misbehaves: AV1 at an
            # 800 Mbit/s ceiling ignored CQ completely on a lossless 4K source.
            # HEVC and AV1 share the level grid (picture size, samples/s, rate).
            source_rate = self.source_video_bitrate(metadata) if metadata else 0
            cap = min(800e6, max(30e6, source_rate * 1.5))
            level = []
            if encoder in {'hevc_nvenc', 'av1_nvenc'}:
                name, _, _, level_rate = hevc_level(video, self.fps(video))
                cap = min(cap, level_rate)
                # AV1 NVENC rejects an explicit level; the capped rate makes it pick one.
                level = ['-level', name, '-tier', 'high'] if encoder == 'hevc_nvenc' else ['-tier', '1']
            else:
                cap = min(cap, 240e6)
            cap = int(cap)
            result += ['-preset', 'p6', '-tune', 'hq', '-rc', 'vbr', '-cq', str(quality), '-b:v', '0',
                       '-maxrate', str(cap), '-bufsize', str(cap * 2),
                       '-rc-lookahead', '16', '-spatial-aq', '1', *level]
        elif encoder == 'libsvtav1':
            result += ['-preset', '6', '-crf', str(quality), '-svtav1-params', f'lp={min(6, max(1, self.threads // 4))}:tune=0']
        elif encoder == 'libx265':
            # aq-mode 3 biases bits towards dark, flat areas where banding shows first.
            result += ['-preset', 'medium', '-crf', str(quality), '-x265-params',
                       f'pools={threads}:aq-mode=3:log-level=error']
        else:
            result += ['-preset', 'slow', '-crf', str(quality), '-aq-mode', '3', '-threads', threads]
        for field, flag in [('color_range', '-color_range'), ('color_space', '-colorspace'),
                            ('color_transfer', '-color_trc'), ('color_primaries', '-color_primaries')]:
            if video.get(field) not in (None, 'unknown', 'unspecified'):
                result += [flag, video[field]]
        return result

    def command(self, source: Path, dest: Path, metadata: dict, encoder: str, quality: int,
                segment: tuple[float, float] | None = None, frames: int | None = None, progress: Progress | None = None):
        video = metadata['video']
        args = [self.ffmpeg, '-hide_banner', '-v', 'error', '-nostdin', '-y' if segment or frames else '-n',
                '-threads', str(self.threads)]
        if progress:
            args += progress.args()
        if segment:
            args += ['-ss', f'{segment[0]:.6f}']
        else:
            args += ['-copyts']
        args += ['-noautorotate', '-i', str(source)]
        if segment or frames:
            if segment:
                args += ['-t', f'{segment[1]:.6f}']
            args += ['-map', f"0:{video['index']}", '-an', '-sn', '-dn']
            if frames:
                args += ['-frames:v', str(frames)]
            index = 0
        else:
            args += ['-map', '0', '-map_metadata', '0', '-map_chapters', '0', '-c', 'copy']
            index = sum(1 for stream in metadata['streams'] if stream['codec_type'] == 'video' and stream['index'] < video['index'])
        tb = Fraction(video['time_base'])
        args += [f'-c:v:{index}', encoder, f'-fps_mode:v:{index}', 'passthrough',
                 f'-enc_time_base:v:{index}', f'{tb.numerator}:{tb.denominator}']
        args += self.encode_options(encoder, quality, video, metadata)
        if video.get('chroma_location') not in (None, 'unknown', 'unspecified'):
            args += ['-chroma_sample_location', video['chroma_location']]
        if ENCODERS[encoder] == 'av1' and video.get('chroma_location') in {'left', 'topleft'}:
            # NVENC may omit AV1 sample-position signaling. Preserve the source
            # YUV sample geometry explicitly; this edits signaling, not pixels.
            position = {'left': 'vertical', 'topleft': 'colocated'}[video['chroma_location']]
            args += [f'-bsf:v:{index}', f'av1_metadata=chroma_sample_position={position}']
        if dest.suffix.lower() in {'.mp4', '.mov', '.m4v'}:
            args += ['-movflags', '+faststart+use_metadata_tags']
            if ENCODERS[encoder] == 'hevc':
                args += [f'-tag:v:{index}', 'hvc1']
        return args + [str(dest)]

    # ---------------------------------------------------------------- metrics
    def metric(self, source: Path, candidate: Path, metadata: dict, work: Path, segment=None,
               subsample=1, label='Kalite ölçülüyor'):
        """One decode pass: VMAF (+ reference ceiling), chroma PSNR and CAMBI banding."""
        source, candidate, work = source.resolve(), candidate.resolve(), work.resolve()
        video = metadata['video']
        pixels = video['width'] * video['height']
        four_k = pixels >= 3840 * 2160 * .75
        model = 'vmaf_4k_v0.6.1' if four_k else 'vmaf_v0.6.1'
        # The 1080p model scores an untouched high-motion source below 100.
        # Measure that ceiling and judge the encode by its distance to it.
        ceiling = not four_k
        threads = max(2, self.threads)
        out_props = self.probe_pixel_format(candidate)
        src_depth, chroma, _ = pixel_properties(video['pix_fmt'])
        depth = max(src_depth, out_props[0])
        fmt = {'420': 'yuv420p', '422': 'yuv422p', '444': 'yuv444p'}[chroma] + ('' if depth == 8 else f'{depth}le')
        cambi = 'name=cambi\\:full_ref=true' + ('\\:eotf=pq' if video.get('color_transfer') == 'smpte2084' else '')
        trim = f'trim=duration={segment[1]:.6f},' if segment else ''
        for name in ('q.csv', 'c.csv'):
            (work / name).unlink(missing_ok=True)
        common = f'n_threads={threads}:n_subsample={subsample}:shortest=1:repeatlast=0:log_fmt=csv'
        # Frames are paired by decode index, not by timestamp: container rounding
        # (e.g. 1 ms MKV ticks at 60 fps) must not pair a frame with its neighbour.
        # Exact PTS equality is verified separately by compare_timeline.
        graph = (f"[0:{video['index']}]{trim}settb=1,setpts=N,format={fmt},split={3 if ceiling else 1}"
                 + ('[r1][r2][r3];' if ceiling else '[r1];')
                 + f"[1:v:0]settb=1,setpts=N,format={fmt}[d];"
                 + f"[d][r1]libvmaf=model=version={model}:{common}:log_path=q.csv:feature='name=psnr|{cambi}'[o1]")
        maps = ['-map', '[o1]']
        if ceiling:
            graph += f";[r2][r3]libvmaf=model=version={model}:{common}:log_path=c.csv[o2]"
            maps += ['-map', '[o2]']
        args = [self.ffmpeg, '-hide_banner', '-nostdin', '-v', 'error']
        total = int(round((segment[1] if segment else metadata['duration']) * self.fps(video))) or 1
        progress = Progress(work / 'metric.progress', total, self.notify, label) if not segment else None
        if progress:
            args += progress.args()
        if segment:
            args += ['-ss', f'{segment[0]:.6f}']
        args += ['-threads', str(self.threads), '-noautorotate', '-i', str(source),
                 '-threads', str(self.threads), '-noautorotate', '-i', str(candidate),
                 '-filter_complex', graph, *maps, '-f', 'null', '-']
        # libvmaf's Windows log writer cannot reliably open Unicode absolute paths;
        # each child gets the job folder as cwd and ASCII-only log names.
        run(args, self.cancel, timeout=self.options.sample_timeout if segment else None, cwd=work,
            tick=progress)
        rows = self.read_csv(work / 'q.csv')
        if not rows:
            raise MediaError('VMAF sonuç dosyası oluşturulamadı; görüntü kalitesi doğrulanamadı')
        ceilings = [row['vmaf'] for row in self.read_csv(work / 'c.csv')] if ceiling else []
        if ceiling and len(ceilings) != len(rows):
            raise MediaError('VMAF referans ölçümü eksik; görüntü kalitesi doğrulanamadı')
        scores = []
        for number, row in enumerate(rows):
            value = row['vmaf'] + (100 - ceilings[number] if ceiling else 0)
            if not math.isfinite(value):
                raise MediaError('VMAF geçersiz değer döndürdü')
            scores.append(min(100.0, value))
        def mean(key):
            return sum(row[key] for row in rows) / len(rows)
        def percentile(values, fraction):
            ordered = sorted(values)
            return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]
        added = [row.get('cambi_full_reference', 0.0) for row in rows]
        result = {
            'frames_measured': len(rows) * subsample if subsample > 1 else len(rows),
            'frames_scored': len(rows), 'vmaf_model': model, 'vmaf_reference_ceiling_used': ceiling,
            'vmaf': sum(scores) / len(scores), 'vmaf_low': percentile(scores, .02), 'vmaf_min': min(scores),
            'psnr_y': mean('psnr_y'), 'psnr_cb': mean('psnr_cb'), 'psnr_cr': mean('psnr_cr'),
            'cambi_added_mean': sum(added) / len(added), 'cambi_added_high': percentile(added, .98),
            'cambi_output_mean': mean('cambi'), 'cambi_output_high': percentile([row['cambi'] for row in rows], .98),
            'cambi_source_mean': mean('cambi_source'),
            'compared_format': fmt, 'resolution': [video['width'], video['height']],
            'note': ('VMAF HDR için kalibre değildir; göreli sadakat ölçüsü olarak kullanıldı.' if hdr(video)
                     else 'VMAF algısal model skorudur; piksel eşitliği garantisi değildir.'),
        }
        return result

    @staticmethod
    def read_csv(path: Path):
        if not path.is_file() or path.stat().st_size == 0:
            return []
        rows = []
        with path.open(newline='', encoding='utf-8') as stream:
            for row in csv.DictReader(stream):
                parsed = {}
                for key, value in row.items():
                    if key is None:
                        continue
                    try:
                        parsed[key.strip()] = float(value)
                    except (TypeError, ValueError):
                        pass
                if 'vmaf' in parsed:
                    rows.append(parsed)
        return rows

    def probe_pixel_format(self, path: Path):
        text = run([self.ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=pix_fmt',
                    '-of', 'default=nw=1:nk=1', str(path)], self.cancel, timeout=60)
        return pixel_properties(text.strip().splitlines()[0] if text.strip() else '')

    def quality_problems(self, metrics, margin=False):
        limits = self.options.thresholds
        extra = SAMPLE_MARGIN if margin else {}
        problems = []
        if metrics['vmaf'] < limits['vmaf_mean'] + extra.get('vmaf_mean', 0):
            problems.append(f"VMAF ort. {metrics['vmaf']:.2f} < {limits['vmaf_mean']}")
        if metrics['vmaf_low'] < limits['vmaf_low'] + extra.get('vmaf_low', 0):
            problems.append(f"VMAF en kötü %2 {metrics['vmaf_low']:.2f} < {limits['vmaf_low']}")
        scale = .8 if margin else 1
        floor = limits['cambi_floor'] * scale
        if metrics['cambi_added_mean'] > limits['cambi_mean'] * scale and metrics['cambi_output_mean'] > floor:
            problems.append(f"bantlanma artışı {metrics['cambi_added_mean']:.2f} > {limits['cambi_mean']}")
        if metrics['cambi_added_high'] > limits['cambi_high'] * scale and metrics['cambi_output_high'] > 2 * floor:
            problems.append(f"yerel bantlanma {metrics['cambi_added_high']:.2f} > {limits['cambi_high']}")
        # VMAF ignores colour planes. Colour may not be degraded disproportionately:
        # it has to reach the absolute floor or stay within 2 dB of luma fidelity
        # (grainy sources legitimately have lower PSNR in every plane).
        chroma = min(metrics['psnr_cb'], metrics['psnr_cr'])
        if chroma < limits['chroma_psnr'] and chroma < metrics['psnr_y'] - 2:
            problems.append(f'renk (chroma) PSNR {chroma:.1f} dB < {limits["chroma_psnr"]}')
        return problems

    # ---------------------------------------------------------------- analysis
    @staticmethod
    def fps(video: dict):
        for key in ('avg_frame_rate', 'r_frame_rate'):
            try:
                value = float(Fraction(video.get(key, '0/1')))
                if value > 0:
                    return value
            except (ValueError, ZeroDivisionError):
                pass
        return 30.0

    def segments(self, source: Path, metadata: dict, work: Path):
        """Representative sample windows: the most detailed/moving scenes (hard for
        VMAF) plus the smoothest one (where banding appears)."""
        duration = metadata['duration']
        length = min(self.options.sample_seconds, duration)
        if duration <= 3.5 * length:
            return [{'offset': 0.0, 'length': duration, 'spatial_detail': None, 'motion': None, 'reason': 'tamamı'}]
        count = 5 if duration > 60 else 4
        offsets = [round((duration - length) * i / (count - 1), 6) for i in range(count)]
        scenes = []
        for offset in offsets:
            raw = work / 'analysis.gray'
            run([self.ffmpeg, '-hide_banner', '-v', 'error', '-nostdin', '-y', '-ss', f'{offset:.6f}',
                 '-threads', str(self.threads), '-noautorotate', '-i', str(source), '-t', f'{length:.6f}',
                 '-map', f"0:{metadata['video']['index']}", '-vf', 'scale=160:90,fps=4,format=gray',
                 '-an', '-sn', '-dn', '-f', 'rawvideo', str(raw)], self.cancel, timeout=self.options.sample_timeout)
            data = raw.read_bytes()
            raw.unlink(missing_ok=True)
            frames = [data[i:i + 14400] for i in range(0, len(data) - 14399, 14400)]
            if not frames:
                raise MediaError('Örnek sahne çözülemedi')
            spatial = sum(sum(abs(frame[i] - frame[i - 1]) for i in range(1, len(frame), 3) if i % 160)
                          / (len(frame) / 3) for frame in frames) / len(frames)
            motion = sum(sum(abs(x - y) for x, y in zip(left[::3], right[::3])) / 4800
                         for left, right in zip(frames, frames[1:])) / max(1, len(frames) - 1)
            scenes.append({'offset': offset, 'length': length, 'spatial_detail': spatial, 'motion': motion})
        hard = sorted(scenes, key=lambda s: s['spatial_detail'] + s['motion'], reverse=True)
        chosen = hard[:2]
        for scene in chosen:
            scene['reason'] = 'ayrıntı/hareket'
        smooth = min((s for s in scenes if s not in chosen), key=lambda s: s['spatial_detail'], default=None)
        if smooth:
            smooth['reason'] = 'düz alan / bantlanma riski'
            chosen.append(smooth)
        return sorted(chosen, key=lambda s: s['offset'])

    # ---------------------------------------------------------------- per encoder
    def capability(self, source: Path, metadata: dict, encoder: str, work: Path, suffix: str):
        """A few full-resolution frames in the final container: catches unsupported
        sizes/profiles/colour signalling in seconds instead of after a long encode."""
        test = work / f'capability-{encoder}{suffix}'
        try:
            run(self.command(source, test, metadata, encoder, QSCALE[encoder][2], frames=8), self.cancel, timeout=180)
            output = probe(test, self.cancel)
            video_stream_checks(metadata['video'], output['video'])
        finally:
            test.unlink(missing_ok=True)

    def search(self, source: Path, metadata: dict, encoder: str, scenes: list, work: Path):
        best, worst, guess, step = QSCALE[encoder]
        guess += {'high': 0, 'balanced': 3, 'compact': 5}[self.options.quality]
        results = {}
        subsample = 2 if sum(scene['length'] for scene in scenes) * self.fps(metadata['video']) > 120 else 1

        def evaluate(quality):
            if quality in results:
                return results[quality]
            self.notify(f'{encoder} · CQ {quality} örnek sahnelerde deneniyor')
            total_bytes, seconds, measured, problems = 0, 0.0, [], []
            for number, scene in enumerate(scenes):
                sample = work / f'sample-{encoder}-{quality}-{number}.mkv'
                segment = (scene['offset'], scene['length'])
                try:
                    run(self.command(source, sample, metadata, encoder, quality, segment), self.cancel,
                        timeout=self.options.sample_timeout)
                    total_bytes += sample.stat().st_size
                    seconds += scene['length']
                    metrics = self.metric(source, sample, metadata, work, segment, subsample)
                finally:
                    sample.unlink(missing_ok=True)
                measured.append(metrics)
                problems += self.quality_problems(metrics, margin=True)
                if problems:
                    break
            record = {'quality': quality, 'passed': not problems, 'problems': problems,
                      'bytes_per_second': total_bytes / max(seconds, 1e-6),
                      'sample_metrics': [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()
                                          if k in ('vmaf', 'vmaf_low', 'cambi_added_mean', 'cambi_added_high', 'psnr_cb', 'psnr_cr')}
                                         for m in measured]}
            results[quality] = record
            return record

        passing, failing = None, None
        quality = guess
        for _ in range(7):
            record = evaluate(quality)
            if record['passed']:
                passing = quality if passing is None else max(passing, quality)
            else:
                failing = quality if failing is None else min(failing, quality)
            if passing is not None and failing is not None:
                if failing - passing <= 1:
                    break
                quality = (passing + failing) // 2
            elif passing is not None:
                if passing >= worst:
                    break
                quality = min(worst, passing + step)
            else:
                if failing <= best:
                    break
                quality = max(best, failing - step)
        tested = sorted(results.values(), key=lambda r: r['quality'])
        if passing is None:
            raise MediaError(f'{encoder}: en yüksek denenen kalitede bile örnekler kalite eşiğini geçmedi')
        return passing, results[passing]['bytes_per_second'], tested

    def verify(self, source: Path, candidate: Path, metadata: dict, work: Path, checks: dict, details: dict):
        self.notify('Akışlar, metadata ve kare zamanları doğrulanıyor')
        output = probe(candidate, self.cancel)
        checks.update(metadata_checks(metadata, output))
        if not (work / 'source.frames').is_file():
            frame_file(source, metadata, work / 'source.frames', self.cancel)
        frame_file(candidate, output, work / 'output.frames', self.cancel)
        timeline = compare_timeline(work / 'source.frames', work / 'output.frames', metadata['video'], output['video'])
        details['timeline'] = timeline
        details['output_pixel_format'] = output['video']['pix_fmt']
        checks['frame_count_and_timing'] = True
        for left, right in zip(metadata['streams'], output['streams']):
            if left['codec_type'] != 'audio':
                continue
            if 'start_time' not in left or 'start_time' not in right:
                raise MediaError('Ses başlangıç zamanlaması doğrulanamıyor')
            tolerance = max(float(Fraction(left['time_base'])), float(Fraction(right['time_base'])))
            delta = float(right['start_time']) - float(left['start_time'])
            if abs(delta - timeline['common_shift_seconds']) > tolerance + 1e-6:
                raise MediaError('Ses/video eşzamanlaması değişti')
        details['audio'] = validate_audio(source, candidate, metadata, work, self.cancel, timeline['common_shift_seconds'])
        checks['audio_samples'] = True
        details['copied_streams'] = validate_copied_streams(source, candidate, metadata, self.cancel)
        checks['copied_streams'] = True
        metrics = self.metric(source, candidate, metadata, work, label='Tam video kalite ölçümü (VMAF + bantlanma)')
        details['quality'] = metrics
        if metrics['frames_measured'] != timeline['frames']:
            raise MediaError(f"Kalite analizi bütün kareleri kapsamıyor ({metrics['frames_measured']} / {timeline['frames']})")
        problems = self.quality_problems(metrics)
        if problems:
            raise QualityError('Tam video kalite eşiğini karşılamadı: ' + '; '.join(problems))
        checks['perceptual_quality'] = True
        checks['no_added_banding'] = True

    # ---------------------------------------------------------------- main
    def optimize(self, source: Path, metadata: dict, work: Path):
        video = metadata['video']
        suffix = source.suffix.lower() if source.suffix.lower() in {'.mp4', '.mov', '.m4v', '.mkv', '.webm'} else '.mkv'
        details = {'source': metadata, 'thresholds': self.options.thresholds, 'attempts': [],
                   'rejected_encoders': self.failures}
        source_bytes = source.stat().st_size
        other_bytes = sum(int(s.get('bit_rate') or 0) for s in metadata['streams']
                          if s['index'] != video['index']) / 8 * metadata['duration']
        video_bytes = max(1.0, source_bytes - other_bytes)
        plan = self.plan(metadata, suffix)
        if not plan:
            raise MediaError('Bu kapsayıcı ve codec tercihi için kullanılabilir video kodlayıcı yok '
                             '(MOV içine AV1 yazılamaz; HEVC veya Otomatik seçin).')
        if pixel_properties(video['pix_fmt'])[2] or pixel_properties(video['pix_fmt'])[0] is None:
            return None, {}, {**details, 'reason': f"{video['pix_fmt']}: alfa kanallı/özel piksel biçimli video, "
                              'görüntüyü birebir koruyan kodlayıcı olmadığı için orijinal korundu.'}
        self.notify('Sahne ayrıntısı, hareket ve düz alanlar analiz ediliyor')
        scenes = self.segments(source, metadata, work)
        details['scene_analysis'] = scenes
        frames_total = int(round(metadata['duration'] * self.fps(video)))
        kept_reasons = []
        # Once an encoder cannot beat the source size at the required quality,
        # equally or less efficient codecs cannot either: skip their long searches.
        efficiency = {'av1': 3, 'hevc': 2, 'h264': 1}
        too_big_at = 0
        for encoder in plan:
            entry = {'encoder': encoder}
            details['attempts'].append(entry)
            if self.cancel.is_set():
                raise Cancelled('İptal edildi')
            if efficiency[ENCODERS[encoder]] <= too_big_at:
                entry['skipped'] = 'daha verimli bir codec bile kaynaktan küçük çıktı üretemedi'
                continue
            try:
                if 'nvenc' not in encoder:
                    self.notify('Yazılım kodlama için RAM bütçesi ayrılıyor')
                    self.resize_budget(max(1536 * 1024**2, video['width'] * video['height'] * 6 * 72 + 512 * 1024**2), 0)
                self.notify(f'{encoder}: gerçek çözünürlükte yetenek denemesi')
                self.capability(source, metadata, encoder, work, suffix)
                quality, rate, tested = self.search(source, metadata, encoder, scenes, work)
                entry.update(search=tested, chosen_quality=quality)
                estimate = rate * metadata['duration']
                entry['estimated_video_bytes'] = round(estimate)
                if estimate > video_bytes * 1.15:
                    reason = (f'{encoder}: görsel kayıpsız kalite için tahmini boyut ({estimate / 1e6:.1f} MB) '
                              f'kaynağın video akışından ({video_bytes / 1e6:.1f} MB) büyük')
                    entry['skipped'] = reason
                    kept_reasons.append(reason)
                    too_big_at = max(too_big_at, efficiency[ENCODERS[encoder]])
                    continue
                result = self.final(source, metadata, work, encoder, quality, suffix, frames_total, entry)
                if result is not None:
                    candidate, checks = result
                    details.update(selected={'encoder': encoder, 'quality': entry['final_quality'],
                                             'output_pixel_format': entry.get('output_pixel_format')},
                                   **{k: v for k, v in entry.items() if k in ('timeline', 'quality', 'audio', 'copied_streams', 'command')})
                    return candidate, checks, details
                kept_reasons.append(entry.get('reason', f'{encoder}: kaynak dosyadan küçük değil'))
                too_big_at = max(too_big_at, efficiency[ENCODERS[encoder]])
            except Cancelled:
                raise
            except MediaError as error:
                entry['error'] = str(error)
                self.failures.append({'encoder': encoder, 'error': str(error)[-900:]})
        if kept_reasons:
            return None, {}, {**details, 'reason': 'Seçilen kalite korunarak küçültülemedi; orijinal korundu. '
                              + ' · '.join(dict.fromkeys(kept_reasons))}
        raise MediaError('Çıktı doğrulanamadı; orijinal korundu. ' + '; '.join(
            dict.fromkeys(f"{entry['encoder']}: {entry['error'][-600:]}" for entry in details['attempts'] if 'error' in entry)))

    def final(self, source, metadata, work, encoder, quality, suffix, frames_total, entry):
        best = QSCALE[encoder][0]
        step = 3 if ENCODERS[encoder] == 'av1' else 2
        errors = []
        entry['final_attempts'] = errors
        for attempt in range(3):
            candidate = work / f'candidate-{encoder}-{quality}{suffix}'
            checks, details = {}, {}
            try:
                label = f'Kodlanıyor · {encoder} · CQ {quality}'
                self.notify(label)
                progress = Progress(work / 'encode.progress', frames_total, self.notify, label)
                args = self.command(source, candidate, metadata, encoder, quality, progress=progress)
                details['command'] = args
                run(args, self.cancel, tick=progress)
                if candidate.suffix.lower() in {'.mov', '.mp4', '.m4v'}:
                    from .mov_metadata import preserve_native_dates
                    preserve_native_dates(source, candidate)
                if candidate.stat().st_size >= source.stat().st_size:
                    errors.append({'quality': quality, 'bytes': candidate.stat().st_size, 'result': 'kaynaktan küçük değil'})
                    entry['reason'] = f'{encoder}: CQ {quality} çıktısı kaynaktan küçük değil'
                    candidate.unlink(missing_ok=True)
                    return None
                self.verify(source, candidate, metadata, work, checks, details)
                entry.update(details, final_quality=quality, output_pixel_format=details.get('output_pixel_format'))
                return candidate, checks
            except QualityError as error:
                errors.append({'quality': quality, 'error': str(error), 'metrics': details.get('quality')})
                candidate.unlink(missing_ok=True)
                if quality <= best:
                    raise MediaError(f'{encoder}: {error}')
                quality = max(best, quality - step)
            except Exception:
                candidate.unlink(missing_ok=True)
                raise
        raise MediaError(f'{encoder}: tam video kalite eşiği üç denemede sağlanamadı')


class QualityError(MediaError):
    pass
