from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
import shutil
import tempfile
import threading
import time

from PIL import Image
import psutil

from .core import PHOTO_EXT, VIDEO_EXT, Options, Result, Resources, MediaError, Cancelled, sha256, publish, gpu_memory
from .photos import photo_optimize
from .probe import probe
from .video import Video


class Engine:
    def __init__(self, options: Options | None = None, cancel: threading.Event | None = None):
        self.options = options or Options()
        self.cancel = cancel or threading.Event()
        self.resources = Resources(self.options.max_parallel)

    def optimize(self, source: Path, destination: Path, progress=lambda message: None) -> Result:
        source, destination = Path(source).resolve(), Path(destination).resolve()
        result = Result(str(source))
        started = time.monotonic()
        try:
            if not source.is_file():
                raise MediaError('Kaynak dosya bulunamadı')
            if self.cancel.is_set():
                raise Cancelled('İptal edildi')
            destination.mkdir(parents=True, exist_ok=True)
            result.source_bytes = source.stat().st_size
            if not result.source_bytes:
                raise MediaError('Kaynak dosya boş')
            progress('Kaynak bütünlüğü kaydediliyor')
            original_hash = sha256(source, self.cancel)
            result.details['source_sha256'] = original_hash
            result.details['options'] = asdict(self.options)
            if source.suffix.lower() in PHOTO_EXT:
                try:
                    with Image.open(source) as image:
                        pixels = image.width * image.height
                except (OSError, ValueError) as error:
                    raise MediaError(f'Fotoğraf açılamadı veya bozuk: {error}')
                ram = max(512 * 1024**2, pixels * 48 + result.source_bytes * 6)
                gpu = 0
                metadata = None
            elif source.suffix.lower() in VIDEO_EXT:
                progress('Çözünürlük, akışlar ve renk özellikleri okunuyor')
                metadata = probe(source, self.cancel)
                result.details['source'] = metadata
                video = metadata['video']
                pixels = video['width'] * video['height']
                if self.options.mode == 'upscale':
                    # Budget for the enlarged frames (up to 4K/8K), not the source.
                    pixels = max(pixels, 3840 * 2160) if self.options.upscale_target != '2x' else pixels * 4
                # Reserve for encoder lookahead, decoder surfaces AND the three-input
                # VMAF/CAMBI validation. Long videos never load all frames into RAM.
                ram = max(2048 * 1024**2, pixels * 6 * 40 + 1024**3)
                gpu = max(512 * 1024**2, pixels * 6 * 24)
                total, free = gpu_memory()
                if gpu > max(0, free - 768 * 1024**2):
                    gpu = 0
                    ram = max(ram, pixels * 6 * 72 + 512 * 1024**2)
            else:
                raise MediaError('Desteklenmeyen dosya türü')
            disk = shutil.disk_usage(destination)
            required_disk = max(1024**3, result.source_bytes * 2)
            if disk.free < required_disk:
                raise MediaError('Geçici dosyalar ve doğrulama için yeterli boş disk alanı yok')
            with self.resources.lease(ram, gpu, self.cancel, progress) as resize_budget:
                with tempfile.TemporaryDirectory(prefix='.lrxe8-', dir=destination) as temporary:
                    work = Path(temporary)
                    upscale = self.options.mode == 'upscale'
                    if metadata is None and upscale:
                        from .upscale import upscale_photo
                        candidate, checks, details = upscale_photo(source, work, self.cancel, progress, self.options)
                    elif metadata is None:
                        candidate, checks, details = photo_optimize(source, work, self.cancel, progress, self.options)
                    else:
                        processor = Video(self.options, self.cancel, progress)
                        processor.hardware_allowed = gpu > 0
                        processor.resize_budget = resize_budget
                        if upscale:
                            from .upscale import upscale_video
                            candidate, checks, details = upscale_video(source, metadata, work, self.cancel, progress,
                                                                       self.options, processor)
                        else:
                            candidate, checks, details = processor.optimize(source, metadata, work)
                    result.checks.update(checks)
                    result.details.update(details)
                    if sha256(source, self.cancel) != original_hash:
                        raise MediaError('Kaynak işlem sırasında değişti; çıktı yayımlanmadı')
                    result.checks['original_unchanged'] = True
                    if candidate is None:
                        result.status = 'kept'
                        result.message = details.get('reason', 'Orijinal korundu')
                    elif upscale:
                        # Enlarged files are bigger by nature; publish them under their own name.
                        result.details['output_sha256'] = sha256(candidate, self.cancel)
                        tag = 'upscaled-4k' if self.options.upscale_target == '4k' or metadata is not None and \
                            self.options.upscale_target == '4x' else f'upscaled-{self.options.upscale_target}'
                        final = publish(candidate, destination, source, self.cancel, tag)
                        result.output = str(final)
                        result.output_bytes = final.stat().st_size
                        result.status = 'optimized'
                        before, after = details.get('source_size') or [0, 0], details.get('target_size') or [0, 0]
                        result.message = (f'Büyütüldü · {before[0]}×{before[1]} → {after[0]}×{after[1]} · '
                                          f"{details.get('model', '')}")
                    elif candidate.stat().st_size >= result.source_bytes:
                        result.status = 'kept'
                        result.message = 'Doğrulanan çıktı daha küçük değil; orijinal korundu.'
                        result.details['candidate_bytes'] = candidate.stat().st_size
                        result.checks['smaller'] = False
                    else:
                        result.checks['smaller'] = True
                        result.details['output_sha256'] = sha256(candidate, self.cancel)
                        final = publish(candidate, destination, source, self.cancel)
                        result.output = str(final)
                        result.output_bytes = final.stat().st_size
                        result.status = 'optimized'
                        result.message = f'Doğrulandı · %{100 * (1 - result.output_bytes / result.source_bytes):.1f} daha küçük'
                        selected = details.get('selected') or {}
                        if metadata is not None and selected.get('encoder'):
                            quality = details.get('quality') or {}
                            result.message += (f" · {selected['encoder']} {selected.get('output_pixel_format', '')}"
                                               f" · VMAF {quality.get('vmaf', 0):.1f}")
                        if details.get('photo_mode') == 'small':
                            result.message += f" · {details.get('output_format', 'WebP')} · SSIMULACRA2 {details.get('selected', {}).get('ssimulacra2', 0):.1f}"
                            if not details.get('target_met'):
                                result.message += f" · {self.options.photo_target_kb} KB hedefi görsel kalite için aşıldı"
        except Cancelled as error:
            result.status, result.message = 'cancelled', str(error)
        except Exception as error:
            result.status, result.message = 'failed', str(error)
            result.details['error_type'] = type(error).__name__
        result.elapsed_seconds = round(time.monotonic() - started, 3)
        # Keep verification details in memory. Only an optimized media file is
        # published; normal jobs never create reports/logs beside user outputs.
        progress(result.message)
        return result

    def batch(self, sources, destination, progress=lambda source, message: None, done=lambda result: None):
        results = []
        paths = list(dict.fromkeys(Path(path).resolve() for path in sources))
        with ThreadPoolExecutor(max_workers=self.options.max_parallel, thread_name_prefix='lrxe8') as pool:
            futures = [pool.submit(self.optimize, path, destination, lambda message, p=path: progress(p, message)) for path in paths]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                done(result)
        return results
