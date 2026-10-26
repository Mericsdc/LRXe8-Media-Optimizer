from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QSettings
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QFontMetrics, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFileDialog, QComboBox, QCheckBox, QSpinBox, QPlainTextEdit, QFrame, QProgressBar,
    QMessageBox, QScrollArea, QDialog, QStackedWidget, QButtonGroup, QSizePolicy, QProgressDialog)

from .core import Options, PHOTO_EXT, VIDEO_EXT, asset, find_tool
from .engine import Engine
from .status import CHECK_NAMES, ENCODER_NAMES, describe, kept_reason
from . import __version__, updater

ACCENT = '#3b8cff'
# Pure black with the logo's blue glow; fonts fall back to the macOS system face.
STYLE = '''
* { font-family: "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Arial"; }
QWidget { color: #f2f5fa; font-size: 14px; }
QMainWindow, QWidget#root, QDialog { background: #000000; }
QLabel { background: transparent; }
QLabel#title { font-size: 20px; font-weight: 700; color: #ffffff; }
QLabel#tagline, QLabel#muted { color: #8a94a8; }
QLabel#small { color: #8a94a8; font-size: 12px; }
QLabel#section { color: #6f8ab8; font-size: 12px; font-weight: 700; letter-spacing: 1px; }
QLabel#h2 { font-size: 16px; font-weight: 700; color: #ffffff; }
QLabel#glyph { color: #4d9bff; }
QFrame#drop { background: qradialgradient(cx:0.5, cy:0.35, radius:0.9, fx:0.5, fy:0.3, stop:0 #0b1d3f, stop:0.6 #050a14, stop:1 #000000);
              border: 2px dashed #1e3560; border-radius: 22px; }
QFrame#drop[active="true"] { border-color: #4d9bff; background: #08183a; }
QLabel#dropTitle { font-size: 24px; font-weight: 700; color: #ffffff; }
QLabel#dropHint { color: #8a94a8; font-size: 14px; }
QFrame#row { background: #090c13; border: 1px solid #161e2e; border-radius: 14px; }
QFrame#row:hover { border-color: #2a4677; }
QLabel#name { font-size: 14px; font-weight: 600; color: #ffffff; }
QLabel#status { color: #8f9bb3; font-size: 12px; }
QLabel#sizes { color: #c8d3e6; font-size: 13px; }
QLabel#badge { border-radius: 7px; padding: 3px 9px; font-size: 11px; font-weight: 800; }
QLabel#badge[kind="video"] { background: #0e2350; color: #7db4ff; }
QLabel#badge[kind="photo"] { background: #1d1745; color: #b6a6ff; }
QLabel#chip { border-radius: 11px; padding: 3px 11px; font-size: 12px; font-weight: 700; }
QLabel#chip[state="ok"] { background: #0c2b5c; color: #8cc2ff; }
QLabel#chip[state="up"] { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1554d6, stop:1 #3b8cff); color: #ffffff; }
QLabel#chip[state="kept"] { background: #33290c; color: #f2cc60; }
QLabel#chip[state="failed"] { background: #3a1414; color: #ff8a80; }
QLabel#chip[state="cancelled"] { background: #1a1f29; color: #8f9bb3; }
QLabel#chip[state="busy"] { background: #0b1a33; color: #6fa8ff; }
QProgressBar { background: #141b28; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1554d6, stop:1 #5aa8ff); border-radius: 2px; }
QProgressBar#overall { max-height: 6px; min-height: 6px; border-radius: 3px; }
QProgressBar#overall::chunk { border-radius: 3px; }
QPushButton { background: #0d1320; border: 1px solid #1f2b42; border-radius: 10px; padding: 9px 16px; font-weight: 600; color: #e8eef9; }
QPushButton:hover { background: #121b2e; border-color: #2f4875; }
QPushButton:disabled { color: #4d586b; background: #070a10; border-color: #121a28; }
QPushButton#primary { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1554d6, stop:1 #3b8cff); color: #ffffff;
                      border: none; padding: 13px 34px; font-size: 16px; font-weight: 800; border-radius: 12px; }
QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d63f0, stop:1 #5aa2ff); }
QPushButton#primary:disabled { background: #0b1a36; color: #3e5d93; }
QPushButton#stop { background: #2a0e0e; color: #ffb4ab; border: 1px solid #5c2020; padding: 13px 34px; font-size: 16px; font-weight: 800; border-radius: 12px; }
QPushButton#stop:hover { background: #3a1313; }
QPushButton#ghost { background: transparent; border: none; color: #8f9bb3; padding: 6px 10px; }
QPushButton#ghost:hover { color: #ffffff; background: #0d1320; }
QPushButton#ghost:disabled { color: #3c4555; background: transparent; }
QPushButton#big { padding: 12px 26px; font-size: 15px; color: #ffffff; border: none; border-radius: 12px; font-weight: 800;
                  background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1554d6, stop:1 #3b8cff); }
QPushButton#big:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d63f0, stop:1 #5aa2ff); }
QFrame#segmented { background: #070a10; border: 1px solid #161e2e; border-radius: 13px; }
QPushButton#segment { background: transparent; border: 1px solid transparent; border-radius: 10px; padding: 0; }
QPushButton#segment:hover { background: #0c1220; }
QPushButton#segment:checked { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0c2a66, stop:1 #123c8c); border-color: #2f6bd6; }
QPushButton#segment:disabled { background: transparent; }
QPushButton#segment:checked:disabled { background: #0b1a36; border-color: #1a3363; }
QLabel#segTitle { font-size: 14px; font-weight: 700; color: #ffffff; }
QLabel#segHint { color: #8a94a8; font-size: 12px; }
QFrame#panel { background: #04060a; border-top: 1px solid #121a28; }
QFrame#card { background: #090c13; border: 1px solid #161e2e; border-radius: 14px; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #1f2b42; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QComboBox, QSpinBox { background: #070a10; border: 1px solid #1f2b42; padding: 7px 10px; border-radius: 8px; }
QComboBox QAbstractItemView { background: #0d1320; selection-background-color: #133a80; border: 1px solid #1f2b42; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #3a4a66; border-radius: 5px; background: #070a10; }
QCheckBox::indicator:checked { background: #3b8cff; border-color: #3b8cff; }
QPlainTextEdit { background: #05070b; color: #9fb0c8; border: 1px solid #161e2e; border-radius: 10px; padding: 8px;
                 font-family: "Cascadia Mono", "Menlo", "Consolas"; font-size: 12px; }
QToolTip { background: #0d1320; color: #f2f5fa; border: 1px solid #2f4875; padding: 6px; }
QPushButton#bmc { background: #FFDD00; color: #000000; border: 1px solid #000000; border-radius: 10px; padding: 6px 14px;
                  font-family: "Bree Serif", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text"; font-size: 14px; font-weight: 700; }
QPushButton#bmc:hover { background: #ffe94d; }
QProgressDialog QLabel { color: #f2f5fa; }
'''

