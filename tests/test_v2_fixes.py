"""Regression tests for the 2.0 fixes: large/odd sources, banding, NVENC rate cap,
queueing of big jobs, ImageOptim-style photo paths."""
from pathlib import Path
import io
import struct
import threading
import time
import zlib

import pytest
from PIL import Image, ImageCms, PngImagePlugin

from lrxe8.core import MediaError, Options, Resources
from lrxe8.engine import Engine
from lrxe8.photos import canonical_rgba, jpeg_metadata, png_chunks, write_chunk
from lrxe8.probe import pixel_properties, same_or_deeper, video_stream_checks
from lrxe8.video import Video


def video_info(**changes):
    info = {'width': 3840, 'height': 2160, 'pix_fmt': 'yuv420p', 'color_range': 'tv', 'color_space': 'bt709',
            'color_transfer': 'bt709', 'color_primaries': 'bt709', 'chroma_location': 'left'}
    info.update(changes)
    return info


def test_pixel_format_families():
    assert pixel_properties('p010le') == (10, '420', False)
    assert pixel_properties('nv16') == (8, '422', False)
    assert pixel_properties('yuvj422p') == (8, '422', False)
    assert pixel_properties('yuva444p10le') == (10, '444', True)


def test_bit_depth_may_grow_but_never_shrink():
    assert same_or_deeper('yuv420p', 'yuv420p10le')
    assert not same_or_deeper('yuv420p10le', 'yuv420p')
    assert not same_or_deeper('yuv422p', 'yuv420p10le')
    assert not same_or_deeper('yuva420p', 'yuv420p10le')


def test_chroma_siting_only_compared_for_420():
    # x265 4:2:2 output cannot signal chroma siting; MJPEG says "center".
    video_stream_checks(video_info(pix_fmt='yuvj422p', color_range='pc', chroma_location='center'),
                        video_info(pix_fmt='yuv422p10le', color_range='pc', chroma_location='unspecified'))
    with pytest.raises(MediaError, match='chroma_location'):
        video_stream_checks(video_info(chroma_location='center'), video_info(pix_fmt='yuv420p10le', chroma_location='left'))
    with pytest.raises(MediaError, match='color_range'):
        video_stream_checks(video_info(color_range='pc'), video_info(color_range='tv'))


@pytest.fixture(scope='module')
def processor():
    return Video(Options(), threading.Event(), lambda _: None)


def test_ten_bit_targets(processor):
    assert processor.target_format('av1_nvenc', video_info()) == 'p010le'
    assert processor.target_format('hevc_nvenc', video_info()) == 'p010le'
    assert processor.target_format('libx265', video_info(pix_fmt='yuvj422p')) == 'yuv422p10le'
    assert processor.target_format('libsvtav1', video_info()) == 'yuv420p10le'
    # H.264 stays 8-bit for player compatibility.
    assert processor.target_format('libx264', video_info()) == 'yuv420p'
    with pytest.raises(MediaError):
        processor.target_format('libsvtav1', video_info(pix_fmt='yuv422p'))


def test_nvenc_has_explicit_rate_ceiling_and_compatible_level(processor):
    metadata = {'video': video_info(index=0, bit_rate='450000000', avg_frame_rate='60/1'), 'streams': [], 'format': {}}
    args = processor.encode_options('hevc_nvenc', 20, metadata['video'], metadata)
    # Without -maxrate HEVC NVENC caps 4K60 near 35 Mbit/s and ignores lower CQ values;
    # an unbounded maxrate made it signal level 6.2 that many players refuse.
    assert args[args.index('-maxrate') + 1] == str(int(160e6))
    assert args[args.index('-level') + 1] == '5.1'
    assert args[args.index('-tier') + 1] == 'high'
    small = {'video': video_info(index=0, width=1920, height=1080, bit_rate='20000000', avg_frame_rate='25/1'),
             'streams': [], 'format': {}}
    args = processor.encode_options('hevc_nvenc', 20, small['video'], small)
    assert args[args.index('-level') + 1] == '4.1'
    assert args[args.index('-maxrate') + 1] == str(int(30e6))
    # AV1 too: an 800 Mbit/s ceiling (lossless intermediates) made it ignore CQ.
    args = processor.encode_options('av1_nvenc', 20, metadata['video'], metadata)
    assert args[args.index('-maxrate') + 1] == str(int(160e6))
    assert '-level' not in args  # AV1 NVENC rejects explicit levels; the capped rate selects one


def test_mov_never_gets_av1(processor):
    metadata = {'video': video_info()}
    assert not any('av1' in name for name in processor.plan(metadata, '.mov'))
    assert processor.plan(metadata, '.mp4')[0] in {'av1_nvenc', 'libsvtav1'}


def test_quality_gate_rejects_banding_and_disproportionate_chroma(processor):
    good = {'vmaf': 98.6, 'vmaf_low': 97.0, 'cambi_added_mean': .1, 'cambi_added_high': .2,
            'cambi_output_mean': .3, 'cambi_output_high': .4, 'psnr_y': 50.0, 'psnr_cb': 52.0, 'psnr_cr': 52.0}
    assert processor.quality_problems(good) == []
    # 8-bit AV1 on a dark gradient: 0.16 -> 1.6 CAMBI is new, visible banding.
    assert processor.quality_problems({**good, 'cambi_added_mean': 1.45, 'cambi_output_mean': 1.6})
    # 0.45 -> 0.86 stays below the perceptibility floor (smoothed JPEG noise).
    assert processor.quality_problems({**good, 'cambi_added_mean': .41, 'cambi_output_mean': .86,
                                       'cambi_added_high': .68, 'cambi_output_high': 1.1}) == []
    assert processor.quality_problems({**good, 'vmaf_low': 94.0})
    assert processor.quality_problems({**good, 'psnr_cb': 36.0})
    # Grainy source: every plane is lower, chroma is not disproportionately worse.
    assert processor.quality_problems({**good, 'psnr_y': 39.0, 'psnr_cb': 38.5, 'psnr_cr': 38.5}) == []


