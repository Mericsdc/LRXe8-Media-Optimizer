from pathlib import Path
import threading

import pytest

from lrxe8.core import MediaError, find_tool, run
from lrxe8.mov_metadata import date_fields, preserve_native_dates
from lrxe8.probe import probe, metadata_checks, compare_timeline


def test_mov_timecode_track_keeps_its_own_creation_date(tmp_path):
    cancel = threading.Event()
    source, output = tmp_path/'source.mov', tmp_path/'output.mov'
    run([find_tool('ffmpeg'), '-v', 'error', '-n', '-f', 'lavfi', '-i',
         'color=size=1920x1080:rate=25:duration=0.12', '-c:v', 'libx264',
         '-preset', 'ultrafast', '-threads', '2', '-timecode', '00:00:00:00',
         '-metadata', 'creation_time=2016-05-04T11:08:48Z', str(source)], cancel)
    handlers, fields = date_fields(source)
    assert handlers == (b'vide', b'tmcd')
    # A real camera/editor can give its timecode track a different native date.
    position, width, created, modified = fields[(1, 'mdhd')]
    with source.open('r+b') as stream:
        stream.seek(position)
        stream.write((created+174).to_bytes(width, 'big'))
    before = probe(source, cancel)
    assert before['streams'][1]['tags']['creation_time'] == '2016-05-04T11:11:42.000000Z'
    run([find_tool('ffmpeg'), '-v', 'error', '-n', '-i', str(source), '-map', '0',
         '-c', 'copy', '-map_metadata', '0', '-movflags', '+faststart+use_metadata_tags', str(output)], cancel)
    encoded = output.read_bytes()
    _, output_fields = date_fields(output)
    allowed = {n for position, width, _, _ in output_fields.values() for n in range(position, position+2*width)}
    preserve_native_dates(source, output)
    restored = output.read_bytes()
    assert len(encoded) == len(restored)
    assert {n for n, (a, b) in enumerate(zip(encoded, restored)) if a != b} <= allowed
    assert all(metadata_checks(before, probe(output, cancel)).values())


def frame_file(path, pts, duration):
    path.write_text(''.join(f'pts={value}|duration={duration}|width=1920|height=1080|pix_fmt=yuv420p\n' for value in pts))
    return path


def test_native_one_tick_per_frame_source_can_use_finer_output_clock(tmp_path):
    a = frame_file(tmp_path/'a', [0, 1, 2], 1)
    b = frame_file(tmp_path/'b', [0, 512, 1024], 512)
    source = {'width': 1920, 'height': 1080, 'pix_fmt': 'yuv420p', 'time_base': '1/25', 'avg_frame_rate': '25/1'}
    output = {**source, 'time_base': '1/12800'}
    result = compare_timeline(a, b, source, output)
    assert result['max_timing_error_seconds'] == 0
    assert result['frames'] == 3


def test_coarse_source_does_not_hide_output_pts_drift(tmp_path):
    a = frame_file(tmp_path/'a', [0, 1, 2], 1)
    b = frame_file(tmp_path/'b', [0, 513, 1024], 512)
    source = {'width': 1920, 'height': 1080, 'pix_fmt': 'yuv420p', 'time_base': '1/25', 'avg_frame_rate': '25/1'}
    with pytest.raises(MediaError, match='zamanlama değişti'):
        compare_timeline(a, b, source, {**source, 'time_base': '1/12800'})


def test_coarse_clock_cannot_hide_an_extra_final_frame_duration(tmp_path):
    a = frame_file(tmp_path/'a', [0, 1, 2], 1)
    b = frame_file(tmp_path/'b', [0, 1, 2], 1)
    b.write_text(b.read_text().replace('pts=2|duration=1', 'pts=2|duration=2'))
    source = {'width': 1920, 'height': 1080, 'pix_fmt': 'yuv420p', 'time_base': '1/25', 'avg_frame_rate': '25/1'}
    with pytest.raises(MediaError, match='süresi değişti'):
        compare_timeline(a, b, source, source)
