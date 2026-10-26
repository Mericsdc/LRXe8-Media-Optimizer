"""Opt-in enlargement ("Büyüt"): Real-ESRGAN (ncnn/Vulkan: NVIDIA/AMD/Intel on
Windows, Apple GPU on macOS) or classic Lanczos.

The neural network runs in a separate worker process: a GPU/driver crash cannot
take the app down, cancelling kills it at once, and ncnn's known crash during
interpreter shutdown never reaches the GUI. Videos are enlarged into a lossless
intermediate and then compressed by the normal verified video pipeline, so the
final 4K file is checked frame by frame against the enlarged frames. The result
is also shrunk back to the original size and compared with the original, to
catch an enhancement that changed the content instead of sharpening it.
"""
from __future__ import annotations

from fractions import Fraction
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading

from PIL import Image

from .core import HIDDEN, MediaError, Cancelled, Options, find_tool, run

# name -> (ncnn files stem, native scale)
MODELS = {'photo': ('realesrgan-x4plus', 4), 'art': ('realesrgan-x4plus-anime', 4),
          'video2': ('realesr-animevideov3-x2', 2), 'video3': ('realesr-animevideov3-x3', 3),
          'video4': ('realesr-animevideov3-x4', 4)}
MAX_PHOTO_PIXELS = 400_000_000
MATRICES = {'bt709': 'bt709', 'bt470bg': 'bt601', 'smpte170m': 'bt601', 'bt2020nc': 'bt2020', 'bt2020c': 'bt2020',
            'smpte240m': 'smpte240m', 'fcc': 'fcc'}


def target_size(width: int, height: int, target: str, even: bool = False):
    """Output size for '2x', '4x' or '4k' (fit inside 3840x2160, either
    orientation). None when the source is already that big."""
    factor = {'2x': 2.0, '4x': 4.0}.get(target)
    if factor is None:
        box = (3840, 2160) if width >= height else (2160, 3840)
        factor = min(box[0] / width, box[1] / height)
    if factor < 1.01:
        return None
    w, h = int(round(width * factor)), int(round(height * factor))
    if even:
        w, h = w - w % 2, h - h % 2
    return w, h


# ---------------------------------------------------------------- neural backend
def backend_dir() -> Path | None:
    """realesrgan_ncnn_py's folder (compiled wrapper + models) without importing
    the package itself, whose __init__ pulls in OpenCV for nothing."""
    bundle = getattr(sys, '_MEIPASS', None)
    places = [Path(bundle) / 'realesrgan_ncnn_py'] if bundle else []
    spec = importlib.util.find_spec('realesrgan_ncnn_py')
    if spec and spec.submodule_search_locations:
        places += [Path(location) for location in spec.submodule_search_locations]
    for place in places:
        if (place / 'models').is_dir() and any(place.glob('realesrgan_ncnn_vulkan_wrapper*')):
            return place
    return None


def available() -> bool:
    return backend_dir() is not None


class Network:
    """Thin wrapper over the compiled Real-ESRGAN module (worker process only)."""

    def __init__(self, model: str, gpu: int = 0):
        folder = backend_dir()
        if folder is None:
            raise MediaError('Real-ESRGAN modülü bulunamadı')
        suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
        binary = next(path for path in folder.glob('realesrgan_ncnn_vulkan_wrapper*') if str(path).endswith(suffixes))
        loader = importlib.machinery.ExtensionFileLoader('realesrgan_ncnn_vulkan_wrapper', str(binary))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        self.module = module
        stem, self.scale = MODELS[model]
        self.engine = module.RealESRGANWrapped(gpu, False)
        self.engine.set_parameters(0, self.scale)
        self.engine.load(str(folder / 'models' / f'{stem}.param'), str(folder / 'models' / f'{stem}.bin'))

    def __call__(self, data: bytes, width: int, height: int, channels: int = 3) -> bytes:
        # The compiled images point into these buffers without copying them:
        # both must stay referenced until process() has finished.
        buffer = bytes(len(data) * self.scale * self.scale)
        source = self.module.RealESRGANImage(data, width, height, channels)
        output = self.module.RealESRGANImage(buffer, width * self.scale, height * self.scale, channels)
        self.engine.process(source, output)
        result = output.get_data()
        del source, output, buffer
        return result


