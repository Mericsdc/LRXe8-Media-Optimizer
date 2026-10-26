"""Restore native MOV/MP4 creation/modification dates without remuxing media."""
from pathlib import Path
import struct

from .core import MediaError


def boxes(stream, start, end):
    position = start
    while position < end:
        stream.seek(position)
        header = stream.read(8)
        if len(header) != 8:
            raise MediaError('MOV metadata kutusu eksik')
        size, kind = struct.unpack('>I4s', header)
        length = 8
        if size == 1:
            value = stream.read(8)
            if len(value) != 8:
                raise MediaError('MOV genişletilmiş kutu eksik')
            size, length = int.from_bytes(value, 'big'), 16
        elif size == 0:
            size = end-position
        if size < length or position+size > end:
            raise MediaError('MOV metadata kutusu sınır dışında')
        yield kind, position+length, position+size
        position += size


def date_fields(path: Path):
    fields = {}
    handlers = []
    with path.open('rb') as stream:
        moov = next((box for box in boxes(stream, 0, path.stat().st_size) if box[0] == b'moov'), None)
        if moov is None:
            raise MediaError('MOV moov metadata alanı bulunamadı')
        children = list(boxes(stream, moov[1], moov[2]))

        def dates(box, key):
            _, payload, end = box
            stream.seek(payload)
            version = stream.read(1)
            if version not in (b'\x00', b'\x01'):
                raise MediaError('MOV tarih alanı sürümü desteklenmiyor')
            width = 8 if version == b'\x01' else 4
            position = payload+4
            if position+2*width > end:
                raise MediaError('MOV tarih alanı kesilmiş')
            stream.seek(position)
            fields[key] = (position, width, int.from_bytes(stream.read(width), 'big'),
                           int.from_bytes(stream.read(width), 'big'))

        movie = next((box for box in children if box[0] == b'mvhd'), None)
        if movie is None:
            raise MediaError('MOV movie header eksik')
        dates(movie, ('movie', 'mvhd'))
        for index, track in enumerate(box for box in children if box[0] == b'trak'):
            track_boxes = list(boxes(stream, track[1], track[2]))
            tkhd = next((box for box in track_boxes if box[0] == b'tkhd'), None)
            mdia = next((box for box in track_boxes if box[0] == b'mdia'), None)
            if tkhd is None or mdia is None:
                raise MediaError('MOV track header eksik')
            media = list(boxes(stream, mdia[1], mdia[2]))
            mdhd = next((box for box in media if box[0] == b'mdhd'), None)
            hdlr = next((box for box in media if box[0] == b'hdlr'), None)
            if mdhd is None or hdlr is None or hdlr[1]+12 > hdlr[2]:
                raise MediaError('MOV media header eksik')
            stream.seek(hdlr[1]+8)
            handlers.append(stream.read(4))
            dates(tkhd, (index, 'tkhd'))
            dates(mdhd, (index, 'mdhd'))
    return tuple(handlers), fields


def preserve_native_dates(source: Path, output: Path):
    source_handlers, original = date_fields(source)
    output_handlers, encoded = date_fields(output)
    if source_handlers != output_handlers or original.keys() != encoded.keys():
        raise MediaError('MOV tarih aktarımında akış eşleştirmesi doğrulanamadı')
    patches = []
    for key, (_, _, created, modified) in original.items():
        position, width, _, _ = encoded[key]
        if max(created, modified) >= 1 << (8*width):
            raise MediaError('MOV tarih değeri çıktı alanına kayıpsız aktarılamıyor')
        patches.append((position, created.to_bytes(width, 'big')+modified.to_bytes(width, 'big')))
    # Fixed-width writes only: media bytes, offsets, sizes, track IDs and timing
    # fields are untouched. Complete stream/pixel/timing checks still run next.
    with output.open('r+b') as stream:
        for position, value in patches:
            stream.seek(position)
            stream.write(value)