def test_queued_big_job_waits_instead_of_failing(monkeypatch):
    import lrxe8.core as core
    from types import SimpleNamespace
    clock = [0.0]
    def monotonic():
        clock[0] += 30.0
        return clock[0]
    monkeypatch.setattr(core.time, 'monotonic', monotonic)
    monkeypatch.setattr(core.psutil, 'virtual_memory', lambda: SimpleNamespace(total=64*1024**3, available=64*1024**3))
    resources = Resources(maximum=1)
    release, acquired, errors = threading.Event(), threading.Event(), []
    def holder():
        with resources.lease(1024**3, 0, threading.Event(), lambda _: None):
            acquired.set()
            release.wait(5)
    def waiter():
        try:
            with resources.lease(1024**3, 0, threading.Event(), lambda _: None):
                pass
        except MediaError as error:
            errors.append(error)
    first = threading.Thread(target=holder)
    first.start()
    acquired.wait(5)
    second = threading.Thread(target=waiter)
    second.start()
    second.join(1.5)       # far more than "90 s" on the fake clock
    assert second.is_alive() and not errors
    release.set()
    first.join(5)
    second.join(5)
    assert not errors and resources.active == 0


def test_photo_open_has_no_decompression_bomb_limit():
    assert Image.MAX_IMAGE_PIXELS is None


def opaque_rgba_png(path, text=True):
    image = Image.new('RGBA', (160, 90))
    image.putdata([(x, y, (x * y) % 256, 255) for y in range(90) for x in range(160)])
    info = PngImagePlugin.PngInfo()
    if text:
        info.add_text('Comment', 'kamera / yazılım bilgisi')
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    image.save(path, compress_level=0, pnginfo=info, icc_profile=icc)


def test_opaque_rgba_png_is_reduced_losslessly_with_metadata(tmp_path):
    source = tmp_path/'opaque.png'
    opaque_rgba_png(source)
    result = Engine().optimize(source, tmp_path/'out')
    assert result.status == 'optimized', result.message
    output = Path(result.output)
    assert canonical_rgba(source, threading.Event()) == canonical_rgba(output, threading.Event())
    kinds = [kind for kind, _ in png_chunks(output)]
    assert b'iCCP' in kinds and (b'tEXt' in kinds or b'iTXt' in kinds)
    assert b'IHDR' in kinds and dict(png_chunks(output))[b'IHDR'][9] == 2  # RGBA -> RGB


def test_strip_metadata_keeps_colour_profile_only(tmp_path):
    source = tmp_path/'strip.png'
    opaque_rgba_png(source)
    result = Engine(Options(strip_metadata=True)).optimize(source, tmp_path/'out')
    assert result.status == 'optimized', result.message
    output = Path(result.output)
    kinds = [kind for kind, _ in png_chunks(output)]
    assert b'iCCP' in kinds and b'tEXt' not in kinds and b'iTXt' not in kinds
    assert dict(png_chunks(source))[b'iCCP'] == dict(png_chunks(output))[b'iCCP']
    assert canonical_rgba(source, threading.Event()) == canonical_rgba(output, threading.Event())


def test_strip_metadata_keeps_jpeg_orientation_and_icc(tmp_path):
    source = tmp_path/'rotated.jpg'
    image = Image.new('RGB', (120, 80))
    image.putdata([(x * 2, y * 3, (x + y) % 256) for y in range(80) for x in range(120)])
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010F] = 'Kamera'
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    image.save(source, quality=95, exif=exif.tobytes(), icc_profile=icc, comment=b'yorum')
    result = Engine(Options(strip_metadata=True)).optimize(source, tmp_path/'out')
    assert result.status == 'optimized', result.message
    with Image.open(source) as a, Image.open(result.output) as b:
        assert b.getexif().get(0x0112) == 6
        assert 0x010F not in b.getexif()
        assert a.info['icc_profile'] == b.info['icc_profile']
        assert a.tobytes() == b.tobytes()


def test_jpeg_comment_between_progressive_scans_is_not_reported_as_loss(tmp_path):
    """Regression (WhatsApp JPEG): jpegtran moves a COM marker that sits between
    progressive scans to the header; that is not metadata loss."""
    buffer = io.BytesIO()
    image = Image.new('RGB', (96, 64))
    image.putdata([(x * 2, y * 4, (x * y) % 256) for y in range(64) for x in range(96)])
    image.save(buffer, format='JPEG', quality=90, progressive=True)
    data = buffer.getvalue()
    first = data.index(b'\xff\xda')
    second = data.index(b'\xff\xda', first + 2)
    comment = b'\xff\xfe\x00\x03\x00'
    source = tmp_path/'scan-comment.jpg'
    source.write_bytes(data[:second] + comment + data[second:])
    assert ('fe', '00') in jpeg_metadata(source)
    result = Engine().optimize(source, tmp_path/'out')
    assert result.status in {'optimized', 'kept'}, result.message
    if result.output:
        assert sorted(jpeg_metadata(source)) == sorted(jpeg_metadata(Path(result.output)))
