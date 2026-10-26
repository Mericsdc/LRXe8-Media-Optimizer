from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, asdict, field
from typing import Callable

import psutil

PHOTO_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif', '.avif', '.tif', '.tiff', '.bmp', '.gif'}
VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v', '.mts', '.m2ts', '.ts', '.mpg', '.mpeg', '.mxf'}
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


class MediaError(Exception):
    pass


class Cancelled(MediaError):
    pass


# Video quality gates. VMAF is normalised against the reference's own ceiling
# (the score the model gives the untouched source), 'vmaf_low' is the 2nd
# percentile frame. CAMBI: banding the encode *adds* to the source; it only
# counts once the output's own banding reaches 'cambi_floor' (below ~1 CAMBI
# banding is imperceptible). Chroma PSNR guards colour planes VMAF ignores.
QUALITY = {
    'high': {'vmaf_mean': 98.0, 'vmaf_low': 96.0, 'cambi_mean': 0.5, 'cambi_high': 1.0, 'cambi_floor': 1.0,
             'chroma_psnr': 40.0},
    'balanced': {'vmaf_mean': 96.5, 'vmaf_low': 94.0, 'cambi_mean': 1.0, 'cambi_high': 2.0, 'cambi_floor': 1.5,
                 'chroma_psnr': 38.0},
    'compact': {'vmaf_mean': 95.0, 'vmaf_low': 92.0, 'cambi_mean': 1.5, 'cambi_high': 3.0, 'cambi_floor': 2.0,
                'chroma_psnr': 36.0},
}


