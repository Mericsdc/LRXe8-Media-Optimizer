"""Plain-language status lines and progress estimates for the GUI.

The engine reports technical steps ("hevc_nvenc · CQ 22 örnek sahnelerde
deneniyor"); people need "En uygun kalite ayarı aranıyor". Technical text stays
available in the details window.
"""
from __future__ import annotations

import re

ENCODER_NAMES = {'av1_nvenc': 'AV1 · ekran kartı', 'hevc_nvenc': 'HEVC · ekran kartı',
                 'h264_nvenc': 'H.264 · ekran kartı', 'libsvtav1': 'AV1 · işlemci',
                 'libx265': 'HEVC · işlemci', 'libx264': 'H.264 · işlemci'}

CHECK_NAMES = {
    'dimensions': 'Çözünürlük aynı', 'pixel_format': 'Bit derinliği ve renk örneklemesi korundu',
    'color_hdr': 'Renk / HDR bilgisi korundu', 'stream_metadata': 'Akış bilgileri korundu',
    'chapters': 'Bölümler korundu', 'frame_count_and_timing': 'Kare sayısı ve zamanlama birebir',
    'audio_samples': 'Ses örnek düzeyinde aynı', 'copied_streams': 'Diğer akışlar birebir kopyalandı',
    'perceptual_quality': 'Görüntü kalitesi her karede doğrulandı', 'no_added_banding': 'Bantlanma eklenmedi',
    'original_unchanged': 'Orijinal dosya değişmedi', 'smaller': 'Çıktı daha küçük',
    'pixels_exact': 'Pikseller birebir aynı', 'alpha_exact': 'Saydamlık birebir aynı',
    'metadata_exact': 'Metadata korundu', 'encoded_payload_exact': 'Görüntü verisi baytı baytına aynı',
    'visually_lossless': 'Görsel kayıpsız (SSIMULACRA2 ≥ 90)',
    'dimensions_target': 'Hedef çözünürlüğe ulaşıldı', 'metadata_copied': 'Renk profili ve EXIF korundu',
    'content_consistent': 'İçerik orijinalle tutarlı (küçültülüp karşılaştırıldı)',
}

FINAL_PREFIXES = ('Doğrulandı', 'Doğrulanan çıktı', 'Seçilen kalite', 'Görsel kayıpsız kalite', 'İptal',
                  'Çıktı doğrulanamadı', 'Büyütüldü')
# Upscaling runs the normal video pipeline as its second half; those messages
# carry this invisible prefix and fill the second half of the progress bar.
STAGE_TWO = '⁣'


def describe(message: str, tries: int = 0):
    """Returns (text, overall progress 0..1 or None, counts_as_search_step).
    text is None for messages the GUI should not show as a running status."""
    percent_match = re.search(r' · %(\d+)$', message)
    fraction = int(percent_match[1]) / 100 if percent_match else 0.0
    percent = f' · %{int(fraction * 100)}' if percent_match else ''
    if message.startswith(STAGE_TWO):
        inner = message[len(STAGE_TWO):]
        if inner.startswith('Büyütülen video sıkıştırılıyor'):
            return 'Büyütülen video sıkıştırılıyor…', .50, False
        if inner.startswith('Orijinalle içerik'):
            return 'Orijinalle içerik ve ses karşılaştırılıyor…', .97, False
        text, fraction, search = describe(inner, tries)
        return text, (None if fraction is None else .50 + .47 * fraction), search
    if message.startswith(FINAL_PREFIXES):
        return None, None, False
    if message.startswith('Yapay zekâ ile büyütülüyor'):
        if percent_match:
            return f'Yapay zekâ ile büyütülüyor{percent}', .05 + .45 * fraction, False
        return message.replace(' · kare kare', '') + '…', .30 if 'model' in message else .05, False
    if message.startswith('Klasik yöntemle büyütülüyor'):
        return f'Klasik yöntemle büyütülüyor{percent}', (.05 + .45 * fraction) if percent_match else .30, False
    if message.startswith('Büyütülen fotoğraf kaydediliyor'):
        return 'Büyütülen fotoğraf kaydediliyor…', .85, False
    if message.startswith('Kaynak bütünlüğü'):
        return 'Hazırlanıyor…', .02, False
    if message.startswith('Sırada'):
        return 'Sırada · önceki dosya bitince başlayacak', None, False
    if message.startswith('Çözünürlük, akışlar'):
        return 'Dosya inceleniyor…', .04, False
    if message.startswith('Sahne ayrıntısı'):
        return 'Sahneler analiz ediliyor…', .06, False
    if message.startswith('Yazılım kodlama için'):
        return 'İşlemci ile kodlamaya hazırlanıyor…', None, False
    match = re.match(r'(\w+): gerçek çözünürlükte yetenek denemesi', message)
    if match:
        return f'Kodlayıcı hazırlanıyor · {ENCODER_NAMES.get(match[1], match[1])}', .08, False
    if re.match(r'\w+ · CQ \d+ örnek sahnelerde deneniyor', message):
        return f'En uygun kalite ayarı aranıyor · deneme {tries + 1}', min(.38, .10 + .05 * tries), True
    match = re.match(r'Kodlanıyor · (\w+)', message)
    if match:
        return f'Video sıkıştırılıyor · {ENCODER_NAMES.get(match[1], match[1])}{percent}', .40 + .25 * fraction, False
    if message.startswith('Akışlar, metadata'):
        return 'Kareler, zamanlama ve ses kontrol ediliyor…', .67, False
    if message.startswith('Tam video kalite ölçümü'):
        return f'Görüntü kalitesi kare kare doğrulanıyor{percent}', .70 + .28 * fraction, False
    if message.startswith(('Kayıpsız fotoğraf analizi', 'Görsel kayıpsız küçültme analizi')):
        return 'Fotoğraf inceleniyor…', .05, False
    if message.startswith('Kayıpsız PNG'):
        return 'PNG kayıpsız sıkıştırılıyor…', .30, False
    if message.startswith('Kayıpsız JPEG'):
        return 'JPEG kayıpsız optimize ediliyor…', .30, False
    if message.startswith('Pikseller, alpha'):
        return 'Pikseller birebir karşılaştırılıyor…', .85, False
    match = re.match(r'(AVIF|WEBP|JPEG) kalite \d+ deneniyor', message)
    if match:
        name = 'WebP' if match[1] == 'WEBP' else match[1]
        return f'En küçük görsel kayıpsız ayar aranıyor · {name} · deneme {tries + 1}', min(.92, .10 + .06 * tries), True
    return None, None, False


def kept_reason(message: str) -> str:
    """Short explanation for 'original kept' results."""
    if 'tahmini boyut' in message or 'küçük değil' in message or 'daha küçük değil' in message:
        return 'Zaten verimli sıkıştırılmış; kalite bozulmadan küçülmüyor. Orijinal olduğu gibi kaldı.'
    if 'Görsel kayıpsız kalite' in message:
        return 'Görsel kayıpsız kaliteye bu biçimlerde ulaşılamadı. Orijinal olduğu gibi kaldı.'
    if 'dolgu' in message:
        return 'Bu HEIC/AVIF zaten en küçük hâlinde. Orijinal olduğu gibi kaldı.'
    first = message.split('; ')[0].split(' · ')[0]
    return first if len(first) < 140 else first[:137] + '…'
