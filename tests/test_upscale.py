"""Opt-in enlargement: sizes, photos (AI + classic) and a short video through the
whole pipeline (enlarge -> lossless intermediate -> verified encode)."""
from pathlib import Path
import threading

import pytest
from PIL import Image, ImageCms

from lrxe8.core import Options, find_tool, run
from lrxe8.engine import Engine
from lrxe8.probe import probe
from lrxe8.upscale import available, target_size


def test_target_sizes():
    assert target_size(1920, 1080, '4k') == (3840, 2160)
    assert target_size(1080, 1920, '4k') == (2160, 3840)          # portrait
    assert target_size(1280, 720, '4k') == (3840, 2160)
    assert target_size(1600, 1200, '4k') == (2880, 2160)
    assert target_size(3840, 2160, '4k') is None                  # already 4K
    assert target_size(1254, 1254, '4x') == (5016, 5016)
    assert target_size(641, 361, '2x', even=True) == (1282, 722)


def source_photo(path, size=(96, 64)):
    image = Image.new('RGB', size)
    image.putdata([(x * 2 % 256, y * 3 % 256, (x * y) % 256) for y in range(size[1]) for x in range(size[0])])
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    image.save(path, icc_profile=icc)
    return path


def test_classic_photo_upscale_keeps_profile_and_never_touches_source(tmp_path):
    source = source_photo(tmp_path / 'küçük.png')
    before = source.read_bytes()
    result = Engine(Options(mode='upscale', upscale_target='4x', upscale_method='classic')).optimize(source, tmp_path / 'out')
    assert result.status == 'optimized', result.message
    assert source.read_bytes() == before
    output = Path(result.output)
    assert output.name == 'küçük.upscaled-4x.png'
    with Image.open(output) as image, Image.open(source) as original:
        assert image.size == (384, 256)
        assert image.info['icc_profile'] == original.info['icc_profile']
    assert result.details['consistency']['psnr'] > 25
    assert result.details['model'] == 'Lanczos'


def test_photo_already_large_is_kept(tmp_path):
    source = source_photo(tmp_path / 'big.png', (3840, 2160))
    result = Engine(Options(mode='upscale', upscale_target='4k', upscale_method='classic')).optimize(source, tmp_path / 'out')
    assert result.status == 'kept' and result.output is None


@pytest.mark.skipif(not available(), reason='Real-ESRGAN modülü yok')
def test_ai_photo_upscale_runs_in_worker_process(tmp_path):
    source = source_photo(tmp_path / 'logo.jpg')
    result = Engine(Options(mode='upscale', upscale_target='2x', upscale_content='art')).optimize(source, tmp_path / 'out')
    assert result.status == 'optimized', result.message
    assert result.details['model'] == 'realesrgan-x4plus-anime', result.details
    with Image.open(result.output) as image:
        assert image.size == (192, 128) and image.format == 'JPEG'


@pytest.mark.parametrize('method', ['classic', 'ai'])
def test_short_video_upscale_end_to_end(tmp_path, method):
    if method == 'ai' and not available():
        pytest.skip('Real-ESRGAN modülü yok')
    cancel = threading.Event()
    source = tmp_path / 'clip.mp4'
    run([find_tool('ffmpeg'), '-v', 'error', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=480x270:rate=25:duration=1',
         '-f', 'lavfi', '-i', 'sine=f=440:r=48000:duration=1', '-c:v', 'libx264', '-crf', '12', '-pix_fmt', 'yuv420p',
         '-c:a', 'aac', '-shortest', str(source)], cancel)
    result = Engine(Options(mode='upscale', upscale_target='2x', upscale_method=method, max_parallel=1)).optimize(
        source, tmp_path / 'out')
    assert result.status == 'optimized', result.message
    output = probe(Path(result.output), cancel)
    assert (output['video']['width'], output['video']['height']) == (960, 540)
    assert result.details['timeline']['frames'] == 25
    assert result.details['audio'] and result.checks['audio_samples']
    assert result.details['consistency']['psnr_y'] > 24