@dataclass(frozen=True)
class Options:
    quality: str = 'high'
    compatibility: str = 'auto'
    software: bool = True
    max_parallel: int = 2
    threads: int = 0
    sample_seconds: float = 2.0
    sample_timeout: int = 600
    photo_mode: str = 'lossless'
    photo_target_kb: int = 256
    photo_format: str = 'auto'
    strip_metadata: bool = False
    # 'optimize' makes files smaller without visible loss; 'upscale' enlarges
    # them (Real-ESRGAN or classic Lanczos) and is always an explicit choice.
    mode: str = 'optimize'
    upscale_target: str = '4k'
    upscale_content: str = 'photo'
    upscale_method: str = 'ai'

    def __post_init__(self):
        if self.quality not in QUALITY:
            raise ValueError('Geçersiz kalite modu')
        if self.compatibility not in {'auto', 'h264', 'hevc', 'av1'}:
            raise ValueError('Geçersiz codec tercihi')
        if not 1 <= self.max_parallel <= 4 or not 0 <= self.threads <= 64:
            raise ValueError('Geçersiz kaynak sınırı')
        if not 0.2 <= self.sample_seconds <= 5 or self.sample_timeout < 5:
            raise ValueError('Geçersiz örnekleme sınırı')
        if self.photo_mode not in {'lossless', 'small'} or not 32 <= self.photo_target_kb <= 65536:
            raise ValueError('Geçersiz fotoğraf ayarı')
        if self.photo_format not in {'auto', 'webp', 'avif', 'jpeg'}:
            raise ValueError('Geçersiz fotoğraf çıktı biçimi')
        if (self.mode not in {'optimize', 'upscale'} or self.upscale_target not in {'2x', '4x', '4k'}
                or self.upscale_content not in {'photo', 'art'} or self.upscale_method not in {'ai', 'classic'}):
            raise ValueError('Geçersiz büyütme ayarı')

    @property
    def thresholds(self) -> dict:
        return dict(QUALITY[self.quality])

    @property
    def worker_threads(self) -> int:
        """Threads per external tool; parallel jobs share the CPU instead of oversubscribing it."""
        if self.threads:
            return self.threads
        return max(4, min(32, (os.cpu_count() or 8) // self.max_parallel))


@dataclass
class Result:
    source: str
    status: str = 'failed'
    message: str = ''
    output: str | None = None
    source_bytes: int = 0
    output_bytes: int = 0
    elapsed_seconds: float = 0
    report: str | None = None
    checks: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def root_dir() -> Path:
    if getattr(sys, 'frozen', False):
        exe = Path(sys.executable).resolve().parent
        return exe.parent if exe.name == 'app' else exe
    return Path(__file__).resolve().parent.parent


def resource_dirs() -> list[Path]:
    """Where tools/ and assets/ may live: next to the Windows EXE (or its app\\
    parent), inside a macOS .app bundle (PyInstaller's _MEIPASS/Resources), or
    the source checkout."""
    places = [root_dir()]
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        places += [Path(bundle), Path(bundle).parent / 'Resources']
    return list(dict.fromkeys(place for place in places if place.exists()))


def asset(name: str) -> Path:
    for place in resource_dirs():
        if (place / 'assets' / name).is_file():
            return place / 'assets' / name
    return root_dir() / 'assets' / name


def find_tool(name: str, required=True) -> str | None:
    env = os.environ.get('LRXE8_' + name.upper())
    if env and Path(env).is_file():
        return str(Path(env).resolve())
    suffix = '.exe' if os.name == 'nt' else ''
    for place in resource_dirs():
        tools = place / 'tools'
        if tools.exists():
            found = sorted(path for path in tools.rglob(name + suffix) if path.is_file())
            if found:
                return str(found[0])
    found = shutil.which(name)
    if found:
        return found
    if required:
        raise MediaError(f'{name} bulunamadı. Araçlar klasörünü veya LRXE8_{name.upper()} ayarını kontrol edin.')
    return None


def sha256(path: Path, cancel: threading.Event | None = None) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            if cancel and cancel.is_set():
                raise Cancelled('İptal edildi')
            digest.update(block)
    return digest.hexdigest()


def run(args: list[str], cancel: threading.Event, *, timeout: float | None = None,
        stdout_path: Path | None = None, tick: Callable[[], None] | None = None,
        cwd: Path | None = None) -> str:
    """No shell, bounded memory, cancellable child, bounded diagnostic tail."""
    if cancel.is_set():
        raise Cancelled('İptal edildi')
    with tempfile.TemporaryFile() as err, (stdout_path.open('wb') if stdout_path else tempfile.TemporaryFile()) as out:
        process = subprocess.Popen([str(a) for a in args], stdin=subprocess.DEVNULL,
                                   stdout=out, stderr=err, creationflags=HIDDEN,
                                   cwd=str(cwd) if cwd is not None else None)
        started = time.monotonic()
        last_memory_check = started
        try:
            while process.poll() is None:
                if cancel.wait(0.15):
                    raise Cancelled('İptal edildi; orijinal korundu')
                if timeout and time.monotonic() - started > timeout:
                    raise MediaError(f'İşlem zaman sınırını aştı ({timeout:g} sn)')
                if time.monotonic() - last_memory_check > 2:
                    last_memory_check = time.monotonic()
                    if psutil.virtual_memory().available < 1024**3:
                        raise MediaError('Sistem RAM sınırına yaklaştı; işlem güvenle durduruldu')
                if tick:
                    tick()
            err.seek(max(0, err.tell() - 16000))
            diagnostic = err.read().decode('utf-8', 'replace')
            if process.returncode:
                raise MediaError(f'{Path(args[0]).name} hata kodu {process.returncode}: {diagnostic[-6000:]}')
            if stdout_path:
                return diagnostic
            size = out.tell()
            if size > 8 * 1024 * 1024:
                raise MediaError('Araç çıktısı beklenen sınırı aştı')
            out.seek(0)
            return out.read().decode('utf-8', 'replace') or diagnostic
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def gpu_memory() -> tuple[int, int]:
    executable = shutil.which('nvidia-smi')
    if not executable:
        return 0, 0
    try:
        text = subprocess.check_output([executable, '--query-gpu=memory.total,memory.free',
            '--format=csv,noheader,nounits', '--id=0'], creationflags=HIDDEN, timeout=5).decode()
        total, free = map(int, text.strip().split(','))
        return total * 1024**2, free * 1024**2
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0, 0


class Resources:
    def __init__(self, maximum=2):
        self.maximum = maximum
        self.lock = threading.Condition()
        self.active = self.ram_reserved = self.gpu_reserved = self.resizing = 0

    @contextlib.contextmanager
    def lease(self, ram: int, gpu: int, cancel: threading.Event, notify: Callable):
        started = time.monotonic()
        informed = False
        with self.lock:
            while True:
                if cancel.is_set():
                    raise Cancelled('İptal edildi')
                memory = psutil.virtual_memory()
                reserve = max(2 * 1024**3, int(memory.total * .15))
                total_gpu, free_gpu = gpu_memory() if gpu else (0, 0)
                fits_ram = ram <= min(memory.available - reserve, memory.total - reserve - self.ram_reserved)
                fits_gpu = not gpu or (total_gpu > 0 and gpu <= min(free_gpu - 768 * 1024**2,
                                                      total_gpu - 768 * 1024**2 - self.gpu_reserved))
                if self.active < self.maximum and fits_ram and fits_gpu:
                    self.active += 1
                    self.ram_reserved += ram
                    self.gpu_reserved += gpu
                    break
                if not informed:
                    notify('Sırada · diğer dosyanın bitmesi / bellek bekleniyor')
                    informed = True
                # A queued job waits for running jobs however long they take (big
                # 4K/8K files run for many minutes). Only an idle machine that still
                # cannot provide the budget is reported as a real resource failure.
                if self.active:
                    started = time.monotonic()
                elif time.monotonic() - started > 90:
                    raise MediaError('Yeterli RAM/VRAM sağlanamadı. Diğer uygulamaları kapatıp yeniden deneyin.')
                self.lock.wait(.5)
        def resize(new_ram, new_gpu=0):
            nonlocal ram, gpu
            began = time.monotonic()
            with self.lock:
                self.resizing += 1
                try:
                    while True:
                        if cancel.is_set():
                            raise Cancelled('İptal edildi')
                        memory = psutil.virtual_memory()
                        reserve = max(2 * 1024**3, int(memory.total * .15))
                        if new_ram <= min(memory.available - reserve,
                                          memory.total - reserve - self.ram_reserved + ram):
                            self.ram_reserved += new_ram - ram
                            self.gpu_reserved += new_gpu - gpu
                            ram, gpu = new_ram, new_gpu
                            self.lock.notify_all()
                            return
                        # Wait for other running jobs to release memory, but never
                        # deadlock when every active job is itself waiting to grow.
                        if self.resizing < self.active:
                            began = time.monotonic()
                        elif time.monotonic() - began > 90:
                            raise MediaError('Yazılım kodlama için yeterli RAM yok; diğer işleri kapatın veya donanım destekli codec seçin.')
                        self.lock.wait(.5)
                finally:
                    self.resizing -= 1
        try:
            yield resize
        finally:
            with self.lock:
                self.active -= 1
                self.ram_reserved -= ram
                self.gpu_reserved -= gpu
                self.lock.notify_all()


def publish(candidate: Path, directory: Path, source: Path, cancel: threading.Event, tag: str = 'optimized') -> Path:
    if cancel.is_set():
        raise Cancelled('İptal edildi')
    # Staging directory lives on the destination volume. Hard-link creation is atomic
    # and fails on existing names, including races; the source is never a destination.
    for index in range(10000):
        ending = '' if index == 0 else f'-{index}'
        target = directory / f'{source.stem}.{tag}{ending}{candidate.suffix}'
        if target.resolve() == source.resolve():
            continue
        try:
            os.link(candidate, target)
            return target
        except FileExistsError:
            # Repeating the same job should reuse an identical verified file,
            # while distinct existing results remain protected from overwrites.
            if target.is_file() and target.stat().st_size == candidate.stat().st_size:
                if sha256(target, cancel) == sha256(candidate, cancel):
                    return target
            continue
        except OSError as error:
            raise MediaError('Çıktı atomik olarak kaydedilemedi. NTFS üzerinde bir hedef klasör seçin. ' + str(error))
    raise MediaError('Benzersiz çıktı adı oluşturulamadı')
