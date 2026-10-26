"""Explicit opt-in "visually lossless" photo compression.

Pixels may change, but every candidate is scored with SSIMULACRA2 against the
original at native resolution and is accepted only at >= 90 ("visually
lossless" on the SSIMULACRA2 scale). The size target is a wish, never a reason
to go below that floor. Default photo paths stay strictly lossless.
"""
from __future__ import annotations

from pathlib import Path
import io
import json
import re
import struct
import threading
import zlib

from PIL import Image

from .core import Cancelled, MediaError, Options, find_tool, run

MIN_SSIMULACRA2 = 90.0
META_UUID = b'LRXe8-META-v1___'
LIMITS = {'AVIF': 65535, 'WEBP': 16383, 'JPEG': 65500}


def metadata_for_webp(source: Path, image):
    """Copy standard metadata natively; archive format-specific bytes in-file."""
    from .photos import png_chunks, jpeg_metadata, webp_metadata
    info = dict(image.info)
    archived = []
    extras = []
    if image.format == 'PNG':
        for kind, data in png_chunks(source):
            if kind in {b'IHDR', b'IDAT', b'IEND', b'PLTE', b'tRNS', b'iCCP', b'eXIf'}:
                continue
            if kind == b'iTXt' and data.startswith(b'XML:com.adobe.xmp\x00'):
                continue
            if kind == b'cICP' or (kind in {b'gAMA', b'cHRM'} and not info.get('icc_profile')):
                raise MediaError('PNG özel renk/gamma özellikleri için bu dönüşüm doğrulanamıyor')
            archived.append((kind.decode('ascii'), data.hex()))
        # Explicit non-sRGB chromaticity/transfer information is never discarded.
        if 'XML:com.adobe.xmp' in info:
            info['xmp'] = info['XML:com.adobe.xmp'].encode('utf-8')
    elif image.format == 'JPEG':
        for marker, value in jpeg_metadata(source):
            data = bytes.fromhex(value)
            if marker == 'e0' and data.startswith(b'JFIF\x00'):
                archived.append((marker, value))
                continue
            if marker == 'e1' and data.startswith((b'Exif\x00\x00', b'http://ns.adobe.com/xap/1.0/\x00')):
                if b'hdrgm:' in data or b'GainMap' in data:
                    raise MediaError('HDR/gain-map JPEG küçük dosya modunda dönüştürülmedi')
                if data.startswith(b'http://ns.adobe.com/xap/1.0/\x00'):
                    info['xmp'] = data.split(b'\x00', 1)[1]
                continue
            if marker == 'e2' and data.startswith(b'ICC_PROFILE\x00'):
                continue
            if data.startswith(b'MPF\x00'):
                raise MediaError('MPO/gain-map JPEG küçük dosya modunda dönüştürülmedi')
            archived.append((marker, value))
    elif image.format == 'WEBP':
        extras = [(key.encode('ascii'), bytes.fromhex(value)) for key, value in webp_metadata(source)
                  if key not in {'ICCP', 'EXIF', 'XMP '}]
    else:
        raise MediaError('Küçük dosya modu bu sürümde 8 bit SDR PNG, JPEG ve WebP içindir')
    if archived:
        payload = json.dumps({'source_format': image.format, 'chunks': archived}, separators=(',', ':')).encode('utf-8')
        extras.append((b'LRXM', b'LRXe8\x01' + zlib.compress(payload, 9)))
    return {key: info[key] for key in ('icc_profile', 'exif', 'xmp') if info.get(key)}, extras


