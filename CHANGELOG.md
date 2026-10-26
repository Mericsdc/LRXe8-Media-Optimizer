# Değişiklikler

## 2.2.1 — 26 Ekim 2026

- **Uygulama içi güncelleme:** sağ üstte "Güncellemeleri denetle". GitHub Releases'teki en son sürümü kontrol eder; yeni sürümü indirir, boyutunu ve SHA-256 değerini doğrular, uygulamayı kapatıp sessizce günceller ve yeniden açar (Mac'te DMG'yi açar). İnternet yalnızca bu düğmeye basınca kullanılır.
- **Buy me a beer** butonu (buymeacoffee.com/Lurexa) uygulamada ve README'de.
- Güncellemeden sonra masaüstü kısayolunun eski logoyu göstermesi giderildi: kurulum artık Windows'a simgeleri yenilemesini bildirir (EXE yolu aynı kaldığı için Windows önbellekteki eski simgeyi gösteriyordu).
- Kaynak kod GitHub'da: https://github.com/Mericsdc/LRXe8-Media-Optimizer. Temiz kopyada araçları indirmek için `tools_dev/fetch_windows_tools.ps1`.

## 2.2.0 — 26 Ekim 2026

**Büyüt / netleştir (yeni):** Üstteki "Ne yapılsın?" seçiminde **Büyüt**: fotoğraf ve videoları yapay zekâ (Real-ESRGAN) ile büyütür ve netleştirir.