def network(model: str, gpu: int):
    try:
        return Network(model, gpu)
    except Exception:
        if gpu < 0:
            raise
        return Network(model, -1)  # no Vulkan GPU: much slower CPU path


# ---------------------------------------------------------------- worker process
def worker_main(spec_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text(encoding='utf-8'))
    try:
        if spec['kind'] == 'photo':
            worker_photo(spec)
        else:
            worker_video(spec)
        Path(spec['done']).write_text('ok', encoding='utf-8')
    except Exception as error:  # reported to the parent through the spec folder
        Path(spec['done']).write_text('error: ' + str(error), encoding='utf-8')
    finally:
        sys.stdout and sys.stdout.flush()
        sys.stderr and sys.stderr.flush()
    # ncnn's Vulkan teardown crashes while the process unloads its DLLs (even
    # after os._exit). The work is already on disk: end the process outright.
    if os.name == 'nt':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.TerminateProcess(kernel32.GetCurrentProcess(), 0)
    os._exit(0)


def enlarge(image: Image.Image, size, model: str, gpu: int):
    """RGB/RGBA image -> exactly `size`. The network may run twice for >4x; alpha
    is resized with Lanczos (the network is trained on colour only)."""
    alpha = image.getchannel('A') if image.mode == 'RGBA' else None
    rgb = image.convert('RGB')
    net = network(model, gpu)
    passes = 0
    while rgb.width < size[0] and passes < 2:
        rgb = Image.frombytes('RGB', (rgb.width * net.scale, rgb.height * net.scale),
                              net(rgb.tobytes(), rgb.width, rgb.height))
        passes += 1
    if rgb.size != tuple(size):
        rgb = rgb.resize(size, Image.LANCZOS)
    if alpha is not None:
        rgb.putalpha(alpha.resize(size, Image.LANCZOS))
    return rgb


def worker_photo(spec):
    with Image.open(spec['input']) as image:
        image.load()
        result = enlarge(image, (spec['width'], spec['height']), spec['model'], spec.get('gpu', 0))
    result.save(spec['output'], compress_level=1)


