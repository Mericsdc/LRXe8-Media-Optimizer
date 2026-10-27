"""Offline packaging check; uses generated fixtures and never opens a window."""
from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

from PIL import Image
from PySide6.QtWidgets import QApplication

from .core import Options, find_tool, gpu_memory
from .engine import Engine
from .gui import MainWindow, STYLE


def self_test(destination: Path) -> int:
    destination = destination.resolve() / ('self-test-' + uuid.uuid4().hex[:8])
    destination.mkdir(parents=True)
    data = {'tools': {key: find_tool(key, False) for key in ('ffmpeg', 'ffprobe', 'jpegtran', 'oxipng', 'ssimulacra2')},
            'gpu_memory': gpu_memory(), 'results': []}
    try:
        # The update check needs TLS: the bundled OpenSSL must match Python's _ssl.
        import ssl
        data['openssl'] = ssl.OPENSSL_VERSION
        ssl.create_default_context()
        engine = Engine(Options(max_parallel=1))
        picture = Image.new('RGBA', (96, 64), (17, 80, 100, 128))
        try:
            import mozjpeg_lossless_optimization  # noqa: F401  (bundled MozJPEG must load in the EXE)
            data['mozjpeg'] = True
        except ImportError as error:
            raise RuntimeError(f'MozJPEG modülü yüklenemedi: {error}')
        for name in ('alpha.png', 'photo.jpg', 'photo.webp', 'photo.heic', 'photo.avif'):
            source = destination / name
            if source.suffix == '.png':
                picture.save(source, compress_level=0)
            elif source.suffix == '.jpg':
                picture.convert('RGB').save(source, quality=95, optimize=False)
            elif source.suffix == '.heic':
                picture.save(source, format='HEIF', quality=90)
            else:
                picture.save(source, lossless=True, exact=True)
            result = engine.optimize(source, destination / 'optimized')
            data['results'].append(result.to_dict())
            if result.status not in {'optimized', 'kept'}:
                raise RuntimeError(f'{name}: {result.message}')
        # jpegtran is optional everywhere (MozJPEG covers lossless JPEG); ssimulacra2 ships on Windows.
        required = ('ffmpeg', 'ffprobe', 'oxipng') + (('ssimulacra2',) if os.name == 'nt' else ())
        if not all(data['tools'][name] for name in required):
            raise RuntimeError('Paket araçları eksik: ' + ', '.join(name for name in required if not data['tools'][name]))
        compact_source = destination / 'small-source.png'
        gradient = Image.new('RGB', (320, 200))
        gradient.putdata([(x * 255 // 319, y * 255 // 199, (x + y) % 256) for y in range(200) for x in range(320)])
        gradient.save(compact_source, compress_level=0)
        compact = Engine(Options(photo_mode='small', photo_format='avif', max_parallel=1)).optimize(
            compact_source, destination / 'small-output')
        data['small_photo'] = compact.to_dict()
        if compact.status != 'optimized' or list((destination / 'small-output').iterdir()) != [Path(compact.output)]:
            raise RuntimeError('Küçük fotoğraf / temiz çıktı klasörü testi başarısız')
        # Enlargement through the separate worker process (Real-ESRGAN on the GPU,
        # classic Lanczos only as a recorded fallback where no Vulkan GPU exists).
        enlarged = Engine(Options(mode='upscale', upscale_target='2x', upscale_content='art', max_parallel=1)).optimize(
            compact_source, destination / 'upscale-output')
        data['upscale'] = {'status': enlarged.status, 'message': enlarged.message,
                           'model': enlarged.details.get('model'), 'note': enlarged.details.get('note')}
        if enlarged.status != 'optimized':
            raise RuntimeError(f'Büyütme: {enlarged.message}')
        if os.name == 'nt' and enlarged.details.get('model') == 'Lanczos':
            # The Windows package ships Real-ESRGAN; a fallback here means packaging broke.
            raise RuntimeError(f"Yapay zekâ büyütme pakette çalışmadı: {enlarged.details.get('note')}")
        # Short real video through the full pipeline: encoder search, 10-bit output,
        # timing/stream checks and VMAF + CAMBI in the frozen package.
        from .core import run
        import threading
        clip = destination / 'video.mp4'
        run([find_tool('ffmpeg'), '-v', 'error', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=1920x1080:rate=30:duration=2',
             '-c:v', 'libx264', '-preset', 'ultrafast', '-qp', '2', '-pix_fmt', 'yuv420p', str(clip)], threading.Event())
        video = Engine(Options(max_parallel=1)).optimize(clip, destination / 'video-output')
        data['video'] = {key: value for key, value in video.to_dict().items() if key != 'details'}
        data['video']['quality'] = video.details.get('quality')
        data['video']['selected'] = video.details.get('selected')
        if video.status != 'optimized':
            raise RuntimeError(f'Video: {video.message}')
        app = QApplication.instance() or QApplication([])
        app.setStyle('Fusion')
        app.setStyleSheet(STYLE)
        window = MainWindow()
        window.add_paths([item['source'] for item in data['results']])
        window.progress_bar.setRange(0, len(data['results']))
        from .core import Result
        for item in data['results']:
            window.on_result(Result(**item))
        window.ensurePolished()
        app.processEvents()
        if not window.grab().save(str(destination / 'preview.png')):
            raise RuntimeError('Arayüz görüntüsü kaydedilemedi')
        window.close()
        data['status'] = 'passed'
    except Exception as error:
        data['status'], data['error'] = 'failed', str(error)
    (destination / 'self-test.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if data['status'] == 'passed' else 1
