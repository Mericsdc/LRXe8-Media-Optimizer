from copy import deepcopy
from pathlib import Path
import threading

import pytest

from lrxe8.core import MediaError, Options, find_tool, run
from lrxe8.probe import creation_time_equivalent, metadata_checks, probe
from lrxe8.video import Video

DATE = '2023-12-01T00:02:00.000000Z'


def media_metadata():
    video = {'index': 0, 'codec_type': 'video', 'codec_name': 'h264', 'width': 1920,
             'height': 1080, 'pix_fmt': 'yuv420p', 'tags': {'creation_time': DATE}}
    audio = {'index': 1, 'codec_type': 'audio', 'codec_name': 'aac', 'tags': {'creation_time': DATE}}
    return {'format': {'tags': {'creation_time': DATE, 'title': 'Keep this title'}},
            'video': video, 'streams': [video, audio]}


@pytest.mark.parametrize('context', ['format', 'video', 'audio'])
def test_duplicate_creation_time_is_preserved(context):
    source = media_metadata()
    output = deepcopy(source)
    target = output['format'] if context == 'format' else output['streams'][context == 'audio']
    target['tags']['creation_time'] = DATE + ';' + DATE
    assert all(metadata_checks(source, output).values())


@pytest.mark.parametrize('value', [
    '2023-12-01T00:02:00Z',
    '2023-12-01T03:02:00+03:00',
    '2023-11-30T19:02:00-05:00',
    DATE + ';2023-12-01T03:02:00+03:00',
])
def test_equal_iso_timestamp_representations(value):
    assert creation_time_equivalent(DATE, value)


@pytest.mark.parametrize('value', [None, '', DATE + ';', 'invalid',
    '2023-12-01T00:02:01Z', '2023-12-01T00:02:00.000001Z',
    '2023-12-01T00:02:00.000000001Z',
    DATE + ';2023-12-01T00:02:01Z', '2023-12-01T00:02:00'])
def test_missing_changed_conflicting_or_invalid_timestamp_fails(value):
    source = media_metadata()
    output = deepcopy(source)
    if value is None:
        del output['format']['tags']['creation_time']
    else:
        output['format']['tags']['creation_time'] = value
    with pytest.raises(MediaError, match='creation_time'):
        metadata_checks(source, output)


def test_other_metadata_remains_strict():
    source = media_metadata()
    output = deepcopy(source)
    output['format']['tags']['title'] = 'Keep this title;Keep this title'
    with pytest.raises(MediaError, match='title'):
        metadata_checks(source, output)


def test_real_mp4_mdta_creation_time_round_trip(tmp_path):
    cancel = threading.Event()
    source = tmp_path / 'source.mp4'
    output = tmp_path / 'output.mp4'
    run([find_tool('ffmpeg'), '-v', 'error', '-n', '-f', 'lavfi', '-i',
         'color=size=1920x1080:rate=30:duration=0.1', '-f', 'lavfi', '-i',
         'anullsrc=r=48000:cl=stereo', '-t', '0.1', '-map', '0:v', '-map', '1:a',
         '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '2', '-c:a', 'aac',
         '-metadata', 'creation_time=' + DATE, '-metadata', 'title=Date regression',
         '-metadata:s:0', 'creation_time=' + DATE, '-metadata:s:1', 'creation_time=' + DATE,
         str(source)], cancel)
    before = probe(source, cancel)
    video = Video(Options(), cancel, lambda _: None)
    command = video.command(source, output, before, 'libx264', 18)
    run(command, cancel)
    after = probe(output, cancel)
    assert all(metadata_checks(before, after).values())
    assert after['format']['tags']['title'] == 'Date regression'
    assert creation_time_equivalent(DATE, after['format']['tags']['creation_time'])
    for stream in after['streams']:
        assert creation_time_equivalent(DATE, stream['tags']['creation_time'])