def append_metadata_chunks(path: Path, chunks, dimensions):
    if not chunks:
        return
    data = path.read_bytes()
    if path.suffix.lower() == '.avif':
        payload = zlib.compress(json.dumps([(key.hex(), value.hex()) for key, value in chunks],
                                          separators=(',', ':')).encode('utf-8'), 9)
        box = struct.pack('>I', 24 + len(payload)) + b'uuid' + META_UUID + payload
        path.write_bytes(data + box)
        return
    if data[:4] != b'RIFF' or data[8:12] != b'WEBP' or int.from_bytes(data[4:8], 'little') + 8 != len(data):
        raise MediaError('WebP kapsayıcısı doğrulanamadı')
    if data[12:16] != b'VP8X':
        width, height = dimensions
        header = bytes(4) + (width-1).to_bytes(3, 'little') + (height-1).to_bytes(3, 'little')
        data = data[:12] + b'VP8X' + struct.pack('<I', 10) + header + data[12:]
    for kind, payload in chunks:
        data += kind + struct.pack('<I', len(payload)) + payload + (b'\x00' if len(payload) % 2 else b'')
    data = data[:4] + struct.pack('<I', len(data)-8) + data[8:]
    path.write_bytes(data)


def stored_extra_metadata(path: Path):
    if path.suffix.lower() == '.avif':
        data = path.read_bytes()
        offset = 0
        found = []
        while offset < len(data):
            size, kind = struct.unpack('>I4s', data[offset:offset+8])
            if size < 8 or offset + size > len(data):
                raise MediaError('Geçersiz AVIF metadata kutusu')
            if kind == b'uuid' and data[offset+8:offset+24] == META_UUID:
                rows = json.loads(zlib.decompress(data[offset+24:offset+size]))
                found.extend((bytes.fromhex(key), bytes.fromhex(value)) for key, value in rows)
            offset += size
        return sorted(found)
    if path.suffix.lower() in {'.jpg', '.jpeg'}:
        return []
    from .photos import webp_metadata
    return [(key.encode('ascii'), bytes.fromhex(value)) for key, value in webp_metadata(path)
            if key not in {'ICCP', 'EXIF', 'XMP '}]


def transplant_jpeg_markers(source: Path, encoded: bytes) -> bytes:
    """JPEG -> JPEG: put every original APPn/COM segment, byte for byte and in
    order, in front of the new image data (whose own APP/COM segments are dropped)."""
    def segments(data: bytes):
        if data[:2] != b'\xff\xd8':
            raise MediaError('Geçersiz JPEG')
        position, meta = 2, []
        while position + 4 <= len(data) and data[position] == 0xFF:
            marker = data[position + 1]
            if marker in (0xDA, 0xD9):
                break
            length = int.from_bytes(data[position + 2:position + 4], 'big')
            if length < 2 or position + 2 + length > len(data):
                raise MediaError('Kesilmiş JPEG segmenti')
            meta.append((marker, data[position:position + 2 + length]))
            position += 2 + length
        return meta, position
    from .photos import jpeg_metadata
    # All APPn/COM segments of the source, including any between progressive scans.
    kept = []
    for marker, value in jpeg_metadata(source):
        payload = bytes.fromhex(value)
        kept.append(b'\xff' + bytes.fromhex(marker) + (len(payload) + 2).to_bytes(2, 'big') + payload)
    new, _ = segments(encoded)
    body = b''.join(raw for marker, raw in new if not (0xE0 <= marker <= 0xEF or marker == 0xFE))
    _, image_start = segments(encoded)
    return b'\xff\xd8' + b''.join(kept) + body + encoded[image_start:]


def ssimulacra2(reference_png: Path, candidate: Path, work: Path, cancel) -> float:
    tool = find_tool('ssimulacra2', required=False)
    if not tool:
        raise MediaError('SSIMULACRA2 aracı bulunamadı; görsel kalite doğrulanamaz')
    decoded = work / 'candidate-decoded.png'
    with Image.open(candidate) as image:
        image.load()
        mode = 'RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB'
        image.convert(mode).save(decoded, compress_level=1)
    text = run([tool, str(reference_png), str(decoded)], cancel, timeout=600)
    decoded.unlink(missing_ok=True)
    match = re.search(r'(-?\d+(?:\.\d+)?)', text.strip())
    if not match:
        raise MediaError('SSIMULACRA2 sonucu okunamadı')
    return float(match[1])


