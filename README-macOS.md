# LRXe8 Media Optimizer — macOS

Uygulama macOS'ta da aynı arayüzle çalışır (Apple Silicon M1–M4 ve Intel, macOS 12 veya üstü). Mac uygulaması Mac üzerinde derlenir; Windows'ta Mac uygulaması üretilemez.

## Kurulum (tek komut)

1. `LRXe8-Media-Optimizer-<sürüm>-macOS-kaynak.zip` dosyasını Mac'e kopyalayıp açın.
2. **Terminal** uygulamasını açın, `cd ` yazıp açtığınız klasörü Terminal penceresine sürükleyin, Enter'a basın.
3. Şunu çalıştırın:

   ```bash
   bash build_macos.sh
   ```

Betik şunları kendisi yapar: Python 3.12'yi bulur (yoksa Homebrew ile kurar), Python paketlerini kurar, FFmpeg 9 (libvmaf, x265, SVT-AV1) ve oxipng'nin Mac sürümlerini indirip SHA-256 ile doğrular, uygulamayı derler, kendi testini çalıştırır ve `dist/LRXe8-Media-Optimizer-<sürüm>-macOS-arm64.dmg` dosyasını oluşturur. İlk çalıştırma internet hızına göre 5–15 dakika sürer.

4. DMG'yi açın ve **LRXe8 Media Optimizer**'ı **Applications (Uygulamalar)** klasörüne sürükleyin.

Uygulama sizin Mac'inizde derlendiği için Gatekeeper uyarısı çıkmaz. Başka bir Mac'e kopyalarsanız ilk açılışta sağ tık → **Aç** deyin.

## Mac'te farklı olanlar

| Özellik | Windows | macOS |
| --- | --- | --- |
| Video kodlama | NVIDIA ekran kartı (AV1/HEVC NVENC), gerekirse işlemci | İşlemci (SVT-AV1, x265). Aynı kalite doğrulaması; Apple Silicon'da hızlıdır ama ekran kartı kadar değil. |
| Yapay zekâ büyütme | NVIDIA/AMD/Intel ekran kartı (Vulkan) | Apple ekran kartı (Metal üzerinden Vulkan). Çalışmazsa klasik yöntemle büyütür ve bunu belirtir. |
| Fotoğraf "Daha küçük" modu | Hazır | `ssimulacra2` aracı betik tarafından kaynaktan derlenir (cmake gerekir; Homebrew varsa kendisi kurar). Derlenemezse bu mod kapalı olur, uygulamanın geri kalanı çalışır. |
| Kayıpsız JPEG | MozJPEG + jpegtran | MozJPEG |

Ayarlar Mac'te `~/Library/Preferences` altında saklanır; varsayılan çıktı klasörü `~/Movies/LRXe8 Optimized`.

## Sorun giderme

- **"Python 3.12 gerekli"**: https://www.python.org/downloads/macos/ adresinden Python 3.12 kurun veya Homebrew'u (https://brew.sh) kurup betiği tekrar çalıştırın.
- **İndirme hatası**: internet bağlantısını kontrol edip betiği tekrar çalıştırın; indirilen araçlar `build-mac/tools` içinde saklanır, tekrar indirilmez.
- **Paket testi başarısız**: `build-mac/selftest/.../self-test.json` dosyasındaki `error` alanı nedeni gösterir.
