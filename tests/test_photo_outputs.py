from pathlib import Path
import json
import random
import struct
import threading
import zlib

from PIL import Image, ImageCms, PngImagePlugin

from lrxe8.core import Options, sha256
from lrxe8.engine import Engine
from lrxe8.photos import png_chunks, pixel_signature, write_chunk
from lrxe8.photo_small import MIN_SSIMULACRA2, stored_extra_metadata


def fixture(path, alpha=False, metadata=False):
    image = Image.new('RGBA' if alpha else 'RGB', (192, 128))
    image.putdata([(x, y, (x+y)//2, (x*3+y)%256) if alpha else (x, y, (x+y)//2)
                   for y in range(128) for x in range(192)])
    arguments = {'compress_level': 0}
    if metadata:
        info = PngImagePlugin.PngInfo()
        info.add_text('Description', 'Türkçe özel metadata')
        info.add_itxt('XML:com.adobe.xmp', '<x:xmpmeta xmlns:x="adobe:ns:meta/">keep</x:xmpmeta>')
        exif = Image.Exif()
        exif[315] = 'LRXe8 test'
        exif[274] = 6
        arguments.update(pnginfo=info, exif=exif.tobytes(),
                         icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
    image.save(path, **arguments)


def test_success_only_leaves_one_media_and_repeated_job_reuses_it(tmp_path):
    source = tmp_path/'source.png'
    fixture(source)
    out = tmp_path/'out'
    first = Engine().optimize(source, out)
    assert first.status == 'optimized', first.message
    assert first.report is None
    assert list(out.iterdir()) == [Path(first.output)]
    second = Engine().optimize(source, out)
    assert second.status == 'optimized', second.message
    assert second.output == first.output
    assert list(out.iterdir()) == [Path(first.output)]


def test_failure_and_cancel_leave_no_junk(tmp_path):
    source = tmp_path/'broken.png'
    source.write_bytes(b'not an image')
    out = tmp_path/'out'
    failed = Engine().optimize(source, out)
    assert failed.status == 'failed' and failed.report is None
    assert list(out.iterdir()) == []
    cancel = threading.Event()
    cancel.set()
    cancelled = Engine(cancel=cancel).optimize(source, out)
    assert cancelled.status == 'cancelled' and cancelled.report is None
    assert list(out.iterdir()) == []


def test_small_webp_preserves_alpha_icc_exif_xmp_and_archives_text(tmp_path):
    source = tmp_path/'alpha.png'
    fixture(source, alpha=True, metadata=True)
    before = sha256(source)
    result = Engine(Options(photo_mode='small', photo_format='webp', photo_target_kb=32)).optimize(source, tmp_path/'out')
    assert result.status == 'optimized', result.message
    assert result.details['selected']['ssimulacra2'] >= MIN_SSIMULACRA2
    assert result.details['lossless'] is False
    assert sha256(source) == before
    with Image.open(source) as a, Image.open(result.output) as b:
        assert a.size == b.size
        assert a.getchannel('A').tobytes() == b.getchannel('A').tobytes()
        assert a.info['icc_profile'] == b.info['icc_profile']
        assert a.getexif().tobytes() == b.getexif().tobytes()
        assert a.info['XML:com.adobe.xmp'].encode('utf-8') == b.info['xmp']
    archive = stored_extra_metadata(Path(result.output))
    assert len(archive) == 1 and archive[0][0] == b'LRXM'
    assert archive[0][1].startswith(b'LRXe8\x01')
    chunks = json.loads(zlib.decompress(archive[0][1][6:]))['chunks']
    assert ['tEXt', b'Description\x00T\xfcrk\xe7e \xf6zel metadata'.hex()] in chunks
    assert list((tmp_path/'out').iterdir()) == [Path(result.output)]


def test_small_avif_preserves_dimensions_and_private_metadata_bytes(tmp_path):
    source = tmp_path/'private.png'
    fixture(source)
    chunks = list(png_chunks(source))
    with source.open('wb') as stream:
        stream.write(b'\x89PNG\r\n\x1a\n')
        for kind, data in chunks:
            write_chunk(stream, kind, data)
            if kind == b'IHDR':
                write_chunk(stream, b'caBX', b'source provenance bytes: \x00\x01\x02')
    result = Engine(Options(photo_mode='small', photo_format='avif', photo_target_kb=32)).optimize(source, tmp_path/'out')
    assert result.status == 'optimized', result.message
    assert Path(result.output).suffix == '.avif'
    with Image.open(result.output) as output:
        assert output.size == (192, 128)
    blob = stored_extra_metadata(Path(result.output))[0][1]
    archived = json.loads(zlib.decompress(blob[6:]))
    assert archived['chunks'] == [['caBX', b'source provenance bytes: \x00\x01\x02'.hex()]]
    assert result.details['selected']['ssimulacra2'] >= MIN_SSIMULACRA2


def test_target_is_not_claimed_when_quality_needs_more_bytes(tmp_path):
    source = tmp_path/'noise.png'
    rng = random.Random(140)
    image = Image.new('RGB', (420, 420))
    image.putdata([(value, value, value) for value in (rng.randrange(256) for _ in range(420*420))])
    image.save(source, compress_level=0)
    result = Engine(Options(photo_mode='small', photo_format='avif', photo_target_kb=32)).optimize(source, tmp_path/'out')
    assert result.status == 'optimized', result.message
    assert result.output_bytes > 32*1024
    assert result.details['target_met'] is False
    assert result.details['selected']['ssimulacra2'] >= MIN_SSIMULACRA2
    assert 'görsel kalite için aşıldı' in result.message


def test_high_depth_photo_is_never_downcast_by_small_mode(tmp_path):
    source = tmp_path/'16bit.png'
    Image.frombytes('I;16', (64, 32), b'\x34\x12'*(64*32)).save(source)
    result = Engine(Options(photo_mode='small')).optimize(source, tmp_path/'out')
    assert result.status == 'kept', result.message
    assert result.output is None
    assert list((tmp_path/'out').iterdir()) == []


def test_refiltering_beats_an_already_deflated_bad_png_filter(tmp_path):
    source = tmp_path/'bad-filter.png'
    width, height = 320, 180
    raw = b''.join(b'\x00'+bytes(value for x in range(width) for value in (x%256,y%256,(x+y)%256)) for y in range(height))
    with source.open('wb') as stream:
        stream.write(b'\x89PNG\r\n\x1a\n')
        write_chunk(stream,b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))
        write_chunk(stream,b'IDAT',zlib.compress(raw,9))
        write_chunk(stream,b'IEND',b'')
    result = Engine().optimize(source,tmp_path/'out')
    assert result.status == 'optimized',result.message
    assert result.output_bytes < source.stat().st_size/2
    assert pixel_signature(source,threading.Event()) == pixel_signature(Path(result.output),threading.Event())
