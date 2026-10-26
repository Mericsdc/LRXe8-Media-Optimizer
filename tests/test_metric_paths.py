from concurrent.futures import ThreadPoolExecutor
import math
from pathlib import Path
import shutil
import threading

import pytest

from lrxe8.core import MediaError, Options, find_tool, run
from lrxe8.probe import probe
from lrxe8.video import Video


@pytest.fixture(scope='module')
def video_source(tmp_path_factory):
    source = tmp_path_factory.mktemp('metric-fixture')/'source.mp4'
    cancel = threading.Event()
    run([find_tool('ffmpeg'), '-v', 'error', '-n', '-f', 'lavfi', '-i',
         'testsrc2=size=1920x1080:rate=25:duration=0.12', '-c:v', 'libx264',
         '-threads', '2', '-preset', 'ultrafast', '-qp', '0',
         '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
         str(source)], cancel)
    return source, probe(source, cancel)


@pytest.mark.parametrize('name', ['Kayıpsız VF', 'Türkçe ve boşluk', "Kullanıcı'nın [Örnek], klasörü"])
def test_real_vmaf_works_with_unicode_spaces_and_filter_punctuation(tmp_path, video_source, name):
    original, metadata = video_source
    work = tmp_path/name
    work.mkdir()
    source = work/"Çığ görüntüsü ' [] .mp4"
    shutil.copy2(original, source)
    before = Path.cwd()
    result = Video(Options(), threading.Event(), lambda _: None).metric(source, source, metadata, work)
    assert result['frames_measured'] == 3
    # Identical input: no deficit against the model's own ceiling, no added banding.
    assert result['vmaf'] == pytest.approx(100, abs=1e-6)
    assert result['cambi_added_mean'] == 0
    assert math.isfinite(result['psnr_cb'])
    assert (work/'q.csv').is_file() and (work/'c.csv').is_file()
    assert Path.cwd() == before


def test_concurrent_metrics_have_separate_child_working_directories(tmp_path, video_source):
    source, metadata = video_source
    before = Path.cwd()
    def metric(name):
        work = tmp_path/name
        work.mkdir()
        result = Video(Options(), threading.Event(), lambda _: None).metric(source, source, metadata, work)
        return result, work
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(metric, ['İşlem ı', 'İşlem ş']))
    assert all(result['frames_measured'] == 3 and math.isfinite(result['vmaf']) for result, _ in results)
    assert all((work/'q.csv').exists() for _, work in results)
    assert Path.cwd() == before


def test_missing_metric_file_does_not_reuse_stale_results(tmp_path, monkeypatch):
    import lrxe8.video as module
    work = tmp_path/'Kayıpsız'
    work.mkdir()
    (work/'q.csv').write_text('Frame,psnr_y,psnr_cb,psnr_cr,cambi,vmaf\n0,60,60,60,0,100\n', encoding='utf-8')
    processor = Video.__new__(Video)
    processor.ffmpeg, processor.ffprobe = 'ffmpeg', 'ffprobe'
    processor.filters = 'libvmaf'
    processor.options = Options()
    processor.cancel = threading.Event()
    processor.threads = 2
    processor.notify = lambda _: None
    metadata = {'duration': 1.0, 'video': {'index': 0, 'width': 3840, 'height': 2160, 'pix_fmt': 'yuv420p',
                                           'color_space': 'bt709', 'avg_frame_rate': '25/1'}}
    def fake_run(args, cancel, **kwargs):
        if 'ffprobe' in args[0]:
            return 'yuv420p\n'
        assert kwargs['cwd'] == work.resolve()
        return ''
    monkeypatch.setattr(module, 'run', fake_run)
    with pytest.raises(MediaError, match='VMAF sonuç dosyası oluşturulamadı'):
        processor.metric(tmp_path/'source.mp4', tmp_path/'output.mp4', metadata, work)
    assert not (work/'q.csv').exists()


def test_non_frame_aligned_sample_is_paired_by_frame_not_timestamp(tmp_path):
    """Regression: a sample cut at a non-frame-aligned offset into MKV (1 ms ticks)
    was paired with neighbouring frames, reporting heavy loss for a near-lossless encode."""
    cancel = threading.Event()
    source = tmp_path/'source60.mp4'
    run([find_tool('ffmpeg'), '-v', 'error', '-n', '-f', 'lavfi', '-i',
         'testsrc2=size=1920x1080:rate=60:duration=3', '-c:v', 'libx264', '-preset', 'ultrafast',
         '-qp', '0', '-pix_fmt', 'yuv420p', str(source)], cancel)
    metadata = probe(source, cancel)
    video = Video(Options(), cancel, lambda _: None)
    sample = tmp_path/'sample.mkv'
    segment = (1.2345, 1.0)
    run(video.command(source, sample, metadata, 'libx264', 4, segment), cancel)
    result = video.metric(source, sample, metadata, tmp_path, segment)
    assert result['vmaf'] > 97, result
    assert result['vmaf_low'] > 95, result