VIDEO_QUALITY = [('high', 'En iyi kalite', 'Görsel kayıpsız · önerilen'),
                 ('balanced', 'Yüksek kalite', 'Biraz daha küçük dosya'),
                 ('compact', 'Küçük dosya', 'Kalite yine kontrol edilir')]
PHOTO_MODES = [('lossless', 'Kayıpsız', 'Pikseller birebir aynı'),
               ('small', 'Daha küçük', 'Görsel kayıpsız · AVIF / JPEG')]
MODES = [('optimize', 'Küçült', 'Kaliteyi koruyarak dosya boyutunu düşür'),
         ('upscale', 'Büyüt / netleştir', 'Yapay zekâ ile çözünürlüğü ve netliği artır')]
UPSCALE_TARGETS = [('4k', "4K'ya", 'Video: 3840 × 2160 · fotoğraf: 4K sınırına'),
                   ('2x', '2 kat', 'Genişlik ve yükseklik iki katı'),
                   ('4x', '4 kat', 'Fotoğraf: dört katı · video: 4K')]
UPSCALE_CONTENT = [('photo', 'Fotoğraf / video', 'Gerçek çekimler, manzara, insan'),
                   ('art', 'Çizim / logo', 'Logo, illüstrasyon, anime, grafik')]
MODEL_NAMES = {'realesrgan-x4plus': 'yapay zekâ · fotoğraf modeli', 'realesrgan-x4plus-anime': 'yapay zekâ · çizim modeli',
               'realesr-animevideov3-x2': 'yapay zekâ · video modeli', 'realesr-animevideov3-x3': 'yapay zekâ · video modeli',
               'realesr-animevideov3-x4': 'yapay zekâ · video modeli', 'Lanczos': 'klasik büyütme (Lanczos)'}
CODECS = [('auto', 'Otomatik (önerilen)', 'MP4/MKV için AV1, MOV için HEVC. En küçük dosya.'),
          ('hevc', 'HEVC · Mac / iPhone uyumlu', 'Bütün Apple cihazları, Windows ve çoğu TV oynatır.'),
          ('h264', 'H.264 · en geniş uyumluluk', 'Her yerde oynar; dosyalar biraz daha büyük olur.'),
          ('av1', 'AV1 · en küçük', 'M1/M2 Mac ve eski cihazlar oynatamayabilir.')]
PHOTO_FORMATS = [('auto', 'Otomatik · en küçük'), ('avif', 'AVIF'), ('jpeg', 'JPEG · en geniş uyumluluk'), ('webp', 'WebP')]


def number(value, digits=1):
    return f'{value:.{digits}f}'.replace('.', ',')


def readable(size):
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            text = f'{value:.0f} {unit}' if unit in ('B', 'KB') else f'{value:.1f} {unit}'
            return text.replace('.', ',')
        value /= 1024


def label(text='', name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def icon_font():
    families = set(QFontDatabase.families())
    for family in ('Segoe Fluent Icons', 'Segoe MDL2 Assets'):
        if family in families:
            return family
    return None


def glyph(code, fallback, size=18, name='glyph'):
    widget = QLabel()
    widget.setObjectName(name)
    family = icon_font()
    if family:
        widget.setText(code)
        widget.setStyleSheet(f'font-family: "{family}"; font-size: {size}px;')
    else:
        widget.setText(fallback)
        widget.setStyleSheet(f'font-size: {size}px;')
    widget.setAlignment(Qt.AlignCenter)
    return widget


def repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def reveal(path: Path):
    path = Path(path)
    if os.name == 'nt' and path.exists():
        subprocess.Popen(['explorer', '/select,', str(path)])
    elif sys.platform == 'darwin' and path.exists():
        subprocess.Popen(['open', '-R', str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent if path.is_file() else path)))


def media_files(paths):
    """Files and dropped folders (recursively) filtered to supported media."""
    found, skipped = [], 0
    for item in paths:
        item = Path(item)
        candidates = sorted(p for p in item.rglob('*') if p.is_file()) if item.is_dir() else [item]
        for path in candidates:
            if path.suffix.lower() in PHOTO_EXT | VIDEO_EXT and '.lrxe8-' not in str(path):
                found.append(path.resolve())
            elif path.is_file():
                skipped += 1
    return found, skipped


class UpdateCheck(QThread):
    done = Signal(object, str)

    def run(self):
        try:
            self.done.emit(updater.check(), '')
        except Exception as error:
            self.done.emit(None, str(error))


class UpdateDownload(QThread):
    progress = Signal(int, int)
    done = Signal(str, str)

    def __init__(self, asset):
        super().__init__()
        self.asset = asset
        self.cancel = threading.Event()

    def run(self):
        try:
            path = updater.download(self.asset, self.cancel, lambda done, total: self.progress.emit(done, total))
            self.done.emit(str(path), '')
        except Exception as error:
            self.done.emit('', str(error))


class BatchWorker(QThread):
    progress = Signal(str, str)
    result = Signal(object)
    complete = Signal()

    def __init__(self, sources, destination, options):
        super().__init__()
        self.sources, self.destination = sources, destination
        self.engine = Engine(options)

    def run(self):
        try:
            self.engine.batch(self.sources, self.destination,
                lambda path, text: self.progress.emit(str(path), text), self.result.emit)
        finally:
            self.complete.emit()