def worker_video(spec):
    """decode (rgb24) -> Real-ESRGAN -> lossless x264 intermediate, all streamed."""
    w, h, W, H = spec['src_width'], spec['src_height'], spec['width'], spec['height']
    net = network(spec['model'], spec.get('gpu', 0))
    progress = Path(spec['progress'])
    decoder = subprocess.Popen(spec['decode'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, creationflags=HIDDEN)
    encoder = subprocess.Popen(spec['encode'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=HIDDEN)
    frames_in, frames_out = queue.Queue(4), queue.Queue(4)
    frame_size = w * h * 3

    def read():
        while True:
            data = decoder.stdout.read(frame_size)
            if len(data) < frame_size:
                frames_in.put(None)
                return
            frames_in.put(data)

    def write():
        while (data := frames_out.get()) is not None:
            encoder.stdin.write(data)
        encoder.stdin.close()

    threads = [threading.Thread(target=read, daemon=True), threading.Thread(target=write, daemon=True)]
    for thread in threads:
        thread.start()
    count = 0
    while (data := frames_in.get()) is not None:
        out = net(data, w, h)
        size = (w * net.scale, h * net.scale)
        if size != (W, H):
            out = Image.frombytes('RGB', size, out).resize((W, H), Image.LANCZOS).tobytes()
        frames_out.put(out)
        count += 1
        if count % 5 == 0:
            with progress.open('a', encoding='ascii') as stream:
                stream.write(f'frame={count}\n')
    frames_out.put(None)
    threads[1].join()
    if decoder.wait() != 0 or encoder.wait() != 0:
        raise MediaError('Video çözme/kodlama hattı hata verdi')
    Path(spec['frames_file']).write_text(str(count), encoding='ascii')


def start_worker(spec: dict, work: Path, cancel, label: str, total: int, notify):
    from .video import Progress
    spec_path = work / 'upscale-spec.json'
    spec['done'] = str(work / 'upscale-done.txt')
    Path(spec['done']).unlink(missing_ok=True)
    progress = Progress(work / 'upscale.progress', max(1, total), notify, label)
    spec['progress'] = str(progress.path)
    spec_path.write_text(json.dumps(spec), encoding='utf-8')
    if getattr(sys, 'frozen', False):
        command = [sys.executable, 'upscale-worker', str(spec_path)]
    else:
        from .core import root_dir
        command = [sys.executable, str(root_dir() / 'launch.py'), 'upscale-worker', str(spec_path)]
    # The network prints a progress line per tile; keep that out of memory limits.
    done = Path(spec['done'])
    try:
        run(command, cancel, tick=progress, cwd=work, stdout_path=work / 'upscale-worker.log')
    except Cancelled:
        raise
    except MediaError:
        # A crash while unloading the GPU driver happens after the result was
        # written; the worker's own done-marker is what counts.
        if not done.is_file():
            raise
    status = done.read_text(encoding='utf-8') if done.is_file() else 'error: yapay zekâ işlemi beklenmedik şekilde kapandı'
    if status != 'ok':
        raise MediaError('Büyütme başarısız: ' + status.removeprefix('error: '))


# ---------------------------------------------------------------- photos
def upscale_photo(source: Path, work: Path, cancel, notify, options: Options):
    from .photo_small import transplant_jpeg_markers
    with Image.open(source) as original:
        original.load()
        fmt, size, mode, info = original.format, original.size, original.mode, dict(original.info)
        animated = getattr(original, 'n_frames', 1) > 1
        details = {'mode': 'upscale', 'format': fmt, 'source_size': list(size), 'method': options.upscale_method,
                   'target': options.upscale_target}
        if animated:
            return None, {}, {**details, 'reason': 'Hareketli görsel büyütülmez; orijinal korundu.'}
        if mode not in {'RGB', 'RGBA', 'L', 'LA', 'P'}:
            return None, {}, {**details, 'reason': f'{mode} (16-bit, CMYK veya HDR) fotoğraf renkleri bozulmadan büyütülemez; orijinal korundu.'}
        size_out = target_size(*size, options.upscale_target)
        if size_out is None:
            return None, {}, {**details, 'reason': 'Fotoğraf zaten hedef boyutta veya daha büyük; orijinal korundu.'}
        if size_out[0] * size_out[1] > MAX_PHOTO_PIXELS:
            return None, {}, {**details, 'reason': 'Hedef boyut 400 megapikseli aşıyor; daha küçük bir hedef seçin.'}
        has_alpha = mode in {'RGBA', 'LA'} or (mode == 'P' and 'transparency' in info)
        working = original.convert('RGBA' if has_alpha else 'RGB')
    details['target_size'] = list(size_out)
    enlarged = work / 'enlarged.png'
    if options.upscale_method == 'ai' and available():
        model = 'art' if options.upscale_content == 'art' else 'photo'
        details['model'] = MODELS[model][0]
        notify('Yapay zekâ ile büyütülüyor · ' + ('çizim/logo modeli' if model == 'art' else 'fotoğraf modeli'))
        prepared = work / 'prepared.png'
        working.save(prepared, compress_level=1)
        try:
            start_worker({'kind': 'photo', 'input': str(prepared), 'output': str(enlarged), 'model': model,
                          'width': size_out[0], 'height': size_out[1]}, work, cancel, 'Yapay zekâ ile büyütülüyor', 1, notify)
            result = Image.open(enlarged)
            result.load()
        except Cancelled:
            raise
        except MediaError as error:
            details.update(model='Lanczos', note=f'Yapay zekâ bu bilgisayarda çalışamadı ({str(error)[:160]}); klasik yöntem kullanıldı.')
            notify('Klasik yöntemle büyütülüyor')
            result = working.resize(size_out, Image.LANCZOS)
    else:
        if options.upscale_method == 'ai':
            details['note'] = 'Real-ESRGAN bulunamadı; klasik Lanczos kullanıldı.'
        details['model'] = 'Lanczos'
        notify('Klasik yöntemle büyütülüyor')
        result = working.resize(size_out, Image.LANCZOS)
    if result.size != tuple(size_out):
        raise MediaError('Büyütülen fotoğrafın boyutu beklenenden farklı')
    if cancel.is_set():
        raise Cancelled('İptal edildi')
    notify('Büyütülen fotoğraf kaydediliyor')
    metadata = {key: info[key] for key in ('icc_profile', 'exif') if info.get(key)}
    if fmt == 'JPEG' and not has_alpha:
        candidate = work / 'upscaled.jpg'
        buffer = io.BytesIO()
        result.convert('RGB').save(buffer, format='JPEG', quality=95, subsampling=0, optimize=True, progressive=True)
        data = buffer.getvalue()
        try:
            import mozjpeg_lossless_optimization as mozjpeg
            data = mozjpeg.optimize(data, copy=mozjpeg.COPY_MARKERS.ALL)
        except (ImportError, ValueError):
            pass
        candidate.write_bytes(transplant_jpeg_markers(source, data))
        details['output_format'] = 'JPEG (kalite 95, 4:4:4)'
    elif fmt == 'WEBP':
        candidate = work / 'upscaled.webp'
        result.save(candidate, format='WEBP', lossless=True, method=4, exact=True, **metadata)
        details['output_format'] = 'WebP (kayıpsız)'
    else:
        candidate = work / 'upscaled.png'
        result.save(candidate, format='PNG', compress_level=6, **metadata)
        oxipng = find_tool('oxipng', required=False)
        if oxipng and candidate.stat().st_size < 400 * 1024**2:
            try:
                run([oxipng, '-o', '2', '-q', '--strip', 'none', str(candidate)], cancel, timeout=600)
            except MediaError:
                pass
        details['output_format'] = 'PNG (kayıpsız)'
    with Image.open(candidate) as written:
        written.load()
        if written.size != tuple(size_out):
            raise MediaError('Kaydedilen fotoğrafın boyutu yanlış')
        consistency = photo_consistency(working, written)
    details['consistency'] = consistency
    if consistency['psnr'] < 20:
        raise MediaError(f"Büyütülen fotoğraf orijinalle tutarsız (PSNR {consistency['psnr']:.1f} dB); kaydedilmedi")
    checks = {'dimensions_target': True, 'metadata_copied': True, 'content_consistent': True}
    return candidate, checks, details


def photo_consistency(original: Image.Image, enlarged: Image.Image):
    """Shrink the result back and compare with the original: PSNR on RGB."""
    import math
    small = enlarged.convert(original.mode).resize(original.size, Image.LANCZOS)
    a, b = original.convert('RGB').tobytes(), small.convert('RGB').tobytes()
    step = max(1, len(a) // 3_000_000) * 3
    total = count = 0
    for offset in range(0, len(a), step):
        for i in range(offset, min(offset + 3, len(a))):
            diff = a[i] - b[i]
            total += diff * diff
            count += 1
    mse = total / max(1, count)
    return {'psnr': 99.0 if mse == 0 else round(10 * math.log10(255 * 255 / mse), 2),
            'note': 'Büyütülen görüntü orijinal boyuta küçültülüp orijinalle karşılaştırıldı.'}


# ---------------------------------------------------------------- videos
def upscale_video(source: Path, metadata: dict, work: Path, cancel, notify, options: Options, video_processor):
    from .probe import pixel_properties, hdr, probe, validate_audio
    from .video import Progress
    video = metadata['video']
    depth, chroma, alpha = pixel_properties(video['pix_fmt'])
    details = {'mode': 'upscale', 'source_size': [video['width'], video['height']], 'method': options.upscale_method,
               'target': options.upscale_target}
    size = target_size(video['width'], video['height'], options.upscale_target if options.upscale_target != '4x' else '4k', even=True)
    if size is None:
        return None, {}, {**details, 'reason': 'Video zaten 4K veya daha büyük; büyütülmedi, orijinal korundu.'}
    if hdr(video) or alpha or depth is None:
        return None, {}, {**details, 'reason': 'HDR, alfa kanallı veya özel biçimli video büyütülmez; orijinal korundu.'}
    try:
        fps, avg = Fraction(video['r_frame_rate']), Fraction(video['avg_frame_rate'])
    except (KeyError, ValueError, ZeroDivisionError):
        fps = avg = Fraction(0)
    if fps <= 0 or abs(fps - avg) > fps / 1000:
        return None, {}, {**details, 'reason': 'Değişken kare hızlı (VFR) video büyütmede zamanlama korunamaz; orijinal korundu.'}
    ai = options.upscale_method == 'ai' and depth == 8 and available()
    if options.upscale_method == 'ai' and depth > 8:
        details['note'] = '10-bit video yapay zekâ ile 8-bit\'e düşürülmesin diye klasik yöntemle büyütüldü.'
    details['target_size'] = list(size)
    ffmpeg, ffprobe = find_tool('ffmpeg'), find_tool('ffprobe')
    counted = run([ffprobe, '-v', 'error', '-select_streams', str(video['index']), '-count_packets',
                   '-show_entries', 'stream=nb_read_packets', '-of', 'csv=p=0', str(source)], cancel, timeout=600).split()
    # FFprobe 9 may print the stream twice (stream groups); the first number is the stream's.
    packets = int(counted[0]) if counted and counted[0].isdigit() else 0
    frames = packets or int(round(metadata['duration'] * float(fps)))
    # Lossless 4K intermediate (~5 bit/pixel) plus the final file must fit.
    need = size[0] * size[1] * frames * 0.7 + source.stat().st_size + 2 * 1024**3
    if shutil.disk_usage(work).free < need:
        raise MediaError(f'4K ara dosya için yaklaşık {need / 1024**3:.0f} GB boş disk alanı gerekiyor')
    matrix = MATRICES.get(video.get('color_space'), 'bt709' if video['height'] >= 720 else 'bt601')
    full = video.get('color_range') == 'pc'
    out_fmt = {'420': 'yuv420p', '422': 'yuv422p', '444': 'yuv444p'}[chroma] + ('' if depth == 8 else f'{depth}le')
    tags = []
    for field, flag in [('color_range', '-color_range'), ('color_space', '-colorspace'),
                        ('color_transfer', '-color_trc'), ('color_primaries', '-color_primaries')]:
        if video.get(field) not in (None, 'unknown', 'unspecified'):
            tags += [flag, video[field]]
    rate = f'{fps.numerator}/{fps.denominator}'
    lossless = ['-c:v', 'libx264', '-qp', '0', '-preset', 'ultrafast', '-threads', str(options.worker_threads)]
    video_only = work / 'upscaled-video.mkv'
    if ai:
        scale = 2 if max(size[0] / video['width'], size[1] / video['height']) <= 2 else (
            3 if max(size[0] / video['width'], size[1] / video['height']) <= 3 else 4)
        model = f'video{scale}'
        details['model'] = MODELS[model][0]
        range_name = 'pc' if full else 'tv'
        decode = [ffmpeg, '-v', 'error', '-nostdin', '-noautorotate', '-i', str(source), '-map', f"0:{video['index']}",
                  '-vf', f'scale=in_color_matrix={matrix}:in_range={range_name}:flags=accurate_rnd+full_chroma_int,format=rgb24',
                  '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
        encode = [ffmpeg, '-v', 'error', '-nostdin', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                  '-s', f'{size[0]}x{size[1]}', '-framerate', rate, '-i', '-',
                  '-vf', f'scale=out_color_matrix={matrix}:out_range={range_name}:flags=accurate_rnd,format={out_fmt}',
                  *lossless, *tags, str(video_only)]
        notify('Yapay zekâ ile büyütülüyor · kare kare')
        try:
            start_worker({'kind': 'video', 'decode': decode, 'encode': encode, 'model': model,
                          'src_width': video['width'], 'src_height': video['height'], 'width': size[0], 'height': size[1],
                          'frames_file': str(work / 'upscaled-frames.txt')}, work, cancel,
                         'Yapay zekâ ile büyütülüyor', frames, notify)
            processed = int((work / 'upscaled-frames.txt').read_text(encoding='ascii'))
        except Cancelled:
            raise
        except MediaError as error:
            details['note'] = f'Yapay zekâ bu bilgisayarda çalışamadı ({str(error)[:160]}); klasik yöntem kullanıldı.'
            ai = False
    if not ai:
        details['model'] = 'Lanczos'
        video_only.unlink(missing_ok=True)
        progress = Progress(work / 'classic.progress', frames, notify, 'Klasik yöntemle büyütülüyor')
        run([ffmpeg, '-v', 'error', '-nostdin', '-y', *progress.args(), '-noautorotate', '-i', str(source),
             '-map', f"0:{video['index']}", '-vf', f'scale={size[0]}:{size[1]}:flags=lanczos+accurate_rnd+full_chroma_int',
             '-r', rate, *lossless, *tags, str(video_only)], cancel, tick=progress)
        processed = frames
    if processed != frames:
        raise MediaError(f'Kare sayısı tutmuyor ({processed} / {frames}); büyütülen video kaydedilmedi')
    # Put the original audio/subtitles/chapters back next to the enlarged video.
    suffix = source.suffix.lower() if source.suffix.lower() in {'.mp4', '.mov', '.m4v', '.mkv'} else '.mkv'
    intermediate = work / ('enlarged' + suffix)
    start = float(video.get('start_time') or 0)
    run([ffmpeg, '-v', 'error', '-nostdin', '-y', '-itsoffset', f'{start:.6f}', '-i', str(video_only), '-i', str(source),
         '-map', '0:v:0', '-map', '1:a?', '-map', '1:s?', '-c', 'copy', '-map_metadata', '1', '-map_chapters', '1',
         *(['-movflags', '+faststart'] if suffix in {'.mp4', '.mov', '.m4v'} else []), str(intermediate)], cancel)
    video_only.unlink(missing_ok=True)
    notify('⁣Büyütülen video sıkıştırılıyor')
    inner = probe(intermediate, cancel)
    stage = work / 'encode'
    stage.mkdir()
    video_processor.notify = lambda message: notify('⁣' + message)
    candidate, checks, encode_details = video_processor.optimize(intermediate, inner, stage)
    if candidate is None:
        raise MediaError('Büyütülen video doğrulanmış biçimde sıkıştırılamadı: ' + encode_details.get('reason', ''))
    details.update(selected=encode_details.get('selected'), quality=encode_details.get('quality'),
                   timeline=encode_details.get('timeline'), encode_attempts=encode_details.get('attempts'))
    notify('⁣Orijinalle içerik ve ses karşılaştırılıyor')
    final = probe(candidate, cancel)
    if (final['video']['width'], final['video']['height']) != tuple(size):
        raise MediaError('Büyütülen videonun boyutu beklenenden farklı')
    if details.get('timeline', {}).get('frames') != frames:
        raise MediaError('Büyütülen videonun kare sayısı orijinalden farklı')
    details['audio'] = validate_audio_relative(source, candidate, metadata, cancel)
    details['consistency'] = video_consistency(source, candidate, video, work, cancel)
    if details['consistency']['psnr_y'] < 24:
        raise MediaError(f"Büyütülen video orijinalle tutarsız (PSNR {details['consistency']['psnr_y']:.1f} dB)")
    checks.update(dimensions_target=True, frame_count_and_timing=True, audio_samples=True, content_consistent=True)
    checks.pop('dimensions', None)
    return candidate, checks, details


def validate_audio_relative(source: Path, output: Path, metadata: dict, cancel):
    """Audio streams were copied; decoded samples must be identical, in order."""
    results = []
    for number, stream in enumerate(s for s in metadata['streams'] if s['codec_type'] == 'audio'):
        digests = [run([find_tool('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(path), '-map', f'0:a:{number}',
                        '-c:a', 'pcm_s32le', '-f', 'hash', '-hash', 'sha256', '-'], cancel).strip() for path in (source, output)]
        if digests[0] != digests[1]:
            raise MediaError('Ses akışı büyütme sırasında değişti')
        results.append({'stream': number, 'pcm_sha256': digests[0]})
    return results


def video_consistency(source: Path, candidate: Path, video: dict, work: Path, cancel):
    """Every 5th frame of the result, shrunk back to the source size, against the source."""
    from .video import Video
    log = work / 'consistency.csv'
    log.unlink(missing_ok=True)
    graph = (f"[0:{video['index']}]settb=1,setpts=N,format=yuv420p[r];"
             f"[1:v:0]scale={video['width']}:{video['height']}:flags=lanczos,settb=1,setpts=N,format=yuv420p[d];"
             f"[d][r]libvmaf=model=version=vmaf_v0.6.1:n_threads=8:n_subsample=5:shortest=1:log_fmt=csv:"
             f"log_path=consistency.csv:feature='name=psnr'")
    run([find_tool('ffmpeg'), '-hide_banner', '-nostdin', '-v', 'error', '-noautorotate', '-i', str(source),
         '-noautorotate', '-i', str(candidate), '-filter_complex', graph, '-f', 'null', '-'], cancel, cwd=work)
    rows = Video.read_csv(log)
    if not rows:
        raise MediaError('Büyütülen video ile orijinal karşılaştırılamadı')
    return {'vmaf': round(sum(r['vmaf'] for r in rows) / len(rows), 2),
            'psnr_y': round(sum(r['psnr_y'] for r in rows) / len(rows), 2), 'frames_compared': len(rows),
            'note': 'Sonuç orijinal boyuta küçültülüp orijinalle karşılaştırıldı (her 5. kare).'}
