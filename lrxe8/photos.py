"""Strictly lossless photo paths; no lossy fallback and no size requirement."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import struct
import threading
import zlib

from PIL import Image, ImageSequence
import pillow_heif

from .core import MediaError, Cancelled, Options, find_tool, run

pillow_heif.register_heif_opener()
# Local tool with its own RAM budget: very large panoramas/scans are legitimate
# input, not decompression bombs.
Image.MAX_IMAGE_PIXELS = None
LAYOUT_CHUNKS = {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS'}
# Chunks that change how pixels look or print; always kept, even when the user
# asks to remove invisible metadata (camera data, text, XMP, C2PA, thumbnails).
VISUAL_CHUNKS = {b'iCCP', b'sRGB', b'gAMA', b'cHRM', b'cICP', b'mDCV', b'cLLI', b'pHYs'}


def png_chunks(path: Path):
    with path.open('rb') as stream:
        if stream.read(8) != b'\x89PNG\r\n\x1a\n':
            raise MediaError('Geçersiz PNG imzası')
        while header := stream.read(8):
            if len(header) != 8:
                raise MediaError('Kesilmiş PNG')
            size, kind = struct.unpack('>I4s', header)
            if size > 512 * 1024**2:
                raise MediaError('PNG parçası güvenli bellek sınırını aşıyor')
            data, crc = stream.read(size), stream.read(4)
            if len(data) != size or len(crc) != 4 or zlib.crc32(kind + data) != struct.unpack('>I', crc)[0]:
                raise MediaError('PNG CRC doğrulaması başarısız')
            yield kind, data
            if kind == b'IEND':
                if stream.read(1):
                    raise MediaError('PNG sonunda tanımlanmamış veri var; koruma gerekiyor')
                return
        raise MediaError('PNG IEND eksik')


def write_chunk(stream, kind, data):
    stream.write(struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data)))


def canonical_rgba(path: Path, cancel: threading.Event):
    """8-bit PNG pixels as straight RGBA, independent of colour type/palette/bit depth."""
    if cancel.is_set():
        raise Cancelled('İptal edildi')
    with Image.open(path) as image:
        image.load()
        return image.size, hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest()


def oxipng_run(source: Path, dest: Path, raw_bytes: int, cancel: threading.Event, reductions: bool, keep_gray: bool,
               strip: bool = False):
    optimizer = find_tool('oxipng', required=False)
    if not optimizer:
        return None
    # Exhaustive filter search for normal photos; a lighter preset keeps huge
    # scans/panoramas (>64 MB of pixels) from running for many minutes.
    level = 'max' if raw_bytes <= 64 * 1024**2 else '3'
    args = [optimizer, '-o', level, '--interlace', 'keep', '--force', '-q', '--threads', '8']
    if strip:
        args += ['--keep', ','.join(sorted(kind.decode('ascii') for kind in VISUAL_CHUNKS))]
    if not reductions:
        args += ['--nx']
    elif keep_gray:
        args += ['--ng']
    # Zopfli adds ~0.3-1 % for 10x time; worth it only for small images.
    if raw_bytes <= 1536 * 1024:
        args += ['-z', '--zi', '15', '--ziwi', '5']
    seconds = 60 + raw_bytes / 1024**2 * 3
    run(args + ['--timeout', str(int(seconds)), '--out', str(dest), str(source)], cancel, timeout=seconds * 2 + 60)
    return dest


def png_kept_metadata(chunks, strip: bool):
    return [(kind, data) for kind, data in chunks
            if kind not in LAYOUT_CHUNKS and (not strip or kind in VISUAL_CHUNKS)]


def optimize_png(source: Path, dest: Path, cancel: threading.Event, strip: bool = False):
    """Returns the method used. Ancillary chunks (ICC, EXIF, XMP, text, private,
    C2PA) stay byte-identical; with strip=True only colour/print chunks are kept.
    Decoded pixels are verified by the caller."""
    chunks = list(png_chunks(source))
    if any(kind in {b'acTL', b'fdAT'} for kind, _ in chunks):
        raise MediaError('Animasyonlu PNG için mevcut kayıpsız yol etkin değil; orijinal korundu')
    width, height, depth, color = struct.unpack('>IIBB', chunks[0][1][:10])
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if not channels:
        raise MediaError('Bilinmeyen PNG renk biçimi')
    # Adam7 overhead is bounded by an extra filter byte for each sub-row.
    limit = (width * channels * depth // 8 + 16) * height + 1024
    if limit > 4 * 1024**3:
        raise MediaError('Bu PNG için kayıpsız yeniden sıkıştırma bellek sınırını aşıyor')
    metadata = png_kept_metadata(chunks, strip)
    best_file, method = None, None
    # 1) ImageOptim-style: let oxipng also apply lossless colour-type/bit-depth/
    #    palette reductions (e.g. fully opaque RGBA -> RGB). Accepted only when
    #    every metadata chunk survives byte-identical and RGBA pixels are equal.
    reduced = dest.with_name('reduced.png')
    if depth <= 8:
        trial = dest.with_name('oxipng-reduced.png')
        try:
            if oxipng_run(source, trial, limit, cancel, True, any(k in {b'iCCP', b'cICP'} for k, _ in chunks)):
                layout = [(kind, data) for kind, data in png_chunks(trial) if kind in LAYOUT_CHUNKS]
                # Only the pixel layout (IHDR/PLTE/tRNS/IDAT) is taken from oxipng; every
                # metadata chunk is written back byte-for-byte from the source, in order.
                # bKGD/sBIT/hIST depend on the colour type and would become invalid.
                changed = layout[0] != chunks[0]
                if not (changed and any(kind in {b'bKGD', b'sBIT', b'hIST'} for kind, _ in metadata)):
                    first_idat = next(i for i, (kind, _) in enumerate(chunks) if kind == b'IDAT')
                    before = [chunk for chunk in chunks[:first_idat] if chunk in metadata]
                    after = [chunk for chunk in chunks[first_idat:] if chunk in metadata]
                    idat = b''.join(data for kind, data in layout if kind == b'IDAT')
                    palette = [chunk for chunk in layout if chunk[0] in {b'PLTE', b'tRNS'}]
                    with reduced.open('wb') as stream:
                        stream.write(b'\x89PNG\r\n\x1a\n')
                        for kind, data in [layout[0], *before, *palette, (b'IDAT', idat), *after, (b'IEND', b'')]:
                            write_chunk(stream, kind, data)
                    if canonical_rgba(reduced, cancel) == canonical_rgba(source, cancel):
                        best_file, method = reduced, 'oxipng reductions + filters'
        except Cancelled:
            raise
        except (MediaError, OSError, StopIteration):
            pass
        finally:
            trial.unlink(missing_ok=True)
    # 2) Layout-preserving: identical IHDR/PLTE/tRNS, only the IDAT stream is
    #    rebuilt (zlib strategies or oxipng --nx), every other chunk is copied.
    compressed = b''.join(data for kind, data in chunks if kind == b'IDAT')
    decoder = zlib.decompressobj()
    raw = decoder.decompress(compressed, limit + 1)
    if len(raw) > limit or not decoder.eof or decoder.unused_data:
        raise MediaError('PNG açılım boyutu veya sıkıştırılmış veri geçersiz')
    best = compressed
    for strategy in (zlib.Z_DEFAULT_STRATEGY, zlib.Z_FILTERED, zlib.Z_RLE):
        if cancel.is_set():
            raise Cancelled('İptal edildi')
        compressor = zlib.compressobj(9, zlib.DEFLATED, 15, 9, strategy)
        candidate = compressor.compress(raw) + compressor.flush()
        if len(candidate) < len(best):
            best = candidate
    del raw
    refiltered = dest.with_name('refiltered.png')
    try:
        if oxipng_run(source, refiltered, limit, cancel, False, False):
            optimized = list(png_chunks(refiltered))
            if optimized[0] != chunks[0]:
                raise MediaError('PNG örnek biçimi değişti; güçlü aday kullanılmadı')
            encoded = b''.join(data for kind, data in optimized if kind == b'IDAT')
            if len(encoded) < len(best):
                best = encoded
    except Cancelled:
        raise
    except MediaError:
        # The original byte-preserving zlib candidate remains a safe fallback.
        pass
    finally:
        refiltered.unlink(missing_ok=True)
    layout = dest.with_name('layout.png')
    with layout.open('wb') as stream:
        stream.write(b'\x89PNG\r\n\x1a\n')
        written = False
        for kind, data in chunks:
            if kind == b'IDAT':
                if not written:
                    write_chunk(stream, kind, best)
                    written = True
            elif kind in LAYOUT_CHUNKS or (kind, data) in metadata:
                write_chunk(stream, kind, data)
    if best_file is None or layout.stat().st_size <= best_file.stat().st_size:
        best_file, method = layout, 'same layout, recompressed IDAT'
    shutil.copyfile(best_file, dest)
    reduced.unlink(missing_ok=True)
    layout.unlink(missing_ok=True)
    return method


def jpeg_metadata(path: Path):
    """Every APPn/COM segment in file order, including those between progressive
    scans (jpegtran/MozJPEG legitimately move those in front of the first scan)."""
    data = path.read_bytes()
    if data[:2] != b'\xff\xd8':
        raise MediaError('Geçersiz JPEG')
    records = []
    position, size = 2, len(data)
    while position < size:
        if data[position] != 0xFF:
            raise MediaError('Geçersiz JPEG işaretçisi')
        while position < size and data[position] == 0xFF:
            position += 1
        if position >= size:
            raise MediaError('Kesilmiş JPEG')
        marker = data[position]
        position += 1
        if marker == 0xD9:
            return records
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        if position + 2 > size:
            raise MediaError('Kesilmiş JPEG')
        length = int.from_bytes(data[position:position + 2], 'big')
        if length < 2 or position + length > size:
            raise MediaError('Geçersiz JPEG uzunluğu')
        if 0xE0 <= marker <= 0xEF or marker == 0xFE:
            records.append((f'{marker:02x}', data[position + 2:position + length].hex()))
        position += length
        if marker == 0xDA:
            # Skip entropy-coded data: stuffed 0xFF00 and restart markers belong to it.
            while position < size - 1:
                if data[position] == 0xFF and data[position + 1] != 0 and not 0xD0 <= data[position + 1] <= 0xD7:
                    break
                position += 1
            else:
                raise MediaError('Kesilmiş JPEG (EOI eksik)')
    raise MediaError('Kesilmiş JPEG (EOI eksik)')


def jpeg_visual_metadata(path: Path):
    """ICC profile bytes and EXIF orientation: the metadata that changes how a JPEG looks."""
    icc = b''.join(bytes.fromhex(value)[14:] for marker, value in jpeg_metadata(path)
                   if marker == 'e2' and bytes.fromhex(value).startswith(b'ICC_PROFILE\x00'))
    with Image.open(path) as image:
        orientation = image.getexif().get(0x0112, 1)
    return [('icc', icc.hex()), ('orientation', str(orientation))]


def add_orientation(source: Path, target: Path):
    """After stripping, re-add a minimal EXIF block that carries only the orientation."""
    with Image.open(source) as image:
        orientation = image.getexif().get(0x0112, 1)
    if orientation in (None, 1):
        return
    exif = Image.Exif()
    exif[0x0112] = orientation
    payload = exif.tobytes()
    if not payload.startswith(b'Exif\x00\x00'):
        payload = b'Exif\x00\x00' + payload
    data = target.read_bytes()
    position = 2
    if data[2:4] == b'\xff\xe0':
        position += 2 + int.from_bytes(data[4:6], 'big')
    segment = b'\xff\xe1' + (len(payload) + 2).to_bytes(2, 'big') + payload
    target.write_bytes(data[:position] + segment + data[position:])


def webp_metadata(path: Path):
    records = []
    with path.open('rb') as stream:
        header = stream.read(12)
        if header[:4] != b'RIFF' or header[8:] != b'WEBP':
            raise MediaError('Geçersiz WebP')
        while chunk := stream.read(8):
            if len(chunk) != 8:
                raise MediaError('Kesilmiş WebP')
            kind, size = chunk[:4], int.from_bytes(chunk[4:], 'little')
            if size > 512 * 1024**2:
                raise MediaError('WebP parçası çok büyük')
            data = stream.read(size)
            if len(data) != size:
                raise MediaError('Kesilmiş WebP')
            if size % 2:
                stream.read(1)
            if kind not in {b'VP8 ', b'VP8L', b'VP8X', b'ALPH'}:
                records.append((kind.decode('ascii', 'replace'), data.hex()))
    return sorted(records)


def pixel_signature(path: Path, cancel: threading.Event):
    signatures = []
    with Image.open(path) as image:
        for frame in ImageSequence.Iterator(image):
            if cancel.is_set():
                raise Cancelled('İptal edildi')
            frame.load()
            # Same decoder, same sample representation, no color or depth conversion.
            digest = hashlib.sha256(frame.tobytes()).hexdigest()
            palette = frame.palette.tobytes().hex() if frame.palette else None
            signatures.append((frame.size, frame.mode, digest, palette))
    return signatures


def optimize_bmff_padding(source: Path, destination: Path, cancel: threading.Event):
    """Trim only trailing zero-filled free/skip boxes, preserving all offsets.

    Rebuilding HEIF/AVIF or re-encoding RGB can discard HDR, auxiliary images,
    native precision or private metadata. This byte-preserving path cannot.
    """
    size = source.stat().st_size
    boxes = []
    with source.open('rb') as stream:
        position = 0
        while position < size:
            stream.seek(position)
            header = stream.read(8)
            if len(header) != 8:
                raise MediaError('Kesilmiş HEIF/AVIF kutusu')
            length, kind = struct.unpack('>I4s', header)
            header_size = 8
            if length == 1:
                extended = stream.read(8)
                if len(extended) != 8:
                    raise MediaError('Geçersiz HEIF/AVIF genişletilmiş kutu')
                length = int.from_bytes(extended, 'big')
                header_size = 16
            elif length == 0:
                length = size - position
            if length < header_size or position + length > size:
                raise MediaError('Geçersiz HEIF/AVIF kutu uzunluğu')
            boxes.append((position, length, kind, header_size))
            position += length
        end = size
        for position, length, kind, header_size in reversed(boxes):
            if kind not in {b'free', b'skip'}:
                break
            stream.seek(position + header_size)
            remaining = length - header_size
            zeros = True
            while remaining:
                if cancel.is_set():
                    raise Cancelled('İptal edildi')
                block = stream.read(min(1024**2, remaining))
                if not block or any(block):
                    zeros = False
                    break
                remaining -= len(block)
            if not zeros:
                break
            end = position
        if end == size:
            return None
        stream.seek(0)
        digest = hashlib.sha256()
        with destination.open('wb') as output:
            remaining = end
            while remaining:
                if cancel.is_set():
                    raise Cancelled('İptal edildi')
                block = stream.read(min(1024**2, remaining))
                if not block:
                    raise MediaError('Kaynak okuma sırasında değişti')
                output.write(block)
                digest.update(block)
                remaining -= len(block)
    from .core import sha256
    if sha256(destination, cancel) != digest.hexdigest():
        raise MediaError('HEIF/AVIF içerik koruma doğrulaması başarısız')
    return end


def photo_optimize(source: Path, work: Path, cancel: threading.Event, notify, options: Options | None = None):
    options = options or Options()
    if options.photo_mode == 'small':
        from .photo_small import optimize_small
        return optimize_small(source, work, cancel, notify, options)
    notify('Kayıpsız fotoğraf analizi')
    with Image.open(source) as im:
        fmt, dimensions = im.format, im.size
        frames = getattr(im, 'n_frames', 1)
        info = dict(im.info)
    details = {'format': fmt, 'dimensions': dimensions, 'frames': frames,
               'policy': 'exact decoded pixels + metadata; no resize', 'photo_mode': 'lossless'}
    if fmt in {'HEIF', 'AVIF'}:
        candidate = work / ('candidate' + source.suffix.lower())
        retained = optimize_bmff_padding(source, candidate, cancel)
        if retained is None:
            return None, {}, {**details, 'reason': f'{fmt}: güvenle kaldırılabilecek son dolgu alanı yok; orijinal korundu.'}
        # The entire encoded image/alpha/metadata prefix is byte-identical,
        # including high-depth/HDR auxiliary items unavailable to Pillow RGB.
        equal = pixel_signature(source, cancel) == pixel_signature(candidate, cancel)
        if not equal:
            raise MediaError('HEIF/AVIF piksel doğrulaması başarısız')
        return candidate, {'dimensions': True, 'pixels_exact': True, 'alpha_exact': True,
                           'metadata_exact': True, 'encoded_payload_exact': True}, {
                           **details, 'method': 'Trailing zero-filled free/skip boxes only; all image bytes and offsets unchanged',
                           'retained_prefix_bytes': retained}
    if frames != 1:
        return None, {}, {**details, 'reason': 'Çok kareli fotoğraf/animasyon orijinal olarak korundu.'}
    candidate = work / ('candidate' + source.suffix.lower())
    if fmt == 'PNG':
        notify('Kayıpsız PNG: renk indirgeme, filtreler ve güçlü sıkıştırma deneniyor')
        details['method'] = optimize_png(source, candidate, cancel, options.strip_metadata)
        before_meta = png_kept_metadata(png_chunks(source), options.strip_metadata)
        after_meta = png_kept_metadata(png_chunks(candidate), False)
    elif fmt == 'JPEG':
        before_meta = jpeg_metadata(source)
        if any(bytes.fromhex(value).startswith(b'MPF\x00') for _, value in before_meta):
            return None, {}, {**details, 'reason': 'MPO/gain-map içeren JPEG bütünüyle korundu.'}
        jpegtran = find_tool('jpegtran', required=False)
        notify('Kayıpsız JPEG: Huffman/progressive tarama optimizasyonu (MozJPEG + jpegtran)')
        strip = options.strip_metadata
        if strip:
            # Keep what changes the picture: ICC colour profile and EXIF orientation.
            before_meta = jpeg_visual_metadata(source)
        copy = 'icc' if strip else 'all'
        if jpegtran:
            baseline = work / 'baseline.jpg'
            for target, flags in ((candidate, ['-progressive']), (baseline, [])):
                run([jpegtran, '-copy', copy, '-optimize', *flags, '-outfile', str(target), str(source)], cancel)
                if strip:
                    add_orientation(source, target)
            if baseline.stat().st_size < candidate.stat().st_size:
                shutil.copyfile(baseline, candidate)
            details['method'] = f'jpegtran -copy {copy} -optimize'
        else:
            # macOS builds may ship without jpegtran: MozJPEG alone does the job.
            shutil.copyfile(source, candidate)
            details['method'] = 'kaynak'
        try:
            import mozjpeg_lossless_optimization as mozjpeg
            optimized = mozjpeg.optimize(source.read_bytes(),
                                         copy=mozjpeg.COPY_MARKERS.ICC if strip else mozjpeg.COPY_MARKERS.ALL)
            mozfile = work / 'mozjpeg.jpg'
            mozfile.write_bytes(optimized)
            if strip:
                add_orientation(source, mozfile)
            current = jpeg_visual_metadata(mozfile) if strip else jpeg_metadata(mozfile)
            # MozJPEG must keep the selected APP/COM segments exactly, like jpegtran.
            if mozfile.stat().st_size < candidate.stat().st_size and current == before_meta:
                shutil.copyfile(mozfile, candidate)
                details['method'] = 'MozJPEG lossless' + (' (ICC + yön korunur)' if strip else ' (all markers copied)')
        except (ImportError, ValueError, MediaError):
            pass
        if details['method'] == 'kaynak':
            return None, {}, {**details, 'reason': 'JPEG kayıpsız optimize aracı (MozJPEG/jpegtran) bulunamadı; orijinal korundu.'}
        after_meta = jpeg_visual_metadata(candidate) if strip else jpeg_metadata(candidate)
    elif fmt == 'WEBP':
        before_meta = webp_metadata(source)
        if any(k not in {'ICCP', 'EXIF', 'XMP '} for k, _ in before_meta):
            return None, {}, {**details, 'reason': 'Özel WebP parçalarını korumak için orijinal tutuldu.'}
        with Image.open(source) as im:
            save_metadata = {k: info[k] for k in ('icc_profile', 'exif', 'xmp') if k in info}
            for effort in (100, 75):
                attempt = work / f'webp-{effort}.webp'
                im.save(attempt, format='WEBP', lossless=True, exact=True, quality=effort, method=6, **save_metadata)
                if not candidate.exists() or attempt.stat().st_size < candidate.stat().st_size:
                    shutil.copyfile(attempt, candidate)
        after_meta = webp_metadata(candidate)
    else:
        return None, {}, {**details, 'reason': f'{fmt}: doğrulanmış piksel ve metadata koruyan kayıpsız yeniden sıkıştırma yolu yok; orijinal korundu.'}
    notify('Pikseller, alpha ve metadata karşılaştırılıyor')
    if fmt == 'PNG' and details.get('method', '').startswith('oxipng reductions'):
        # Colour type/palette may legitimately change; compare decoded RGBA.
        pixels_equal = canonical_rgba(source, cancel) == canonical_rgba(candidate, cancel)
    else:
        pixels_equal = pixel_signature(source, cancel) == pixel_signature(candidate, cancel)
    checks = {'dimensions': True, 'pixels_exact': pixels_equal, 'alpha_exact': pixels_equal,
              'metadata_exact': before_meta == after_meta}
    if not all(checks.values()):
        raise MediaError('Fotoğraf doğrulaması başarısız: ' + str(checks))
    return candidate, checks, details