class Segmented(QFrame):
    """Large two/three-way choice with a title and a one-line explanation each."""
    changed = Signal(str)

    def __init__(self, choices, current):
        super().__init__()
        self.setObjectName('segmented')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for value, title, hint in choices:
            button = QPushButton()
            button.setObjectName('segment')
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            inner = QVBoxLayout(button)
            inner.setContentsMargins(14, 8, 14, 8)
            inner.setSpacing(1)
            for text, name in ((title, 'segTitle'), (hint, 'segHint')):
                part = label(text, name)
                part.setAttribute(Qt.WA_TransparentForMouseEvents)
                inner.addWidget(part)
            button.setMinimumHeight(58)
            # Child labels do not feed QPushButton's size hint; measure them with the
            # fonts the stylesheet gives them so nothing is clipped.
            bold, small = QFont('Segoe UI'), QFont('Segoe UI')
            bold.setPixelSize(14)
            bold.setBold(True)
            small.setPixelSize(12)
            width = max(QFontMetrics(bold).horizontalAdvance(title), QFontMetrics(small).horizontalAdvance(hint))
            button.setMinimumWidth(max(150, int(width * 1.08) + 34))
            button.setToolTip(hint)
            self.group.addButton(button)
            self.buttons[value] = button
            layout.addWidget(button)
            button.clicked.connect(lambda _=False, v=value: self.changed.emit(v))
        self.set(current)

    def set(self, value):
        (self.buttons.get(value) or next(iter(self.buttons.values()))).setChecked(True)

    def value(self):
        return next(value for value, button in self.buttons.items() if button.isChecked())


class DropZone(QFrame):
    chooseRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName('drop')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch(2)
        layout.addWidget(glyph('', '⇪', 46), alignment=Qt.AlignCenter)
        layout.addSpacing(10)
        title = label('Video ve fotoğraflarını buraya bırak', 'dropTitle')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        hint = label('Klasör de bırakabilirsin · MP4, MOV, MKV, PNG, JPEG, WebP, HEIC, AVIF', 'dropHint')
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        layout.addSpacing(18)
        button = QPushButton('Dosya seç')
        button.setObjectName('big')
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.chooseRequested.emit)
        layout.addWidget(button, alignment=Qt.AlignCenter)
        layout.addStretch(2)
        promise = label('Orijinal dosyaların asla değiştirilmez. Kalite korunamazsa yeni dosya kaydedilmez.', 'small')
        promise.setAlignment(Qt.AlignCenter)
        layout.addWidget(promise)

    def set_active(self, active):
        self.setProperty('active', 'true' if active else 'false')
        repolish(self)


