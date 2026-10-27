# Paket bileşenleri

LRXe8 Media Optimizer'ın kendi kaynak kodu Apache License 2.0 ile lisanslıdır (`LICENSE`, `NOTICE`). Aşağıdaki bileşenler pakete eklenir ve kendi lisanslarına tabidir.

Bu dosya paket içindeki bileşenleri ve yeniden elde etme kaynaklarını kaydeder. Sürümler bu teslimde sabitlenmiştir; uygulama kendiliğinden güncelleme veya araç indirmesi yapmaz.

| Bileşen | Sürüm | Kaynak / lisans bilgisi |
| --- | --- | --- |
| Python | 3.12.15 | [Python](https://www.python.org/), PSF lisansı |
| PySide6 Essentials / Qt | 6.8.3 | [Qt for Python](https://doc.qt.io/qtforpython-6/), LGPL/GPL/ticari lisans seçenekleri |
| Pillow | 13.0.0 | [Pillow](https://github.com/python-pillow/Pillow), HPND |
| pillow-heif | 1.8.1 | [pillow-heif](https://github.com/bigcat88/pillow_heif), BSD-3-Clause; libheif ve codec bileşenlerinin kendi lisansları da geçerlidir |
| psutil | 7.2.2 | [psutil](https://github.com/giampaolo/psutil), BSD-3-Clause |
| FFmpeg / FFprobe | 9.0.2 full build | [Gyan Windows derlemesi](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2), derlemenin GPL lisans metni tools içinde |
| libjpeg-turbo / jpegtran | 3.2.0 | [libjpeg-turbo](https://github.com/libjpeg-turbo/libjpeg-turbo/releases/tag/3.2.0), lisans metinleri tools içinde |
| oxipng | 10.2.1 | [oxipng](https://github.com/oxipng/oxipng/releases/tag/v10.2.1), MIT; lisans metni tools içinde |
| mozjpeg-lossless-optimization (MozJPEG) | 1.3.2 | [wanadev/mozjpeg-lossless-optimization](https://github.com/wanadev/mozjpeg-lossless-optimization), BSD-3-Clause; MozJPEG/libjpeg-turbo lisansları |
| SSIMULACRA2 (libjxl araçları) | 0.12.0 | [libjxl v0.12.0](https://github.com/libjxl/libjxl/releases/tag/v0.12.0) `jxl-x64-windows-static.zip` içinden yalnızca `ssimulacra2.exe`; BSD-3-Clause, lisanslar `tools/jxl/licenses` içinde |
| realesrgan-ncnn-py (Real-ESRGAN + ncnn) | 2.0.0 | [Final2x/realesrgan-ncnn-py](https://github.com/Final2x/realesrgan-ncnn-py), BSD-3-Clause; [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) modelleri BSD-3-Clause; [ncnn](https://github.com/Tencent/ncnn) BSD-3-Clause. Yalnızca derlenmiş modül ve modeller kullanılır (OpenCV/NumPy pakete girmez). |
| FFmpeg (macOS) | 9.0.2 | Mac derlemesinde [martin-riedl.de](https://ffmpeg.martin-riedl.de) statik derlemesi, GPL; betik SHA-256 doğrular |
| Inno Setup — kurulum derleyicisi | 6.7.3 | [Inno Setup](https://jrsoftware.org/isinfo.php), ücretsiz Inno Setup lisansı; kurulum dosyasına yalnızca kurulum/kaldırma çalışma kodu girer |
| PyInstaller — paketleme aracı | 6.22.3 | [PyInstaller](https://pyinstaller.org/), GPL ve bootloader istisnası |

Python bağımlılıklarının lisans metinleri `licenses` klasöründe, harici araçların orijinal lisansları kendi `tools` klasörlerinde korunur. Qt DLL'leri tek exe içine gömülmez; `app/_internal` altında ayrı dosyalardır. Kaynak kodları ve sabit bağımlılık listeleri bu paketle birlikte gelir.

FFmpeg arşivi: `ffmpeg-9.0.2-full_build.7z`.

SHA-256: `f0e46253c70dfe902bac915dfb4224f0cf1b7c6eeab9da2ccc9a5581f9a71b13`.

Bu değer indirme sırasında GitHub yayın varlığı özetiyle karşılaştırıldı. Uygulama yalnızca ffmpeg ve ffprobe kullanır; ffplay taşınabilir ZIP paketine dahil edilmez. libjpeg-turbo arşivinden yalnızca gerekli çalıştırılabilir dosyalar, kütüphaneler ve belgeler kullanılır; sistem geneline kurulum yapılmamıştır.

Yerel çalışma için bütün bağımlılıklar pakete dahildir. Kaynaktan tekrar paketleme: `python -m pip install -r requirements-dev.txt`, ardından `Build.ps1`.
