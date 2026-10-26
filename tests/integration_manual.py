"""Real FFmpeg integration checks. Run explicitly; never touches user media.

python tests/integration_manual.py --work D:/LRXe8-tests --large --matrix
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lrxe8.core import Options, find_tool, run
from lrxe8.engine import Engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--large', action='store_true', help='Also encode real 5K/8K sources')
    parser.add_argument('--matrix', action='store_true', help='Probe 30 NVENC/dimension combinations')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    ffmpeg, cancel = find_tool('ffmpeg'), threading.Event()
    records = []
    cases = [('1080p-auto', 1920, 1080, 'auto')]
    if args.large:
        cases += [('8k-av1', 7680, 4320, 'av1'), ('5k-h264-fallback', 5120, 2880, 'h264')]
    for name, width, height, codec in cases:
        source = args.work / (name + '.mp4')
        if source.exists():
            raise RuntimeError(f'Use an empty work directory: {source} already exists')
        run([ffmpeg, '-v', 'error', '-n', '-f', 'lavfi', '-i',
             f'testsrc2=size={width}x{height}:rate=30:duration=0.4',
             '-c:v', 'libx264', '-preset', 'ultrafast', '-qp', '0', '-threads', '4',
             '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', str(source)], cancel)
        result = Engine(Options(compatibility=codec, max_parallel=1, sample_seconds=.2)).optimize(
            source, args.work / 'optimized', lambda message: print(name, message, flush=True))
        records.append(asdict(result))
    matrix = []
    if args.matrix:
        for width, height in [(1920,1080), (2048,1080), (2560,1440), (3840,2160), (4096,2160),
                              (5120,2880), (6144,3160), (7680,4320), (1080,1920), (2222,1112)]:
            for encoder in ('av1_nvenc', 'hevc_nvenc', 'h264_nvenc'):
                entry = {'resolution': [width, height], 'encoder': encoder}
                try:
                    run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i',
                         f'color=size={width}x{height}:rate=60', '-frames:v', '3',
                         '-c:v', encoder, '-pix_fmt', 'yuv420p', '-preset', 'p4', '-f', 'null', '-'],
                        cancel, timeout=45)
                    entry['result'] = 'pass'
                except Exception as error:
                    entry.update(result='unsupported', reason=str(error))
                matrix.append(entry)
                print(width, height, encoder, entry['result'], flush=True)
    (args.work / 'integration-results.json').write_text(
        json.dumps({'results': records, 'hardware': matrix}, ensure_ascii=False, indent=2), encoding='utf-8')
    return int(any(item['status'] != 'optimized' for item in records))


if __name__ == '__main__':
    raise SystemExit(main())
