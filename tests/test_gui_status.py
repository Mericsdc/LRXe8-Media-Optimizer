"""Plain-language GUI status mapping and the new main window's basic behaviour."""
import os
from pathlib import Path

import pytest
from PIL import Image

from lrxe8.core import Result
from lrxe8.status import describe, kept_reason

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def test_engine_steps_become_plain_turkish_with_rising_progress():
    steps = ['Kaynak bütünlüğü kaydediliyor', 'Çözünürlük, akışlar ve renk özellikleri okunuyor',
             'Sahne ayrıntısı, hareket ve düz alanlar analiz ediliyor', 'hevc_nvenc: gerçek çözünürlükte yetenek denemesi',
             'hevc_nvenc · CQ 22 örnek sahnelerde deneniyor', 'Kodlanıyor · hevc_nvenc · CQ 22 · %50',
             'Akışlar, metadata ve kare zamanları doğrulanıyor', 'Tam video kalite ölçümü (VMAF + bantlanma) · %90']
    fractions = []
    for message in steps:
        text, fraction, _ = describe(message)
        assert text and 'nvenc' not in text and 'CQ' not in text
        fractions.append(fraction)
    assert fractions == sorted(fractions)
    assert describe('Kodlanıyor · hevc_nvenc · CQ 22 · %50')[0] == 'Video sıkıştırılıyor · HEVC · ekran kartı · %50'


def test_search_steps_count_up_and_final_messages_are_not_statuses():
    first = describe('av1_nvenc · CQ 26 örnek sahnelerde deneniyor', 0)
    third = describe('av1_nvenc · CQ 32 örnek sahnelerde deneniyor', 2)
    assert first[2] and third[1] > first[1] and 'deneme 3' in third[0]
    assert describe('Doğrulandı · %76.6 daha küçük')[0] is None
    assert describe('Bilinmeyen teknik satır')[0] is None


def test_kept_reason_is_short_and_plain():
    long = ('Seçilen kalite korunarak küçültülemedi; orijinal korundu. av1_nvenc: görsel kayıpsız kalite için '
            'tahmini boyut (22.8 MB) kaynağın video akışından (9.3 MB) büyük')
    assert kept_reason(long).startswith('Zaten verimli sıkıştırılmış')
    assert kept_reason('HEIF: güvenle kaldırılabilecek son dolgu alanı yok; orijinal korundu.').startswith('Bu HEIC/AVIF')


@pytest.fixture(scope='module')
def qt_app():
    from PySide6.QtWidgets import QApplication
    from lrxe8.gui import STYLE
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    return app


def test_folder_drop_filters_media_and_rows_show_results(tmp_path, qt_app):
    from lrxe8.gui import MainWindow, media_files
    folder = tmp_path / 'klasör'
    (folder / 'alt').mkdir(parents=True)
    Image.new('RGB', (8, 8), 'red').save(folder / 'a.png')
    Image.new('RGB', (8, 8), 'blue').save(folder / 'alt' / 'b.jpg')
    (folder / 'notlar.txt').write_text('x', encoding='utf-8')
    found, skipped = media_files([folder])
    assert [p.name for p in found] == ['a.png', 'b.jpg'] and skipped == 1
    window = MainWindow()
    window.add_paths([str(folder)])
    assert window.stack.currentIndex() == 1 and len(window.rows) == 2
    assert window.summary.text() == '1 desteklenmeyen dosya eklenmedi.'
    window.clear_flash()
    png = folder / 'a.png'
    window.on_result(Result(source=str(png.resolve()), status='optimized', message='Doğrulandı', source_bytes=1000,
                            output_bytes=600, output=str(png), details={'photo_mode': 'lossless'}))
    row = window.rows[png.resolve()]
    assert row.chip.text() == '−%40' and 'birebir' in row.status.text()
    assert row.action.text() == 'Klasörde göster'
    window.on_result(Result(source=str((folder / 'alt' / 'b.jpg').resolve()), status='kept',
                            message='Doğrulanan çıktı daha küçük değil; orijinal korundu.', source_bytes=500))
    assert window.counts() == {'optimized': 1, 'kept': 1, 'failed': 0, 'cancelled': 0}
    assert '1 küçültüldü' in window.summary.text() and '1 korundu' in window.summary.text()
    window.clear()
    assert window.stack.currentIndex() == 0
    window.close()
