from fractions import Fraction
import json
from pathlib import Path
import threading

import pytest
from PIL import Image, PngImagePlugin, ImageCms

from lrxe8.core import Options, Resources, MediaError, Cancelled, publish, run, find_tool
from lrxe8.engine import Engine
from lrxe8.photos import pixel_signature, png_chunks, jpeg_metadata, canonical_rgba
from lrxe8.probe import compare_timeline, pixel_properties, static_hdr_fields


def manifest(path, pts, duration=40, width=1920, height=1080):
    path.write_text(''.join(f'pts={p}|duration={duration}|width={width}|height={height}|pix_fmt=yuv420p\n' for p in pts))
    return path


def metadata(tb='1/1000'):
    return {'width': 1920, 'height': 1080, 'pix_fmt': 'yuv420p', 'time_base': tb, 'avg_frame_rate': '25/1'}


def test_vfr_and_common_offset(tmp_path):
    a = manifest(tmp_path / 'a', [0, 40, 100, 120])
    b = manifest(tmp_path / 'b', [250, 290, 350, 370])
    result = compare_timeline(a, b, metadata(), metadata())
    assert result['frames'] == 4
    assert result['common_shift_seconds'] == .25


@pytest.mark.parametrize('pts', [[0, 40, 120], [0, 40, 80, 120], [0, 40, 101, 120], [0, 40, 40, 120]])
def test_timing_drop_cfr_duplicate_and_drift_rejected(tmp_path, pts):
    a = manifest(tmp_path / 'a', [0, 40, 100, 120])
    b = manifest(tmp_path / 'b', pts)
    with pytest.raises(MediaError):
        compare_timeline(a, b, metadata(), metadata())


def test_changed_dimensions_rejected(tmp_path):
    a = manifest(tmp_path / 'a', [0, 40])
    b = manifest(tmp_path / 'b', [0, 40], width=1280, height=720)
    with pytest.raises(MediaError, match='çözünürlük'):
        compare_timeline(a, b, metadata(), metadata())


def test_high_depth_equivalents():
    assert pixel_properties('p010le') == pixel_properties('yuv420p10le')
    assert pixel_properties('yuv420p10le') != pixel_properties('yuv420p')


def test_hdr_frame_and_stream_metadata_resolve_equally():
    mastering = {'side_data_type': 'Mastering display metadata', 'min_luminance': '0/10000', 'max_luminance': '10000000/10000'}
    cll = {'side_data_type': 'Content light level metadata', 'max_content': 1000, 'max_average': 400}
    source = {'frame_side_data': [mastering, cll]}
    output = {'side_data_list': [mastering, cll], 'frame_side_data': [{'max_content': 0, 'max_average': 0}]}
    assert static_hdr_fields(source) == static_hdr_fields(output)


def test_conflicting_hdr_is_rejected():
    with pytest.raises(MediaError, match='Çelişen'):
        static_hdr_fields({'side_data_list': [{'max_content': 1000}], 'frame_side_data': [{'max_content': 500}]})


def test_missing_hdr_is_rejected_at_frame_level(tmp_path):
    a = manifest(tmp_path / 'a', [0, 40])
    b = manifest(tmp_path / 'b', [0, 40])
    a.write_text(a.read_text().replace('pix_fmt=yuv420p', 'pix_fmt=yuv420p|side_datum/content_light_level_metadata:max_content=1000'))
    with pytest.raises(MediaError, match='HDR'):
        compare_timeline(a, b, metadata(), metadata())


def test_approximate_fps_label_cannot_hide_change(tmp_path):
    a = manifest(tmp_path / 'a', [0, 40])
    b = manifest(tmp_path / 'b', [0, 40])
    other = {**metadata(), 'avg_frame_rate': '25000/1001'}
    with pytest.raises(MediaError, match='kare hızı'):
        compare_timeline(a, b, metadata(), other)


def test_memory_budget_reduces_concurrency(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    import time
    import lrxe8.core as core
    monkeypatch.setattr(core.psutil, 'virtual_memory', lambda: SimpleNamespace(total=12*1024**3, available=12*1024**3))
    resources = Resources(maximum=2)
    active = peak = 0
    lock = threading.Lock()
    def job():
        nonlocal active, peak
        with resources.lease(6*1024**3, 0, threading.Event(), lambda _: None):
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(.1)
            with lock:
                active -= 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: job(), range(2)))
    assert peak == 1
    assert resources.active == resources.ram_reserved == resources.gpu_reserved == 0


def test_bframe_packet_duration_does_not_change_display_time(tmp_path):
    a = manifest(tmp_path / 'a', [0, 40, 100, 120])
    b = manifest(tmp_path / 'b', [0, 40, 100, 120])
    b.write_text(b.read_text().replace('pts=0|duration=40', 'pts=0|duration=30'))
    assert compare_timeline(a, b, metadata(), metadata())['max_timing_error_seconds'] == 0


