from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import threading

from .core import Options, find_tool, gpu_memory, run
from .engine import Engine


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='LRXe8 Media Optimizer')
    sub = parser.add_subparsers(dest='command')
    optimize = sub.add_parser('optimize', help='Dosyaları doğrulayarak optimize et')
    optimize.add_argument('files', nargs='+', type=Path)
    optimize.add_argument('--output', required=True, type=Path)
    optimize.add_argument('--quality', choices=['high', 'balanced', 'compact'], default='high')
    optimize.add_argument('--codec', choices=['auto', 'h264', 'hevc', 'av1'], default='auto')
    optimize.add_argument('--no-software', action='store_true')
    optimize.add_argument('--parallel', type=int, default=2)
    optimize.add_argument('--photo-mode', choices=['lossless', 'small'], default='lossless')
    optimize.add_argument('--photo-target-kb', type=int, default=256)
    optimize.add_argument('--photo-format', choices=['auto', 'webp', 'avif', 'jpeg'], default='auto')
    optimize.add_argument('--report', type=Path, help='Sonuçları ayrıca bu JSON dosyasına yaz (pencereli EXE için)')
    optimize.add_argument('--strip-metadata', action='store_true',
                          help='Fotoğraflarda görünmeyen metadata\'yı sil (ICC renk profili ve yön korunur)')
    optimize.add_argument('--mode', choices=['optimize', 'upscale'], default='optimize',
                          help='optimize: kaliteyi koruyarak küçült · upscale: büyüt / kaliteyi yükselt')
    optimize.add_argument('--upscale-target', choices=['2x', '4x', '4k'], default='4k')
    optimize.add_argument('--upscale-content', choices=['photo', 'art'], default='photo')
    optimize.add_argument('--upscale-method', choices=['ai', 'classic'], default='ai')
    worker = sub.add_parser('upscale-worker', help=argparse.SUPPRESS)
    worker.add_argument('spec')
    sub.add_parser('doctor', help='Araçlar ve donanım')
    check = sub.add_parser('self-test', help='Paket ve arayüz için yerel kısa test')
    check.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'upscale-worker':
        from .upscale import worker_main
        return worker_main(args.spec)
    if args.command == 'self-test':
        from .selftest import self_test
        return self_test(args.output)
    if args.command == 'doctor':
        cancel = threading.Event()
        print(json.dumps({name: find_tool(name, False) for name in ('ffmpeg', 'ffprobe', 'jpegtran', 'oxipng', 'ssimulacra2')}
                         | {'gpu_memory': gpu_memory()}, indent=2))
        if find_tool('ffmpeg', False):
            print(run([find_tool('ffmpeg'), '-hide_banner', '-encoders'], cancel))
        return 0
    if args.command == 'optimize':
        engine = Engine(Options(quality=args.quality, compatibility=args.codec,
                                software=not args.no_software, max_parallel=args.parallel,
                                photo_mode=args.photo_mode, photo_target_kb=args.photo_target_kb,
                                photo_format=args.photo_format, strip_metadata=args.strip_metadata,
                                mode=args.mode, upscale_target=args.upscale_target,
                                upscale_content=args.upscale_content, upscale_method=args.upscale_method))
        import signal
        signal.signal(signal.SIGINT, lambda *_: engine.cancel.set())
        results = engine.batch(args.files, args.output,
            progress=lambda path, message: print(f'{path.name}: {message}', file=sys.stderr, flush=True) if sys.stderr else None)
        text = json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2, default=str)
        print(text)
        if args.report:
            args.report.write_text(text, encoding='utf-8')
        return 1 if any(result.status in {'failed', 'cancelled'} for result in results) else 0
    from .gui import launch
    return launch()


if __name__ == '__main__':
    raise SystemExit(main())