- Hedef: **4K'ya** (video 3840×2160; fotoğraf 4K sınırına), **2 kat** veya **4 kat**. Görüntü türü: **Fotoğraf / video** (gerçek çekim modeli) veya **Çizim / logo** (çizim modeli).
- Videolar hızlı video modeliyle kare kare büyütülür (1080p → 4K, RTX 4080'de kare başına ~0,2 sn), kayıpsız ara dosyaya yazılır, ardından normal doğrulamalı kodlayıcıdan geçer: 4K çıktının kalitesi her karede VMAF + bantlanma ile doğrulanır; ses birebir kopyalanır, kare sayısı ve zamanlama korunur.
- Her sonuç orijinal boyuta küçültülüp orijinalle karşılaştırılır; içeriği bozan bir büyütme kaydedilmez.
- Fotoğraflar biçimini korur (JPEG → JPEG kalite 95 4:4:4 + bütün metadata; WebP → kayıpsız WebP; diğerleri → kayıpsız PNG). Renk profili ve EXIF korunur.
- Yapay zekâ ayrı bir alt süreçte çalışır: ekran kartı/sürücü sorunu uygulamayı kapatmaz, **Durdur** anında işler. Ekran kartı yapay zekâyı çalıştıramazsa klasik Lanczos ile büyütülür ve bu açıkça yazılır. "Gelişmiş ayarlar"dan klasik yöntem de seçilebilir.
- Çıktılar `ad.upscaled-4k.mp4`, `ad.upscaled-2x.png` gibi ayrı adlarla kaydedilir.

**Yeni logo ve siyah tema:** Uygulama simgesi, kurulum sihirbazı ve başlık yeni LRXe8 logosuyla değişti. Arayüz saf siyah zemin ve logodaki mavi tonlarla yeniden renklendirildi.

**macOS:** Aynı uygulama Mac'te de çalışır. `build_macos.sh` Mac'te tek komutla .app ve .dmg üretir (bkz. `README-macOS.md`). Mac'te video işlemciyle (SVT-AV1/x265) kodlanır, yapay zekâ Apple ekran kartında çalışır.

**Düzeltmeler:**
- AV1 NVENC, bit hızı tavanı seviye sınırının üstündeyken (ör. kayıpsız/çok yüksek bit hızlı kaynaklar) kalite ayarını yok sayıyordu (CQ 26 ve CQ 44 aynı boyut). AV1 tavanı artık HEVC gibi çözünürlüğe uygun seviyeyle sınırlı.
- Mac paketinde araçlar ve simgeler uygulama paketinin içinden bulunur; jpegtran ve ssimulacra2 yoksa ilgili özellik açık bir nedenle devre dışı kalır.

## 2.1.0 — 26 Ekim 2026

**Kurulum dosyası:** `dist\LRXe8-Media-Optimizer-2.1.0-Kurulum.exe`. Çift tıklayınca Türkçe kurulum sihirbazı açılır; yönetici izni gerekmez (kullanıcının `AppData\Local\Programs` klasörüne kurar). Başlat menüsü ve isteğe bağlı masaüstü kısayolu oluşturur, Windows "Uygulamalar" listesinden kaldırılabilir. FFmpeg ve diğer araçlar dahildir; ayrıca bir şey kurmak gerekmez. Taşınabilir ZIP de ayrıca üretilir.

**Yeni arayüz:**

- Açılışta büyük bir bırakma alanı: dosya veya **klasör** sürükle-bırak, ya da "Dosya seç". Desteklenmeyen dosyalar sessizce atlanır ve sayısı gösterilir.
- Her dosya için ayrı kart: tür etiketi (VİDEO/FOTO), anlaşılır Türkçe durum ("En uygun kalite ayarı aranıyor", "Görüntü kalitesi kare kare doğrulanıyor · %40"), kendi ilerleme çubuğu, sonuçta "386 MB → 39 MB" ve kazanç rozeti, "Klasörde göster" düğmesi.
- Yalnızca iki basit seçim: **Video kalitesi** (En iyi kalite / Yüksek kalite / Küçük dosya) ve **Fotoğraflar** (Kayıpsız / Daha küçük). Codec, paralel iş, fotoğraf biçimi, hedef KB ve metadata temizleme "Gelişmiş ayarlar" penceresinde; seçimler hatırlanır.
- Ayrıntı penceresi: VMAF, bantlanma, kodlayıcı, süre ve geçen kontroller sade bir listede; ham teknik rapor isteğe bağlı.
- Bitmiş dosyalar listede kalır; "Başlat" yalnızca yeni eklenenleri işler. Kapatırken işlem sürüyorsa onay sorulur.
- EXE dosya özelliklerinde sürüm bilgisi görünür.

Video ve fotoğraf motoru 2.0.0 ile aynıdır.

## 2.0.0 — 26 Ekim 2026

Gerçek büyük dosyalarla (405–882 MB, 4K60, ProRes/MJPEG 4:2:2) yapılan testlerde bulunan bütün sorunlar giderildi.

**Video — "bozarak tamamlıyor" sorunları**

- Önceki çıktılarda koyu gradyanlarda belirgin **bantlanma** vardı (CAMBI 8–17; 5 üstü gözle görülür). SSIM/VMAF bunu görmüyordu. Artık her kare CAMBI ile ölçülür; çıktının kaynağa göre algılanabilir bantlanma eklemesi reddedilir.
- AV1 ve HEVC artık 8-bit kaynaklarda da **10-bit** kodlanır. Aynı ayarda %11–16 daha küçük dosya ve bantlanmasız sonuç verir. H.264 uyumluluk için kaynak bit derinliğinde kalır. Bit derinliği hiçbir zaman düşürülmez.
- **HEVC NVENC gizli bit hızı tavanı** giderildi: `-b:v 0` ile sürücü 4K60'ta ~35 Mbit/s'e takılıyor ve düşük CQ değerlerini yok sayıyordu (CQ 8 ile CQ 22 aynı boyut). Açık `maxrate/bufsize` ve high tier kullanılır.
- Kalite kapısı yenilendi: tam videoda **VMAF ort. ≥ 98 ve en kötü %2 kare ≥ 96** (varsayılan "Görsel kayıpsız"), 1080p modelinde kaynağın kendi tavanına göre normalize; renk düzlemleri için chroma PSNR kontrolü. SSIM'in VMAF 99,8 olan videoları yanlışlıkla reddetmesi sona erdi.
- Örnek sahne ölçümünde kareler zaman damgasıyla eşleşiyordu; kare hizasına denk gelmeyen kesimlerde (MKV 1 ms yuvarlaması) her 3 kareden biri komşusuyla karşılaştırılıyordu. Kareler artık sırayla eşleşir; tam zamanlama ayrıca birebir doğrulanır.
- CQ/CRF değeri ikili aramayla bulunur (en zor sahneler + en düz/bantlanmaya yatkın sahne). Tam doğrulama geçmezse kalite kademeli artırılarak yeniden denenir.

**Video — "yapamıyor" sorunları**

- 4:2:2 kaynaklarda (MJPEG/ProRes) chroma konumu yanlış karşılaştırılıyordu: 6 dakikalık kodlamadan sonra "chroma_location korunmadı" hatası. 4:2:2/4:4:4'te bu alan bitstream'de yazılamaz; yalnızca 4:2:0'da karşılaştırılır.
- Her kodlayıcı önce 8 karelik gerçek çözünürlük denemesiyle sınanır; desteklenmeyen biçim/renk sinyali saniyeler içinde anlaşılır, uzun kodlamadan sonra değil.
- FFmpeg MOV içine AV1 yazmadığı için MOV kaynaklarda AV1 atlanır (HEVC kullanılır).
- Kuyruktaki ikinci büyük dosya, ilki 90 saniyeden uzun sürünce "Yeterli RAM/VRAM sağlanamadı" hatasıyla düşüyordu. Artık sırasını bekler.
- 1080p altı videolar (ör. 720p) reddediliyordu; bütün çözünürlükler desteklenir.
- Kodlama ve kalite ölçümü sırasında yüzde ilerleme gösterilir.

**Fotoğraf — ImageOptim seviyesi**

- Kayıpsız PNG: oxipng ile renk tipi/bit derinliği/palet indirgeme (ör. tamamen opak RGBA → RGB), metadata kaynaktan birebir. Zopfli yalnızca küçük görsellerde (büyük dosyada 50 sn yerine 4–9 sn).
- Kayıpsız JPEG: MozJPEG + jpegtran, en küçüğü seçilir. Progressive taramalar arasındaki yorum işaretçileri artık yanlışlıkla "metadata kaybı" sayılmaz (WhatsApp JPEG'i bu yüzden başarısız oluyordu).
- Çok büyük fotoğraflar (178 MP üstü) "decompression bomb" hatası vermez.
- İsteğe bağlı **"Görünmeyen metadata'yı sil (ImageOptim gibi)"**: kamera/GPS, XMP, yorum, C2PA silinir; ICC renk profili, sRGB/gamma, DPI ve EXIF yön bilgisi her zaman korunur. Örnek: logo 325 KB → 180 KB.
- "Küçük dosya" modu **görsel kayıpsız** oldu: eski RGB SSIM ≥ 0,970 eşiği gözle görülür kayba izin veriyordu. Her aday SSIMULACRA2 ile ölçülür, yalnızca ≥ 90 kaydedilir. AVIF 4:4:4, JPEG 4:4:4 (MozJPEG) veya alpha için WebP. Hedef KB kalite için gerekirse aşılır; kalite asla düşürülmez.

## 1.1.1 — 23 Ekim 2026

- Windows'ta Türkçe/Unicode klasör adlarında `vmaf.json` dosyasının oluşmaması düzeltildi. Her FFmpeg sürecine ayrı çalışma klasörü ve ASCII ölçüm dosyası adları verilir; uygulamanın genel çalışma klasörü değiştirilmez.
- Eski ölçüm dosyaları yeni ölçümden önce kaldırılır. SSIM/VMAF dosyası oluşmazsa eski sonuç kullanılmaz ve açık doğrulama hatası gösterilir.
- MOV/MP4 akışlarının birbirinden farklı yerel oluşturma/değiştirme tarihleri korunur. FFmpeg'in timecode akışının tarihini dosya tarihiyle değiştirmesi giderilir; yalnızca sabit genişlikli tarih alanları düzeltilir, medya verisi ve zamanlama alanları değiştirilmez.
- Kare başına bir tick kullanan özgün MOV saatleri, daha hassas çıktı saatiyle doğru karşılaştırılır. Kaynağın kaba saati çıktıdaki PTS sapmasını veya son karenin uzamasını gizleyemez.
- Video codec, çözünürlük/FPS, sıkıştırma ve kalite eşikleri ile fotoğraf modları değiştirilmedi. Normal çıktılara rapor/log eklenmez.

## 1.1.0 — 23 Ekim 2026

- Normal işlerde otomatik rapor/log dosyası kaldırıldı; çıktı klasörüne yalnızca doğrulanmış medya bırakılır. Ayrıntılar uygulama içinde açılır.
- Aynı işi tekrar çalıştırınca birebir aynı çıktı varsa yeniden kopya üretilmez; farklı mevcut dosyalar korunur.
- PNG için oxipng/Zopfli refiltering, JPEG için baseline/progressive karşılaştırması ve WebP için daha yüksek kayıpsız sıkıştırma eforu eklendi.
- Gerçek kayıpsız fotoğraf modu varsayılan kalır. Kullanıcı isteğiyle ayrı, kayıplı küçük dosya modu eklendi: hedef KB, otomatik AVIF/WebP ve kalite kontrolü.
- Kaynak çözünürlük, alpha ve metadata doğrulanır. Biçime özel metadata çıktının içine arşivlenir; yan dosya üretilmez. Hedef boyut kalite nedeniyle aşılırsa açıkça belirtilir.
- Video kodlama/analiz/doğrulama motoru değişmedi; `video.py` ve `probe.py` 1.0.1 ile bayt düzeyinde aynıdır.

## 1.0.1 — 23 Ekim 2026

- MP4/MOV çıktılarında `creation_time` hem standart tarih alanından hem mdta metadata'sından okununca FFprobe aynı tarihi `tarih;tarih` biçiminde bildirebiliyor. Doğrulayıcı artık bütün değerlerin aynı zaman anını gösterdiğini denetliyor.
- Saat dilimi ve eşdeğer kesirli saniye yazımları doğru karşılaştırılıyor. Eksik, geçersiz, çelişkili veya gerçekten değişmiş tarihler kabul edilmiyor. Kesirli saniyeler yuvarlanmıyor.
- Diğer metadata alanları tam karşılaştırılmaya devam ediyor. Çözünürlük, FPS, ses, HDR ve kalite kontrolleri aynı kalıyor.
- Tekrarlanan aynı doğrulama hatası son mesajda bir kez gösteriliyor. Gerçek metadata hatalarında kaynak/çıktı değeri ve ilgili akış belirtiliyor.
- Pencere başlığında sürüm numarası gösteriliyor.

Bu düzeltme için 18 yeni regresyon testi eklendi; toplam 44 test geçti.