def test_small_png_preserves_alpha_icc_and_metadata(tmp_path):
    source = tmp_path / 'tiny.png'
    image = Image.new('RGBA', (64, 32), (18, 40, 200, 0))
    info = PngImagePlugin.PngInfo()
    info.add_itxt('Comment', 'Türkçe metadata')
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    image.save(source, compress_level=0, pnginfo=info, icc_profile=icc)
    before = source.read_bytes()
    result = Engine().optimize(source, tmp_path / 'out')
    assert result.status == 'optimized', result.message
    assert source.read_bytes() == before
    cancel = threading.Event()
    assert canonical_rgba(source, cancel) == canonical_rgba(Path(result.output), cancel)
    layout = {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS'}
    assert [(k, v) for k, v in png_chunks(source) if k not in layout] == [(k, v) for k, v in png_chunks(Path(result.output)) if k not in layout]
    assert all(result.checks.values())


@pytest.mark.parametrize('mode', ['P', 'I;16'])
def test_png_palette_and_high_depth_are_exact(tmp_path, mode):
    source = tmp_path / 'depth.png'
    if mode == 'P':
        image = Image.new('P', (80, 40))
        image.putpalette([n for i in range(256) for n in (i, 255-i, i)])
        image.info['transparency'] = bytes(range(256))
    else:
        image = Image.frombytes('I;16', (80, 40), b'\x34\x12' * (80*40))
    image.save(source, compress_level=0)
    result = Engine().optimize(source, tmp_path / 'out')
    assert result.status == 'optimized', result.message
    if mode == 'P':
        # Lossless palette reordering/reduction is allowed; decoded RGBA must be identical.
        assert canonical_rgba(source, threading.Event()) == canonical_rgba(Path(result.output), threading.Event())
    else:
        assert pixel_signature(source, threading.Event()) == pixel_signature(Path(result.output), threading.Event())


def test_reoptimization_does_not_publish_larger_result(tmp_path):
    source = tmp_path / 'small.png'
    Image.new('RGB', (32, 24), 'red').save(source, compress_level=0)
    first = Engine().optimize(source, tmp_path / 'out')
    second = Engine().optimize(Path(first.output), tmp_path / 'out')
    assert second.status == 'kept'
    assert second.output is None


def test_webp_transparent_rgb_preserved(tmp_path):
    source = tmp_path / 'alpha.webp'
    image = Image.new('RGBA', (64, 64), (80, 150, 33, 0))
    image.putpixel((0, 0), (10, 20, 30, 128))
    image.save(source, lossless=True, exact=True, method=0, xmp=b'<xmp>keep</xmp>')
    original = source.read_bytes()
    result = Engine().optimize(source, tmp_path / 'out')
    assert result.status in {'kept', 'optimized'}, result.message
    assert source.read_bytes() == original
    if result.output:
        assert pixel_signature(source, threading.Event()) == pixel_signature(Path(result.output), threading.Event())


def test_cancel_preserves_original(tmp_path):
    source = tmp_path / 'source.png'
    Image.new('RGB', (64, 64)).save(source)
    cancel = threading.Event()
    cancel.set()
    result = Engine(cancel=cancel).optimize(source, tmp_path / 'out')
    assert result.status == 'cancelled'
    assert source.exists()
    assert not result.output


@pytest.mark.parametrize('suffix,fmt', [('heic', 'HEIF'), ('avif', 'AVIF')])
def test_heif_avif_padding_preserves_all_encoded_image_bytes(tmp_path, suffix, fmt):
    import struct
    path = tmp_path / f'tiny.{suffix}'
    Image.new('RGB', (32, 24), (10, 30, 50)).save(path, format=fmt)
    encoded = path.read_bytes()
    with path.open('ab') as stream:
        stream.write(struct.pack('>I4s', 16392, b'free') + bytes(16384))
    original = path.read_bytes()
    result = Engine().optimize(path, tmp_path / 'out')
    assert result.status == 'optimized', result.message
    assert path.read_bytes() == original
    assert Path(result.output).read_bytes() == encoded
    assert result.checks['encoded_payload_exact']


def test_unknown_bmff_metadata_is_not_stripped(tmp_path):
    import struct
    path = tmp_path / 'tiny.avif'
    Image.new('RGB', (32, 24), (10, 30, 50)).save(path, format='AVIF')
    with path.open('ab') as stream:
        stream.write(struct.pack('>I4s', 24, b'uuid') + bytes(16))
    result = Engine().optimize(path, tmp_path / 'out')
    assert result.status == 'kept' and not result.output


def test_no_overwrite_even_with_collision(tmp_path):
    source = tmp_path / 'source.png'
    source.write_bytes(b'original')
    candidate = tmp_path / 'candidate.png'
    candidate.write_bytes(b'smaller')
    occupied = tmp_path / 'source.optimized.png'
    occupied.write_bytes(b'existing')
    target = publish(candidate, tmp_path, source, threading.Event())
    assert target.name == 'source.optimized-1.png'
    assert occupied.read_bytes() == b'existing'
    assert source.read_bytes() == b'original'


def test_corrupt_image_fails_and_is_retained(tmp_path):
    path = tmp_path / 'bad.png'
    path.write_bytes(b'bad image')
    result = Engine().optimize(path, tmp_path / 'out')
    assert result.status == 'failed'
    assert path.read_bytes() == b'bad image'
    assert not result.output


def test_no_resize_or_fps_in_final_command(tmp_path):
    from lrxe8.video import Video
    instance = Video(Options(), threading.Event(), lambda _: None)
    data = {'video': {**metadata('1/90000'), 'index': 0}, 'streams': [{'index': 0, 'codec_type': 'video'}]}
    for name in ['av1_nvenc', 'hevc_nvenc', 'h264_nvenc', 'libsvtav1', 'libx265', 'libx264']:
        cmd = instance.command(tmp_path / 'source.mp4', tmp_path / 'out.mp4', data, name, 22)
        assert '-r' not in cmd and '-s' not in cmd and '-vf' not in cmd
        assert '-t' not in cmd and '-ss' not in cmd
        assert 'passthrough' in cmd and '-noautorotate' in cmd
        assert '-copyts' in cmd


def test_subprocess_cancellation(tmp_path):
    import sys
    cancel = threading.Event()
    timer = threading.Timer(.3, cancel.set)
    timer.start()
    with pytest.raises(Cancelled):
        run([sys.executable, '-c', 'import time; time.sleep(20)'], cancel)
    timer.join()