def optimize_small(source: Path, work: Path, cancel: threading.Event, notify, options: Options):
    target = options.photo_target_kb * 1024
    details = {'photo_mode': 'small', 'lossless': False, 'target_bytes': target,
               'policy': f'Görsel kayıpsız: SSIMULACRA2 >= {MIN_SSIMULACRA2:g}, aynı çözünürlük, birebir alpha ve metadata'}
    notify(f'Görsel kayıpsız küçültme analizi · hedef {options.photo_target_kb} KB')
    if not find_tool('ssimulacra2', required=False):
        return None, {}, {**details, 'reason': 'Görsel kalite ölçüm aracı (ssimulacra2) bu kurulumda yok; '
                                               'kalite doğrulanamayacağı için küçültülmedi, orijinal korundu.'}
    with Image.open(source) as original:
        original.load()
        details.update(format=original.format, dimensions=original.size)
        if (getattr(original, 'n_frames', 1) != 1 or getattr(original, 'is_animated', False)
                or original.mode not in {'RGB', 'RGBA', 'L', 'LA', 'P'}):
            return None, {}, {**details, 'reason': 'Bu örnek biçimi/animasyon için küçük dosya modu uygulanmadı; orijinal korundu.'}
        if original.mode in {'L', 'LA'} and original.info.get('icc_profile'):
            return None, {}, {**details, 'reason': 'Gri renk profili için küçük dosya dönüşümü doğrulanmadı; orijinal korundu.'}
        try:
            metadata, extras = metadata_for_webp(source, original)
        except MediaError as error:
            return None, {}, {**details, 'reason': str(error) + '; orijinal korundu.'}
        rgba = original.convert('RGBA')
        source_alpha = rgba.getchannel('A').tobytes()
        has_alpha = (original.mode in {'RGBA', 'LA'} or 'transparency' in original.info) and rgba.getchannel('A').getextrema() != (255, 255)
        image = rgba if has_alpha else original.convert('RGB')
        reference = work / 'reference.png'
        image.save(reference, compress_level=1)
        size_ok = lambda fmt: max(original.size) <= LIMITS[fmt]
        allowed = {
            'AVIF': not has_alpha and not metadata.get('exif') and size_ok('AVIF'),
            'WEBP': size_ok('WEBP'),
            'JPEG': not has_alpha and size_ok('JPEG') and (original.format == 'JPEG' or not extras),
        }
        wanted = {'auto': ['AVIF', 'JPEG', 'WEBP'], 'avif': ['AVIF'], 'webp': ['WEBP'], 'jpeg': ['JPEG']}[options.photo_format]
        formats = [fmt for fmt in wanted if allowed[fmt]]
        if not formats:
            return None, {}, {**details, 'reason': 'Seçilen biçim bu içeriğin alpha/EXIF/metadata/boyut özelliklerini birebir koruyamıyor; '
                                                   'otomatik veya WebP seçin. Orijinal korundu.'}
        details['archived_metadata_chunks'] = [key.decode('ascii') for key, _ in extras]
        if extras:
            details['archive_note'] = 'Format-specific metadata preserved in-file; original signatures describe the source, not this edited image.'
        attempts = []
        results = {}

        def encode(fmt, quality):
            key = (fmt, quality)
            if key in results:
                return results[key]
            if cancel.is_set():
                raise Cancelled('İptal edildi')
            notify(f'{fmt} kalite {quality} deneniyor · görsel kalite eşiği SSIMULACRA2 {MIN_SSIMULACRA2:g}')
            candidate = work / f'photo-{fmt.lower()}-q{quality}.{"jpg" if fmt == "JPEG" else fmt.lower()}'
            if fmt == 'AVIF':
                image.save(candidate, format='AVIF', quality=quality, subsampling='4:4:4', speed=6, max_threads=8, **metadata)
            elif fmt == 'WEBP':
                image.save(candidate, format='WEBP', quality=quality, method=6, lossless=False, exact=True,
                           alpha_quality=100, use_sharp_yuv=True, **metadata)
            else:
                buffer = io.BytesIO()
                image.save(buffer, format='JPEG', quality=quality, subsampling=0, optimize=True, progressive=True,
                           **({} if original.format == 'JPEG' else metadata))
                data = buffer.getvalue()
                try:
                    import mozjpeg_lossless_optimization as mozjpeg
                    data = mozjpeg.optimize(data, copy=mozjpeg.COPY_MARKERS.ALL)
                except (ImportError, ValueError):
                    pass
                candidate.write_bytes(transplant_jpeg_markers(source, data) if original.format == 'JPEG' else data)
            if fmt != 'JPEG':
                append_metadata_chunks(candidate, extras, original.size)
                if stored_extra_metadata(candidate) != sorted(extras):
                    raise MediaError('Fotoğrafın özel metadata verisi korunmadı')
            with Image.open(candidate) as output:
                output.load()
                if output.size != original.size:
                    raise MediaError('Fotoğraf çözünürlüğü değişti')
                if output.convert('RGBA').getchannel('A').tobytes() != source_alpha:
                    raise MediaError('Fotoğraf alpha değerleri değişti')
                if fmt == 'JPEG' and original.format == 'JPEG':
                    from .photos import jpeg_metadata
                    if jpeg_metadata(candidate) != jpeg_metadata(source):
                        raise MediaError('JPEG metadata segmentleri korunmadı')
                else:
                    for name, value in metadata.items():
                        actual = output.info.get(name)
                        # WebP EXIF is a TIFF payload; Pillow may add/remove Exif\0\0.
                        if name == 'exif':
                            value = value.removeprefix(b'Exif\x00\x00')
                            actual = actual.removeprefix(b'Exif\x00\x00') if isinstance(actual, bytes) else actual
                        if actual != value:
                            raise MediaError(f'Fotoğraf metadata korunmadı: {name}')
            score = ssimulacra2(reference, candidate, work, cancel)
            record = {'format': fmt, 'quality': quality, 'bytes': candidate.stat().st_size,
                      'ssimulacra2': round(score, 3), 'quality_passed': score >= MIN_SSIMULACRA2}
            attempts.append(record)
            results[key] = (candidate, record)
            return results[key]

        best = []
        for fmt in formats:
            try:
                # Lowest quality setting that is still visually lossless = smallest
                # acceptable file. Scores rise with the quality setting.
                low, high, passing = 40, 100, None
                while low <= high:
                    middle = (low + high) // 2
                    _, record = encode(fmt, middle)
                    if record['quality_passed']:
                        passing, high = middle, middle - 1
                    else:
                        low = middle + 1
                if passing is None:
                    continue
                fitting = passing if results[(fmt, passing)][1]['bytes'] <= target else None
                if fitting is not None:
                    # Spend the remaining size budget on extra quality.
                    low, high = passing + 1, 100
                    while low <= high:
                        middle = (low + high) // 2
                        _, record = encode(fmt, middle)
                        if record['bytes'] <= target and record['quality_passed']:
                            fitting, low = middle, middle + 1
                        else:
                            high = middle - 1
                best.append(results[(fmt, fitting if fitting is not None else passing)])
                if options.photo_format == 'auto':
                    # AVIF > JPEG 4:4:4 > WebP (4:2:0) for visually lossless photos;
                    # later formats are only fallbacks when the earlier one cannot apply.
                    break
            except Cancelled:
                raise
            except (MediaError, OSError, ValueError) as error:
                attempts.append({'format': fmt, 'error': str(error)})
        details.update(attempts=attempts, minimum_ssimulacra2=MIN_SSIMULACRA2)
        if not best:
            return None, {}, {**details, 'reason': 'Görsel kayıpsız kalite (SSIMULACRA2 ≥ 90) bu biçimlerde sağlanamadı; orijinal korundu.'}
        fitting = [item for item in best if item[1]['bytes'] <= target]
        candidate, record = (max(fitting, key=lambda item: item[1]['ssimulacra2']) if fitting
                             else min(best, key=lambda item: item[1]['bytes']))
        details.update(selected=record, target_met=record['bytes'] <= target, output_format=record['format'])
        return candidate, {'dimensions': True, 'alpha_exact': True, 'metadata_exact': True,
                           'visually_lossless': True}, details