class FileRow(QFrame):
    removeRequested = Signal(object)
    detailsRequested = Signal(object)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.size = path.stat().st_size
        self.kind = 'video' if path.suffix.lower() in VIDEO_EXT else 'photo'
        self.result = None
        self.tries = 0
        self.fraction = 0.0
        self.setObjectName('row')
        self.setMinimumHeight(74)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 14, 10)
        outer.setSpacing(8)
        line = QHBoxLayout()
        line.setSpacing(14)
        badge = label('VİDEO' if self.kind == 'video' else 'FOTO', 'badge')
        badge.setProperty('kind', self.kind)
        badge.setFixedWidth(62)
        badge.setAlignment(Qt.AlignCenter)
        line.addWidget(badge, alignment=Qt.AlignVCenter)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.name = label('', 'name')
        self.name.setToolTip(str(path))
        self.name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status = label('Hazır', 'status')
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        texts.addWidget(self.name)
        texts.addWidget(self.status)
        line.addLayout(texts, 1)
        self.sizes = label(readable(self.size), 'sizes')
        self.sizes.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        line.addWidget(self.sizes)
        self.chip = label('', 'chip')
        self.chip.hide()
        line.addWidget(self.chip, alignment=Qt.AlignVCenter)
        self.action = QPushButton('Kaldır')
        self.action.setObjectName('ghost')
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.clicked.connect(self.on_action)
        line.addWidget(self.action, alignment=Qt.AlignVCenter)
        outer.addLayout(line)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.hide()
        outer.addWidget(self.bar)
        self.update_name()

    def update_name(self):
        metrics = self.name.fontMetrics()
        self.name.setText(metrics.elidedText(self.path.name, Qt.ElideMiddle, max(120, self.name.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_name()

    def mouseDoubleClickEvent(self, event):
        if self.result is not None:
            self.detailsRequested.emit(self)

    def on_action(self):
        if self.result is None:
            self.removeRequested.emit(self)
        elif self.result.output:
            reveal(Path(self.result.output))
        else:
            self.detailsRequested.emit(self)

    def set_chip(self, text, state):
        self.chip.setText(text)
        self.chip.setProperty('state', state)
        repolish(self.chip)
        self.chip.setVisible(bool(text))

    def reset(self):
        self.result, self.tries, self.fraction = None, 0, 0.0
        self.status.setText('Sırada')
        self.sizes.setText(readable(self.size))
        self.set_chip('', 'busy')
        self.bar.setValue(0)
        self.bar.show()
        self.action.setText('Kaldır')
        self.action.hide()

    def set_progress(self, message):
        text, fraction, search = describe(message, self.tries)
        if search:
            self.tries += 1
        if text:
            self.status.setText(text)
            self.status.setToolTip(message)
            self.set_chip('İşleniyor', 'busy')
        if fraction is not None and fraction > self.fraction:
            self.fraction = fraction
            self.bar.setValue(int(fraction * 1000))

    def set_result(self, result):
        self.result = result
        self.bar.hide()
        self.action.show()
        details = result.details
        if result.status == 'optimized' and details.get('mode') == 'upscale':
            before, after = details.get('source_size') or [0, 0], details.get('target_size') or [0, 0]
            self.sizes.setText(f'{before[0]}×{before[1]}  →  {after[0]}×{after[1]}')
            self.sizes.setToolTip(f'{readable(result.source_bytes)} → {readable(result.output_bytes)}')
            target = details.get('target', '')
            self.set_chip('4K' if target == '4k' or (target == '4x' and self.kind == 'video') else target.replace('x', '×'), 'up')
            consistency = details.get('consistency') or {}
            text = 'Büyütüldü · ' + MODEL_NAMES.get(details.get('model'), details.get('model', ''))
            quality = details.get('quality') or {}
            if quality.get('vmaf') is not None:
                text += f" · kodlama VMAF {number(quality['vmaf'])}"
            elif consistency.get('psnr') is not None:
                text += ' · içerik tutarlı'
            self.status.setText(text)
            self.action.setText('Klasörde göster')
            self.status.setToolTip(result.message)
            return
        if result.status == 'optimized':
            saved = 100 * (1 - result.output_bytes / max(1, result.source_bytes))
            self.sizes.setText(f'{readable(result.source_bytes)}  →  {readable(result.output_bytes)}')
            self.set_chip(f'−%{int(saved)}', 'ok')  # rounded down: never overstate the saving
            quality = details.get('quality') or {}
            if quality.get('vmaf') is not None:
                encoder = ENCODER_NAMES.get((details.get('selected') or {}).get('encoder'), '')
                text = f"Kalite doğrulandı · VMAF {number(quality['vmaf'])} · {encoder}"
            elif details.get('photo_mode') == 'small':
                selected = details.get('selected') or {}
                fmt = {'WEBP': 'WebP'}.get(details.get('output_format'), details.get('output_format', ''))
                text = f"Görsel kayıpsız · {fmt} · SSIMULACRA2 {number(selected.get('ssimulacra2', 0))}"
                if not details.get('target_met', True):
                    text += ' · hedef boyut kalite için aşıldı'
            else:
                text = 'Kayıpsız · pikseller birebir aynı'
            self.status.setText(text)
            self.action.setText('Klasörde göster')
        elif result.status == 'kept':
            self.set_chip('Orijinal korundu', 'kept')
            self.status.setText(kept_reason(result.message))
            self.action.setText('Ayrıntı')
        elif result.status == 'cancelled':
            self.set_chip('Durduruldu', 'cancelled')
            self.status.setText('İşlem durduruldu; orijinal dosya değişmedi.')
            self.action.setText('Ayrıntı')
        else:
            self.set_chip('Yapılamadı', 'failed')
            first = result.message.split('\n')[0]
            self.status.setText((first[:150] + '…') if len(first) > 150 else first)
            self.action.setText('Ayrıntı')
        self.status.setToolTip(result.message)


class SettingsDialog(QDialog):
    def __init__(self, parent, settings: QSettings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle('Gelişmiş ayarlar')
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(10)
        layout.addWidget(label('Gelişmiş ayarlar', 'h2'))
        layout.addWidget(label('Varsayılanlar çoğu kullanım için en iyisidir. Değişiklikler kaydedilir.', 'muted', True))
        layout.addSpacing(6)

        layout.addWidget(label('VİDEO', 'section'))
        layout.addWidget(label('Video biçimi (codec)'))
        self.codec = QComboBox()
        for value, title, _ in CODECS:
            self.codec.addItem(title, value)
        self.codec.setCurrentIndex(max(0, self.codec.findData(settings.value('codec', 'auto'))))
        layout.addWidget(self.codec)
        self.codec_hint = label('', 'small', True)
        layout.addWidget(self.codec_hint)
        self.codec.currentIndexChanged.connect(self.update_hint)
        self.update_hint()
        self.software = QCheckBox('Ekran kartı desteklemezse işlemci ile kodla (ör. ProRes / MJPEG 4:2:2)')
        self.software.setChecked(settings.value('software', True, type=bool))
        layout.addWidget(self.software)
        row = QHBoxLayout()
        row.addWidget(label('Aynı anda işlenecek dosya'))
        row.addStretch()
        self.parallel = QSpinBox()
        self.parallel.setRange(1, 4)
        self.parallel.setValue(settings.value('parallel', 2, type=int))
        row.addWidget(self.parallel)
        layout.addLayout(row)

        layout.addSpacing(10)
        layout.addWidget(label('BÜYÜTME', 'section'))
        row = QHBoxLayout()
        row.addWidget(label('Büyütme yöntemi'))
        row.addStretch()
        self.method = QComboBox()
        self.method.addItem('Yapay zekâ · Real-ESRGAN (önerilen)', 'ai')
        self.method.addItem('Klasik · Lanczos (yalnızca boyut)', 'classic')
        self.method.setCurrentIndex(max(0, self.method.findData(settings.value('upscale_method', 'ai'))))
        row.addWidget(self.method)
        layout.addLayout(row)
        layout.addWidget(label('Yapay zekâ ayrıntıyı netleştirir ve bozuklukları temizler; ekran kartı kullanır. '
                               'Klasik yöntem görüntüyü değiştirmeden yalnızca büyütür.', 'small', True))
        layout.addSpacing(10)
        layout.addWidget(label('FOTOĞRAF', 'section'))
        self.strip = QCheckBox("Görünmeyen metadata'yı sil (kamera, GPS, yorumlar)")
        self.strip.setChecked(settings.value('strip_metadata', False, type=bool))
        self.strip.setToolTip('ImageOptim gibi. Renk profili, yön bilgisi ve DPI her zaman korunur; görüntü değişmez.')
        layout.addWidget(self.strip)
        layout.addWidget(label('Renk profili, yön bilgisi ve DPI her zaman korunur; görüntü değişmez.', 'small', True))
        layout.addSpacing(4)
        layout.addWidget(label('"Daha küçük" modunda çıktı biçimi'))
        self.photo_format = QComboBox()
        for value, title in PHOTO_FORMATS:
            self.photo_format.addItem(title, value)
        self.photo_format.setCurrentIndex(max(0, self.photo_format.findData(settings.value('photo_format', 'auto'))))
        layout.addWidget(self.photo_format)
        row = QHBoxLayout()
        row.addWidget(label('"Daha küçük" modunda hedef boyut'))
        row.addStretch()
        self.target = QSpinBox()
        self.target.setRange(32, 65536)
        self.target.setSingleStep(64)
        self.target.setSuffix(' KB')
        self.target.setValue(settings.value('photo_target_kb', 256, type=int))
        row.addWidget(self.target)
        layout.addLayout(row)
        layout.addWidget(label('Kalite her zaman önce gelir: görsel kayıpsız sonuç hedefe sığmazsa hedef aşılır.', 'small', True))

        layout.addSpacing(12)
        buttons = QHBoxLayout()
        reset = QPushButton('Varsayılanlara dön')
        reset.setObjectName('ghost')
        reset.clicked.connect(self.defaults)
        buttons.addWidget(reset)
        buttons.addStretch()
        cancel = QPushButton('Vazgeç')
        cancel.clicked.connect(self.reject)
        save = QPushButton('Kaydet')
        save.setObjectName('big')
        save.clicked.connect(self.save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def update_hint(self):
        self.codec_hint.setText(CODECS[self.codec.currentIndex()][2])

    def defaults(self):
        self.codec.setCurrentIndex(0)
        self.software.setChecked(True)
        self.parallel.setValue(2)
        self.strip.setChecked(False)
        self.photo_format.setCurrentIndex(0)
        self.target.setValue(256)
        self.method.setCurrentIndex(0)

    def save(self):
        for key, value in (('codec', self.codec.currentData()), ('software', self.software.isChecked()),
                           ('parallel', self.parallel.value()), ('strip_metadata', self.strip.isChecked()),
                           ('photo_format', self.photo_format.currentData()), ('photo_target_kb', self.target.value()),
                           ('upscale_method', self.method.currentData())):
            self.settings.setValue(key, value)
        self.accept()


class DetailsDialog(QDialog):
    def __init__(self, parent, result):
        super().__init__(parent)
        source = Path(result.source)
        self.setWindowTitle(source.name)
        self.resize(720, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(10)
        layout.addWidget(label(source.name, 'h2', True))
        state = {'optimized': ('Büyütüldü ve doğrulandı', 'up') if result.details.get('mode') == 'upscale'
                 else ('Küçültüldü ve doğrulandı', 'ok'), 'kept': ('Orijinal korundu', 'kept'),
                 'failed': ('Yapılamadı', 'failed'), 'cancelled': ('Durduruldu', 'cancelled')}[result.status]
        chip = label(state[0], 'chip')
        chip.setProperty('state', state[1])
        layout.addWidget(chip, alignment=Qt.AlignLeft)
        message = result.message if result.status != 'kept' else kept_reason(result.message)
        layout.addWidget(label(message, 'muted', True))

        card = QFrame()
        card.setObjectName('card')
        grid = QGridLayout(card)
        grid.setContentsMargins(18, 14, 18, 14)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(7)
        rows = [('Kaynak', readable(result.source_bytes))]
        if result.output:
            saved = 100 * (1 - result.output_bytes / max(1, result.source_bytes))
            rows += [('Sonuç', f'{readable(result.output_bytes)}  (−%{saved:.1f})'.replace('.', ',')),
                     ('Kaydedildiği yer', result.output)]
        rows.append(('Süre', f'{int(result.elapsed_seconds // 60)} dk {int(result.elapsed_seconds % 60)} sn'))
        details = result.details
        selected = details.get('selected') or {}
        quality = details.get('quality') or {}
        if selected.get('encoder'):
            rows.append(('Kodlayıcı', f"{ENCODER_NAMES.get(selected['encoder'], selected['encoder'])} · "
                                      f"{selected.get('output_pixel_format', '')} · CQ {selected.get('quality')}"))
        if quality:
            rows += [('VMAF (ortalama / en kötü %2 kare)', f"{number(quality.get('vmaf', 0), 2)} / {number(quality.get('vmaf_low', 0), 2)}"),
                     ('Bantlanma (kaynak → çıktı)', f"{number(quality.get('cambi_source_mean', 0), 2)} → {number(quality.get('cambi_output_mean', 0), 2)}"
                                                    '  (1 altı algılanamaz)'),
                     ('Ölçülen kare', str(quality.get('frames_measured')))]
        timeline = details.get('timeline') or {}
        if timeline:
            rows.append(('Zamanlama farkı', f"{timeline.get('max_timing_error_seconds', 0):g} sn · {timeline.get('frames')} kare"))
        if details.get('mode') == 'upscale':
            before, after = details.get('source_size') or [0, 0], details.get('target_size') or [0, 0]
            rows.insert(1, ('Çözünürlük', f'{before[0]}×{before[1]}  →  {after[0]}×{after[1]}'))
            rows.append(('Büyütme', MODEL_NAMES.get(details.get('model'), str(details.get('model')))))
            if details.get('output_format'):
                rows.append(('Kaydedilen biçim', details['output_format']))
            consistency = details.get('consistency') or {}
            if consistency:
                text = (f"VMAF {number(consistency['vmaf'], 1)} · PSNR {number(consistency['psnr_y'], 1)} dB"
                        if 'vmaf' in consistency else f"PSNR {number(consistency['psnr'], 1)} dB")
                rows.append(('Orijinalle tutarlılık', text + '  (küçültülüp karşılaştırıldı)'))
            if details.get('note'):
                rows.append(('Not', details['note']))
        elif details.get('method'):
            rows.append(('Yöntem', details['method']))
        if details.get('photo_mode') == 'small' and selected:
            rows.append(('Görsel kalite (SSIMULACRA2)', f"{number(selected.get('ssimulacra2', 0))}  (90 ve üstü görsel kayıpsız)"))
        for index, (key, value) in enumerate(rows):
            name = label(key, 'muted')
            text = label(str(value), wrap=True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(name, index, 0, alignment=Qt.AlignTop)
            grid.addWidget(text, index, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(card)

        checks = [CHECK_NAMES.get(key, key) for key, value in result.checks.items() if value]
        if checks:
            layout.addWidget(label('KONTROLLER', 'section'))
            layout.addWidget(label('\n'.join('✓  ' + text for text in checks), wrap=True))
        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setPlainText(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
        self.raw.hide()
        layout.addWidget(self.raw, 1)
        layout.addStretch()
        buttons = QHBoxLayout()
        technical = QPushButton('Teknik ayrıntılar')
        technical.setObjectName('ghost')
        technical.clicked.connect(lambda: self.raw.setVisible(not self.raw.isVisible()))
        buttons.addWidget(technical)
        buttons.addStretch()
        if result.output:
            show = QPushButton('Klasörde göster')
            show.clicked.connect(lambda: reveal(Path(result.output)))
            buttons.addWidget(show)
        close = QPushButton('Kapat')
        close.setObjectName('big')
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'LRXe8 Media Optimizer {__version__}')
        self.setWindowIcon(QIcon(str(asset('logo.png'))))
        self.setAcceptDrops(True)
        self.settings = QSettings('LRXe8', 'MediaOptimizer')
        default_output = Path.home() / ('Movies' if sys.platform == 'darwin' else 'Videos') / 'LRXe8 Optimized'
        self.destination = Path(self.settings.value('output', str(default_output)))
        self.paths, self.rows, self.results = [], {}, {}
        self.run_paths = []
        self.flash_text = ''
        self.finished_at = None
        self.worker = None
        self.started = None
        self.completed = 0
        self.saved_bytes = 0
        self.build()
        screen = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(980, 660)
        self.resize(min(1200, screen.width() - 40), min(820, screen.height() - 60))
        timer = QTimer(self)
        timer.timeout.connect(self.tick)
        timer.start(1000)
        self.refresh()

    # ------------------------------------------------------------------ layout
    def build(self):
        canvas = QWidget()
        canvas.setObjectName('root')
        self.setCentralWidget(canvas)
        root = QVBoxLayout(canvas)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QVBoxLayout()
        body.setContentsMargins(30, 22, 30, 18)
        body.setSpacing(16)
        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(str(asset('logo.png'))).pixmap(46, 46))
        header.addWidget(logo)
        header.addSpacing(6)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label('LRXe8 Media Optimizer', 'title'))
        titles.addWidget(label('Kaliteyi bozmadan küçült veya büyüt · her şey bu bilgisayarda kalır', 'tagline'))
        header.addLayout(titles)
        header.addStretch()
        side = QVBoxLayout()
        side.setSpacing(6)
        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        buttons.addStretch()
        self.update_button = QPushButton('⟳  Güncellemeleri denetle')
        self.update_button.setObjectName('ghost')
        self.update_button.setCursor(Qt.PointingHandCursor)
        self.update_button.setToolTip(f'Sürüm {__version__} · GitHub\'daki en son sürümle karşılaştırır')
        self.update_button.clicked.connect(self.check_updates)
        buttons.addWidget(self.update_button)
        self.settings_button = QPushButton('⚙  Gelişmiş ayarlar')
        self.settings_button.setObjectName('ghost')
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.clicked.connect(self.open_settings)
        buttons.addWidget(self.settings_button)
        side.addLayout(buttons)
        donate = QPushButton('🍺  Buy me a beer')
        donate.setObjectName('bmc')
        donate.setCursor(Qt.PointingHandCursor)
        donate.setToolTip('Uygulamayı beğendiysen geliştiriciye bir bira ısmarla · buymeacoffee.com/Lurexa')
        donate.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(updater.DONATE_URL)))
        side.addWidget(donate, alignment=Qt.AlignRight)
        header.addLayout(side)
        body.addLayout(header)
        choice = QHBoxLayout()
        choice.setSpacing(16)
        choice.addWidget(label('NE YAPILSIN?', 'section'))
        self.mode = Segmented(MODES, self.settings.value('mode', 'optimize'))
        self.mode.changed.connect(self.mode_changed)
        choice.addWidget(self.mode)
        choice.addStretch()
        body.addLayout(choice)

        self.stack = QStackedWidget()
        self.drop = DropZone()
        self.drop.chooseRequested.connect(self.choose_files)
        self.stack.addWidget(self.drop)
        list_page = QWidget()
        list_layout = QVBoxLayout(list_page)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)
        toolbar = QHBoxLayout()
        toolbar.addWidget(label('Dosyalar', 'h2'))
        self.count_label = label('', 'muted')
        toolbar.addWidget(self.count_label)
        toolbar.addStretch()
        self.add_button = QPushButton('+  Dosya ekle')
        self.add_button.clicked.connect(self.choose_files)
        self.clear_button = QPushButton('Listeyi temizle')
        self.clear_button.setObjectName('ghost')
        self.clear_button.clicked.connect(self.clear)
        toolbar.addWidget(self.clear_button)
        toolbar.addWidget(self.add_button)
        list_layout.addLayout(toolbar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        self.rows_layout = QVBoxLayout(container)
        self.rows_layout.setContentsMargins(0, 0, 6, 0)
        self.rows_layout.setSpacing(8)
        self.rows_layout.addStretch()
        scroll.setWidget(container)
        list_layout.addWidget(scroll, 1)
        self.stack.addWidget(list_page)
        body.addWidget(self.stack, 1)

        options = QHBoxLayout()
        options.setSpacing(28)
        self.option_pages = QStackedWidget()
        self.option_pages.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        shrink = QWidget()
        row = QHBoxLayout(shrink)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(28)
        for title, attribute, choices, key, default in (
                ('VİDEO KALİTESİ', 'quality', VIDEO_QUALITY, 'quality', 'high'),
                ('FOTOĞRAFLAR', 'photo_mode', PHOTO_MODES, 'photo_mode', 'lossless')):
            column = QVBoxLayout()
            column.setSpacing(6)
            column.addWidget(label(title, 'section'))
            control = Segmented(choices, self.settings.value(key, default))
            control.changed.connect(lambda value, k=key: self.settings.setValue(k, value))
            setattr(self, attribute, control)
            column.addWidget(control)
            row.addLayout(column)
        row.addStretch()
        enlarge = QWidget()
        row = QHBoxLayout(enlarge)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(28)
        for title, attribute, choices, key, default in (
                ('HEDEF BOYUT', 'upscale_target', UPSCALE_TARGETS, 'upscale_target', '4k'),
                ('GÖRÜNTÜ TÜRÜ', 'upscale_content', UPSCALE_CONTENT, 'upscale_content', 'photo')):
            column = QVBoxLayout()
            column.setSpacing(6)
            column.addWidget(label(title, 'section'))
            control = Segmented(choices, self.settings.value(key, default))
            control.changed.connect(lambda value, k=key: self.settings.setValue(k, value))
            setattr(self, attribute, control)
            column.addWidget(control)
            row.addLayout(column)
        row.addStretch()
        self.option_pages.addWidget(shrink)
        self.option_pages.addWidget(enlarge)
        options.addWidget(self.option_pages, 1)
        self.option_pages.setCurrentIndex(1 if self.mode.value() == 'upscale' else 0)
        body.addLayout(options)
        root.addLayout(body, 1)

        panel = QFrame()
        panel.setObjectName('panel')
        bottom = QHBoxLayout(panel)
        bottom.setContentsMargins(30, 14, 30, 18)
        bottom.setSpacing(20)
        info = QVBoxLayout()
        info.setSpacing(6)
        where = QHBoxLayout()
        where.setSpacing(6)
        where.addWidget(label('Kaydedilecek yer:', 'small'))
        self.output_label = label('', 'small')
        self.output_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        where.addWidget(self.output_label, 1)
        self.output_button = QPushButton('Değiştir')
        self.output_button.setObjectName('ghost')
        self.output_button.clicked.connect(self.choose_output)
        open_button = QPushButton('Klasörü aç')
        open_button.setObjectName('ghost')
        open_button.clicked.connect(self.open_output)
        where.addWidget(self.output_button)
        where.addWidget(open_button)
        info.addLayout(where)
        self.summary = label('', 'muted')
        info.addWidget(self.summary)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName('overall')
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        info.addWidget(self.progress_bar)
        bottom.addLayout(info, 1)
        self.start_button = QPushButton('Başlat')
        self.start_button.setObjectName('primary')
        self.start_button.setCursor(Qt.PointingHandCursor)
        self.start_button.setMinimumWidth(180)
        self.start_button.clicked.connect(self.start_or_stop)
        bottom.addWidget(self.start_button, alignment=Qt.AlignVCenter)
        root.addWidget(panel)
        self.update_output_label()

    # ------------------------------------------------------------------ files
    def choose_files(self):
        pattern = ' '.join('*' + ext for ext in sorted(PHOTO_EXT | VIDEO_EXT))
        files, _ = QFileDialog.getOpenFileNames(self, 'Video veya fotoğraf seç', '',
                                                f'Video ve fotoğraflar ({pattern});;Tüm dosyalar (*)')
        self.add_paths(files)

    def add_paths(self, files):
        if self.busy():
            return
        found, skipped = media_files(files)
        added = 0
        for path in found:
            if path in self.rows:
                continue
            row = FileRow(path)
            row.removeRequested.connect(self.remove_row)
            row.detailsRequested.connect(lambda r: self.open_details(r.result))
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            self.rows[path] = row
            self.paths.append(path)
            added += 1
        self.refresh()
        if skipped:
            self.flash(f'{skipped} desteklenmeyen dosya eklenmedi.')

    def remove_row(self, row):
        if self.busy():
            return
        self.paths.remove(row.path)
        self.rows.pop(row.path).deleteLater()
        self.results.pop(str(row.path), None)
        self.refresh()

    def clear(self):
        if self.busy():
            return
        for row in self.rows.values():
            row.deleteLater()
        self.rows.clear()
        self.paths.clear()
        self.results.clear()
        self.completed = self.saved_bytes = 0
        self.started = None
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.refresh()

    # ------------------------------------------------------------------ output
    def update_output_label(self):
        metrics = self.output_label.fontMetrics()
        self.output_label.setText(metrics.elidedText(str(self.destination), Qt.ElideMiddle, max(200, self.output_label.width())))
        self.output_label.setToolTip(str(self.destination))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_output_label()

    def choose_output(self):
        directory = QFileDialog.getExistingDirectory(self, 'Kaydedilecek klasör', str(self.destination))
        if directory:
            self.destination = Path(directory)
            self.settings.setValue('output', str(self.destination))
            self.update_output_label()

    def open_output(self):
        self.destination.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.destination)))

    def mode_changed(self, value):
        self.settings.setValue('mode', value)
        self.option_pages.setCurrentIndex(1 if value == 'upscale' else 0)
        self.refresh()

    # ------------------------------------------------------------------ updates
    def check_updates(self):
        self.update_button.setEnabled(False)
        self.update_button.setText('⟳  Denetleniyor…')
        self.update_check = UpdateCheck()
        self.update_check.done.connect(self.update_checked)
        self.update_check.start()

    def update_checked(self, info, error):
        self.update_button.setEnabled(True)
        self.update_button.setText('⟳  Güncellemeleri denetle')
        if error or info is None:
            QMessageBox.warning(self, 'Güncelleme denetlenemedi',
                                f'{error}\n\nİnternet bağlantını kontrol et. Sürümler: {updater.RELEASES_PAGE}')
            return
        if not info['newer']:
            QMessageBox.information(self, 'Güncel', f'En güncel sürümü kullanıyorsun ({__version__}).')
            return
        notes = info['notes'].strip()
        if len(notes) > 900:
            notes = notes[:900].rsplit('\n', 1)[0] + '\n…'
        box = QMessageBox(self)
        box.setWindowTitle('Yeni sürüm hazır')
        box.setText(f"<b>LRXe8 Media Optimizer {info['version']}</b> yayınlandı (şu an {__version__}).")
        box.setInformativeText('Şimdi indirip kurmak ister misin? Uygulama kapanıp güncellenir ve yeniden açılır.'
                               if info['asset'] else 'Bu sistem için kurulum dosyası yok; sürüm sayfasını açabilirsin.')
        if notes:
            box.setDetailedText(notes)
        install = box.addButton('İndir ve kur', QMessageBox.AcceptRole) if info['asset'] else None
        page = box.addButton('Sürüm sayfası', QMessageBox.HelpRole)
        box.addButton('Sonra', QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is page:
            QDesktopServices.openUrl(QUrl(info['page']))
        elif install is not None and box.clickedButton() is install:
            if self.busy():
                QMessageBox.information(self, 'İşlem sürüyor', 'Önce dosyaların işlenmesi bitsin, sonra güncelle.')
                return
            self.download_update(info['asset'])

    def download_update(self, asset):
        size = max(1, asset.get('size') or 1)
        self.update_progress = QProgressDialog('Güncelleme indiriliyor…', 'İptal', 0, 1000, self)
        self.update_progress.setWindowTitle('Güncelleme')
        self.update_progress.setMinimumDuration(0)
        self.update_progress.setAutoClose(False)
        self.update_progress.setAutoReset(False)
        self.update_progress.setValue(0)
        self.update_download = UpdateDownload(asset)
        self.update_progress.canceled.connect(self.update_download.cancel.set)
        self.update_download.progress.connect(
            lambda done, total: (self.update_progress.setValue(int(1000 * done / max(1, total or size))),
                                 self.update_progress.setLabelText(f'Güncelleme indiriliyor… {readable(done)} / {readable(total or size)}')))
        self.update_download.done.connect(self.update_downloaded)
        self.update_download.start()

    def update_downloaded(self, path, error):
        self.update_progress.close()
        if error:
            if 'iptal' not in error.lower():
                QMessageBox.warning(self, 'Güncelleme indirilemedi', error)
            return
        try:
            updater.install(Path(path))
        except Exception as failure:
            QMessageBox.warning(self, 'Güncelleme başlatılamadı', str(failure))
            return
        QApplication.quit()

    def open_settings(self):
        SettingsDialog(self, self.settings).exec()

    def open_details(self, result):
        if result is not None:
            self.details_dialog = DetailsDialog(self, result)
            self.details_dialog.show()

    # ------------------------------------------------------------------ run
    def busy(self):
        return bool(self.worker and self.worker.isRunning())

    def options(self):
        value = self.settings.value
        return Options(quality=self.quality.value(), compatibility=value('codec', 'auto'),
                       software=value('software', True, type=bool), max_parallel=value('parallel', 2, type=int),
                       photo_mode=self.photo_mode.value(), photo_target_kb=value('photo_target_kb', 256, type=int),
                       photo_format=value('photo_format', 'auto'), strip_metadata=value('strip_metadata', False, type=bool),
                       mode=self.mode.value(), upscale_target=self.upscale_target.value(),
                       upscale_content=self.upscale_content.value(), upscale_method=value('upscale_method', 'ai'))

    def start_or_stop(self):
        if self.busy():
            self.cancel()
        else:
            self.start()

    def start(self):
        if not self.paths:
            return
        if any(p.suffix.lower() in VIDEO_EXT for p in self.paths) and (not find_tool('ffmpeg', False) or not find_tool('ffprobe', False)):
            QMessageBox.warning(self, 'Araç eksik', 'FFmpeg bulunamadı. Uygulamayı yeniden kurun veya tools klasörünü uygulamanın yanında tutun.')
            return
        try:
            self.destination.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.warning(self, 'Klasör kullanılamıyor', f'Kaydedilecek klasör oluşturulamadı:\n{error}')
            return
        # Only files that have not been processed yet; when everything is done,
        # "Başlat" runs the whole list again (e.g. after changing settings).
        pending = [path for path in self.paths if self.rows[path].result is None]
        if not pending:
            pending = list(self.paths)
            self.results.clear()
            self.saved_bytes = 0
        self.run_paths = pending
        self.completed = 0
        self.started, self.finished_at = time.monotonic(), None
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        for path in pending:
            self.rows[path].reset()
        self.worker = BatchWorker(pending, self.destination, self.options())
        self.worker.progress.connect(self.on_progress)
        self.worker.result.connect(self.on_result)
        self.worker.finished.connect(self.finish)
        self.set_busy(True)
        self.worker.start()

    def cancel(self):
        if self.worker:
            self.worker.engine.cancel.set()
            self.start_button.setEnabled(False)
            self.start_button.setText('Durduruluyor…')

    def set_busy(self, busy):
        for control in (self.add_button, self.clear_button, self.output_button, self.settings_button,
                        self.mode, self.quality, self.photo_mode, self.upscale_target, self.upscale_content):
            control.setEnabled(not busy)
        self.start_button.setEnabled(busy or bool(self.paths))
        self.start_button.setText('Durdur' if busy else 'Başlat')
        self.start_button.setObjectName('stop' if busy else 'primary')
        repolish(self.start_button)
        self.refresh()

    def on_progress(self, filename, message):
        row = self.rows.get(Path(filename))
        if row is not None and row.result is None:
            row.set_progress(message)
            self.update_overall()

    def on_result(self, result):
        self.results[result.source] = result
        self.completed += 1
        row = self.rows.get(Path(result.source))
        if row is not None:
            row.set_result(result)
        if result.status == 'optimized' and result.details.get('mode') != 'upscale':
            self.saved_bytes += result.source_bytes - result.output_bytes
        self.update_overall()
        self.refresh()

    def update_overall(self):
        if self.progress_bar.maximum() != 1000:
            self.progress_bar.setValue(self.completed)
            return
        rows = [self.rows[path] for path in self.run_paths if path in self.rows]
        if rows:
            total = sum(1.0 if row.result is not None else row.fraction for row in rows)
            self.progress_bar.setValue(int(1000 * total / len(rows)))

    def finish(self):
        self.finished_at = time.monotonic()
        self.set_busy(False)
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.refresh()
        counts = self.counts()
        if counts['failed']:
            self.flash('Bazı dosyalar işlenemedi. Ayrıntı için satırdaki "Ayrıntı" düğmesine tıklayın.')

    def counts(self):
        counts = {key: sum(result.status == key for result in self.results.values())
                  for key in ('optimized', 'kept', 'failed', 'cancelled')}
        enlarged = sum(result.status == 'optimized' and result.details.get('mode') == 'upscale'
                       for result in self.results.values())
        if enlarged:
            counts['optimized'] -= enlarged
            counts['upscaled'] = enlarged
        return counts

    def elapsed(self):
        if self.started is None:
            return ''
        end = self.finished_at if not self.busy() else None
        seconds = int((end or time.monotonic()) - self.started)
        return f'{seconds // 60:02d}:{seconds % 60:02d}'

    def tick(self):
        if self.busy():
            self.refresh()

    def flash(self, text):
        self.flash_text = text
        self.refresh()
        QTimer.singleShot(5000, self.clear_flash)

    def clear_flash(self):
        self.flash_text = ''
        self.refresh()

    def refresh(self):
        self.stack.setCurrentIndex(1 if self.paths else 0)
        total = sum(row.size for row in self.rows.values())
        videos = sum(row.kind == 'video' for row in self.rows.values())
        photos = len(self.rows) - videos
        parts = [f'{videos} video' if videos else '', f'{photos} fotoğraf' if photos else '']
        self.count_label.setText(' · '.join(p for p in parts if p) + (f' · {readable(total)}' if self.rows else ''))
        if self.busy():
            text = f'İşleniyor · {self.completed} / {len(self.run_paths)} tamamlandı · {self.elapsed()}'
            if self.saved_bytes:
                text += f' · {readable(self.saved_bytes)} kazanıldı'
        elif self.results:
            counts = self.counts()
            pieces = [f"{counts['upscaled']} büyütüldü" if counts.get('upscaled') else '',
                      f"{counts['optimized']} küçültüldü" if counts['optimized'] else '',
                      f"{counts['kept']} korundu" if counts['kept'] else '',
                      f"{counts['failed']} yapılamadı" if counts['failed'] else '',
                      f"{counts['cancelled']} durduruldu" if counts['cancelled'] else '']
            text = 'Bitti · ' + ', '.join(p for p in pieces if p)
            if self.saved_bytes:
                text += f' · {readable(self.saved_bytes)} kazanıldı'
            if self.elapsed():
                text += f' · {self.elapsed()}'
        elif self.paths:
            text = 'Hazır · başlatmak için "Başlat"a bas · orijinaller değişmez'
        else:
            text = 'Başlamak için dosya ekle'
        if self.flash_text:
            text = self.flash_text
        self.summary.setText(text)
        if not self.busy():
            self.start_button.setEnabled(bool(self.paths))

    # ------------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy():
            event.acceptProposedAction()
            self.drop.set_active(True)

    def dragLeaveEvent(self, event):
        self.drop.set_active(False)

    def dropEvent(self, event):
        self.drop.set_active(False)
        self.add_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.busy():
            answer = QMessageBox.question(self, 'İşlem sürüyor',
                                          'Dosyalar hâlâ işleniyor. Durdurup kapatmak ister misin?\n'
                                          'Orijinal dosyalar değişmez; yarım kalan çıktılar silinir.')
            if answer == QMessageBox.Yes:
                self.cancel()
                self.worker.wait(30000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def launch():
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('LRXe8.MediaOptimizer')
        except (AttributeError, OSError):
            pass
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
