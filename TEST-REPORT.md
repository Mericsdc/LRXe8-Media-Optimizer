# Doğrulama raporu

## 2.2.0 — 26 Ekim 2026 · yapay zekâ ile büyütme, yeni logo, macOS

**Otomatik testler: 84 geçti** (yeni: hedef boyut hesapları, klasik ve yapay zekâ fotoğraf büyütme, büyük fotoğrafın korunması, sesli kısa videonun hem klasik hem yapay zekâ ile uçtan uca büyütülmesi; AV1 bit hızı tavanı).

Gerçek dosyalarla yapay zekâ büyütme (RTX 4080 Laptop, Vulkan):

| Dosya | Önce | Sonra | Model | Süre | Orijinalle tutarlılık |
| --- | --- | --- | --- | ---: | --- |
| Yeni logo (WebP) | 1254×1254 | 5016×5016 (4 kat) | çizim modeli | 13 sn | PSNR 30,8 dB |
| WhatsApp JPEG | 1600×1200 | 2880×2160 (4K) | fotoğraf modeli | 12,7 sn | PSNR 26,7 dB |
| Blue Polygons kesiti, sesli (1080p25, 3 sn) | 1920×1080 | 3840×2160 | video modeli 2× | 92 sn | VMAF 99,6 · PSNR 39,0 dB |
| 0_3d_Model_Abstract (720p25, 15 sn, 376 kare) | 1280×720 | 3840×2160 | video modeli 3× | 184 sn | VMAF 92,7 · PSNR 32,4 dB |

Videolarda 4K çıktı, büyütülmüş karelere göre de doğrulandı (1080p kesit: AV1 10-bit, VMAF 98,65, en kötü %2 97,17, bantlanma artışı 0); kare sayısı birebir, ses örnekleri aynı.

Bulunan ve düzeltilen hata: kayıpsız ara dosya gibi çok yüksek bit hızlı kaynaklarda AV1 NVENC, tavan 800 Mbit/s iken kalite ayarını yok sayıyordu (bütün CQ değerlerinde 365 Mbit/s; CQ 26 ve CQ 44 aynı 47.141.985 bayt). Tavan çözünürlüğe uygun seviyeyle (4K30 için 100, 4K60 için 160 Mbit/s) sınırlanınca CQ yeniden etkili oldu (CQ 26 → 5,3 MB, CQ 44 → 1,3 MB / 1 sn). Ayrıca derlenmiş Real-ESRGAN modülünün EXE'ye girmediği paket testinde yakalandı; modül ve çalışma zamanı DLL'leri açıkça eklendi, paket testi artık Windows'ta yapay zekâ çalışmazsa başarısız sayıyor.

Paketlenmiş uygulama (taşınabilir ZIP ayrı klasöre açılarak): `self-test` geçti (yapay zekâ çizim modeliyle büyütme dahil); komut satırından 1080p sesli klip 4K'ya (5,2 MB, tutarlılık VMAF 99,55) ve logo 4K'ya (2160×2160, PSNR 30,9 dB) büyütüldü, çıkış kodu 0. Arayüz gerçek işle sürüldü: "Büyüt" seçiliyken video ve logo büyütüldü, ilerleme "Yapay zekâ ile büyütülüyor → Büyütülen video sıkıştırılıyor → Görüntü kalitesi kare kare doğrulanıyor → Orijinalle içerik ve ses karşılaştırılıyor" sırasıyla hiç geri gitmeden ilerledi.

**macOS:** Kod Mac'e uyarlandı (paket içi araç/simge yolları, Finder'da gösterme, Movies klasörü, Mac yazı tipleri, NVENC olmadan yazılım kodlama, eksik araçlarda açık neden). `build_macos.sh` sözdizimi denetlendi; kullandığı bütün Python paketlerinin Apple Silicon sürümleri ve FFmpeg 9.0.2 (libvmaf, x265, SVT-AV1 dahil) ile oxipng Mac indirmeleri doğrulandı. Mac uygulaması bu Windows bilgisayarında derlenemediği ve çalıştırılamadığı için **Mac'te henüz test edilmedi**; betik derlemenin sonunda paket testini Mac'te kendisi çalıştırır.

## 2.1.0 — 26 Ekim 2026 · yeni arayüz ve kurulum dosyası

**Otomatik testler: 78 geçti** (yeni: sade durum metinleri ve ilerleme sırası, arama adımı sayacı, "korundu" açıklamaları, klasör bırakma ve desteklenmeyen dosya filtresi, sonuç kartları ve özet).

Arayüz gerçek bir işle uçtan uca sürüldü: bir klasör bırakıldı (3 sn 1080p video + logo PNG), iki dosya da bulundu, durum satırları sırayla "Hazırlanıyor → Dosya inceleniyor → Sahneler analiz ediliyor → Kodlayıcı hazırlanıyor · AV1 · ekran kartı → En uygun kalite ayarı aranıyor · deneme 1–5 → Video sıkıştırılıyor → Kareler, zamanlama ve ses kontrol ediliyor → Görüntü kalitesi kare kare doğrulanıyor" oldu, ilerleme hiç geri gitmedi. Sonuç: video 12,4 MB → 2,9 MB (VMAF 98,4), logo 318 KB → 199 KB (kayıpsız); özet "Bitti · 2 küçültüldü · 9,6 MB kazanıldı".

Kurulum dosyası `LRXe8-Media-Optimizer-2.1.0-Kurulum.exe` (155,6 MB, Inno Setup 6.7.3, LZMA2): sessiz kullanıcı kurulumu 16 sn'de tamamlandı (çıkış 0). Kayıt defterinde "LRXe8 Media Optimizer 2.1.0" kaldırma girdisi ve Başlat menüsü kısayolu oluştu. Kurulan EXE'nin `self-test`'i geçti: FFmpeg ve ssimulacra2 kurulum klasöründen bulundu, 2 sn video AV1 10-bit VMAF 98,5, görsel kayıpsız AVIF SSIMULACRA2 95,4. Sessiz kaldırma (çıkış 0) klasörü, kayıt defteri girdisini ve Başlat menüsü kısayolunu tamamen sildi.

## 2.0.0 — 26 Ekim 2026 · büyük dosyalar, bantlanma, ImageOptim seviyesi fotoğraf

Ortam: Windows 11, RTX 4080 Laptop (12 GB, sürücü 621.01), 32 GB RAM, Python 3.12.15, FFmpeg 9.0.2, oxipng 10.2.1, MozJPEG (mozjpeg-lossless-optimization 1.3.2), libjxl 0.12.0 ssimulacra2.

**Otomatik testler: 74 geçti.** Yeni regresyon testleri: 10-bit hedef biçimleri, bit derinliğinin yalnızca artabilmesi, 4:2:2'de chroma konumu, NVENC bit hızı tavanı ve HEVC level seçimi, MOV'da AV1 atlanması, bantlanma/renk kalite kapısı, kare hizasına denk gelmeyen örnekte kare eşleştirme (gerçek FFmpeg), kuyruktaki işin 90 sn'den uzun beklemesi, opak RGBA → RGB kayıpsız indirgeme, metadata temizleme (ICC + yön korunur), progressive taramalar arasındaki JPEG yorumu. Sonuç: `verification/v2-pytest-results.xml`.

### Bulunan sorunlar (eski 1.1.1 ile gerçek dosyalarda ölçüldü)

| Sorun | Kanıt |
| --- | --- |
| Çıktılarda bantlanma | Kullanıcının önceki çıktılarında CAMBI 7,5–17,5 (ör. balık animasyonu 17,5; parçacıklar 15,5; gün batımı 10,3). 5 üstü gözle görülür. SSIM/VMAF bunu yakalamıyordu. Aynı CQ'da 8-bit AV1 CAMBI'yi 0,16 → 1,6 yaparken 10-bit 0,25'te kaldı ve %16 daha küçüktü. |
| HEVC NVENC gizli tavan | `-b:v 0` ile 4K60'ta CQ 8, 14, 22 hepsi aynı 8.792.492 bayt (≈35 Mbit/s). CQ yok sayılıyor, kalite tavana takılıyordu. |
| 4:2:2 MJPEG/ProRes başarısız | `Gold Low Poly Background 4K.mov` (882 MB, yuvj422p): 6 dk kodlama sonrası "chroma_location korunmadı: center → None/left". |
| Örnek ölçümünde yanlış eşleşme | Kare hizasına denk gelmeyen kesimde her 3 karede bir VMAF 92 (komşu kareyle karşılaştırma); CQ 10'da bile "kalite yetmedi". |
| MOV'da AV1 | FFmpeg 9: "av1 only supported in MP4 and AVIF". |
| Kuyruk | İkinci büyük iş 90 sn bekleyince "Yeterli RAM/VRAM sağlanamadı". |
| Fotoğraf | WhatsApp JPEG'i "metadata_exact False" ile başarısız; 178 MP üstü fotoğraf açılamıyordu; küçük dosya modu RGB SSIM 0,970 ile görünür kayba izin veriyordu. |

### Gerçek videolar (kaynaktan, 2 paralel iş, "Görsel kayıpsız" + Otomatik)

| Dosya | Kaynak | Çıktı | Küçülme | Kodlayıcı | VMAF ort. / en kötü %2 | PSNR Y | Bantlanma (kaynak → çıktı) | Süre |
| --- | ---: | ---: | ---: | --- | --- | ---: | --- | ---: |
| abstract-dark-wavy-flowing (4K60 H.264 MOV) | 569.848.337 | 14.865.485 | %97,4 | HEVC NVENC 10-bit | 98,46 / 97,97 | 51,1 dB | 0,14 → 0,05 | 305 sn |
| abstract-dark-wavy-undulating (4K60 MOV) | 759.240.202 | 12.912.970 | %98,3 | HEVC NVENC 10-bit | 98,66 / 97,71 | 52,8 dB | 0,18 → 0,09 | 373 sn |
| Gold Low Poly (4K30 MJPEG 4:2:2 tam aralık) | 882.470.858 | 45.174.093 | %94,9 | x265 10-bit 4:2:2 | 100 / 100 | 51,9 dB | 0,42 → 0,76 (algılanamaz) | 405 sn |
| Blue Polygons (1080p25 H.264 MOV) | 405.108.829 | 40.889.256 | %89,9 | HEVC NVENC 10-bit | 99,99 / 100 | 44,1 dB | 3,88 → 0,75 | 109 sn |
| glowing-blue-particle (4K60 H.264 MP4, 87 Mbit/s) | 108.721.329 | 102.549.187 | %5,7 | AV1 NVENC 10-bit | 98,44 / 96,65 | 54,5 dB | 14,4 → 3,5 | 275 sn |
| 3d_Model_Abstract (720p, 5 Mbit/s) | 9.529.543 | — | korundu | — | görsel kayıpsız için 17–30 MB gerekirdi | — | — | 135 sn |

Bütün çıktılarda kare sayısı ve her PTS kaynakla birebir aynı (maksimum zamanlama farkı 0 sn), çözünürlük/FPS/renk aralığı korundu, `ffmpeg -xerror` ile baştan sona hatasız çözüldü. HEVC çıktıları `hvc1` etiketli Main 10 (4:2:2'de Rext); 4K60 için level 5.1 yazılır. Kaynakların SHA-256 değeri değişmedi. Koyu dalgalı videoda kare 300 piksel karşılaştırması: yeni çıktı PSNR 47,7 dB (eski 1.1.1 çıktısı 23,5 MB ile 48,2 dB) — %37 daha küçük, aynı sadakat, bantlanma yok.

Kalite eşiği ilk denemede VMAF ≥ 97 idi; koyu arka plan dokusunda 5× parlaklık artırımında hafif yumuşama görüldüğü için varsayılan VMAF ≥ 98 / en kötü %2 ≥ 96 yapıldı (dosya 9,0 MB → 14,9 MB). Bantlanma kuralı Netflix CAMBI ölçeğine göre ayarlandı: çıktının kendi bantlanması algılanamaz düzeydeyse (< 1) küçük artışlar hata sayılmaz.

### Fotoğraflar

Kayıpsız (varsayılan), kullanıcının 14 gerçek dosyası, hepsi doğrulandı (piksel + metadata birebir):

| Dosya | Önce | Sonra | Küçülme |
| --- | ---: | ---: | ---: |
| LRXe8 logo.png | 325.280 | 203.903 | %37,3 |
| Minimalist Beyaz X8ngine Logosu.png | 349.217 | 225.991 | %35,3 |
| 4c65ee62….png (opak RGBA → RGB indirgeme) | 813.423 | 471.504 | %42,0 |
| Yeni Proje (1).png | 192.197 | 143.317 | %25,4 |
| Fütüristik Veri Merkezi….png | 1.679.391 | 1.464.523 | %12,8 |
| M-E.png | 2.062.658 | 1.808.424 | %12,3 |
| ChatGPT görselleri (3 adet) | 1,88–2,28 MB | | %5,3–8,2 |
| WhatsApp JPEG (eskiden hata) | 254.833 | 251.004 | %1,5 |
| HR8Zn2paAAA8nEg.jpg | 62.507 | 60.461 | %3,3 |

Logo dosyalarında ~23 KB'lık C2PA (`caBX`) metadata'sı varsayılan olarak korunur. "Görünmeyen metadata'yı sil" seçeneğiyle logo 325.280 → 180.237 bayt (%44,6) oldu; ICC, yön ve pikseller aynı kaldı. Büyük dosyalar: 182 MP / 275,5 MB PNG → 232,1 MB (%15,8, eskiden açılamıyordu); 50 MP JPEG 7,27 → 6,11 MB.

Görsel kayıpsız küçültme (SSIMULACRA2 ≥ 90): ChatGPT PNG 2.276.518 → 377.133 bayt AVIF (%83,4, skor 90,3; 1.1.1'in 273.857 baytlık sonucu bu ölçekte ~86–87 idi, yani görünür kayıplıydı). Alpha'lı logo → 88.800 bayt WebP (skor 90,6). Zaten sıkıştırılmış WhatsApp JPEG'i görsel kayıpsız kalitede küçülmediği için korundu.

Ayrıntılı kayıtlar: `verification/v2/` (makineye özgü yollar maskelendi).

### Paketlenmiş EXE

`app\LRXe8-Media-Optimizer.exe self-test`: araçlar (ffmpeg, ffprobe, jpegtran, oxipng, ssimulacra2) ve MozJPEG modülü paket içinden yüklendi; PNG/JPEG/WebP kayıpsız, HEIC/AVIF korundu, 2 sn 1080p video AV1 NVENC 10-bit VMAF 98,5 ile doğrulandı, görsel kayıpsız AVIF SSIMULACRA2 95,4; arayüz pencere açmadan çizildi.

Son EXE ile komut satırından gerçek dosyalar (2 paralel iş, çıkış kodu 0): Blue Polygons 405.108.829 → 41.077.700 bayt (HEVC Main 10, level 4.1, VMAF 100); koyu dalgalı 4K60 759.240.202 → 12.912.970 bayt (HEVC Main 10, level 5.1, VMAF 98,7); parçacıklı 4K60 MP4 108.721.329 → 102.549.187 bayt (AV1 10-bit, VMAF 98,4); 720p dosya 41 sn'de korundu (verimli codec kaynaktan küçük çıkaramayınca daha az verimli codec'ler denenmez); logo, ChatGPT PNG, WhatsApp JPEG ve 50 MP JPEG kayıpsız doğrulandı. Kayıt: `verification/v2/exe-final-report.json`.

### Sınırlar

Video yeniden kodlaması her zaman kayıplıdır; VMAF/CAMBI/PSNR algısal ve sayısal ölçülerdir, piksel eşitliği garantisi değildir. Eşikler sıkı tutulur ve her karede uygulanır. Zaten verimli sıkıştırılmış kaynaklar (telefon videoları, düşük bit hızlı web videoları) görsel kayıpsız kalitede çoğu zaman küçülmez; bu durumda orijinal korunur. 4:2:2 kaynaklar RTX 40 NVENC'te kodlanamadığı için yazılımla (x265) daha yavaş işlenir. Alfa kanallı, taramalı ve dinamik HDR/Dolby Vision videolar güvenli yol olmadan dönüştürülmez.

## Önceki sürümler — 23 Ekim 2026

## 1.1.1 — Unicode VMAF yolu ve MOV uyumluluğu

**61 test geçti (16,16 saniye).** Türkçe/boşluk/kesme işareti/köşeli parantez/virgül içeren klasör ve kaynak adlarında gerçek SSIM/VMAF ölçümü geçti. Eşzamanlı iki ölçümün çalışma klasörleri birbirinden bağımsız kaldı. Ölçüm dosyası oluşturulmadığında eski sonuçların kullanılmadığı ve açık hata verildiği denetlendi. Sonuç: `verification/vmaf-path-pytest-results.xml`.

MOV'daki ayrı timecode akışının farklı oluşturma tarihi, FFmpeg yeniden kodlamasından sonra özgün yerel header alanlarına geri aktarıldı. Testte dosya boyutu değişmedi; değişen baytların yalnızca tarih alanlarında olduğu doğrulandı. Frame başına bir tick kullanan 1/25 kaynak saati, 1/12800 çıktı saatiyle kayıpsız karşılaştırıldı; PTS sapması ve son kareyi bir kare uzatma negatif testlerde reddedildi.

Gerçek `Blue Polygons Backdrop II.mov` dosyası, kullanıcının **D: sürücüsündeki Türkçe adlı çıktı klasöründe** tamamlandı: 405.108.829 → 64.029.684 bayt, **%84,2 küçülme**. 1920×1080, 25 FPS, 600 kare, 24 saniye ve maksimum PTS farkı 0 saniye. SSIM 0,991962; VMAF 99,994201. Timecode paketi hash'i, ayrı akış tarihleri ve bütün zorunlu kontroller geçti. Orijinal SHA-256 değişmedi. Çıktı klasörüne yalnızca MOV yazıldı; rapor/log kalmadı. Ayrıntılar: `verification/blue-polygons-1.1.1.json`.

Kurulu 1.1.1 EXE, ayrıca Türkçe ve filtergraph noktalama işaretleri içeren bir klasöre videoyu başarıyla işledi. Paket/Qt/fotoğraf kısa testi de geçti. Codec ayarları ve kalite eşikleri düşürülmedi; ölçüm yolu ve MOV metadata/zaman tabanı doğrulama uyumluluğu düzeltildi.

## 1.1.0 — temiz çıktı ve fotoğraf geliştirmesi

**51 test geçti (12,18 saniye).** Kayıpsız PNG/16 bit/palet/alpha/ICC testleri, güçlü refiltering, küçük AVIF/WebP, EXIF/XMP/özel metadata, alpha koruması, kalite nedeniyle hedef boyutun aşılması, aynı çıktının yeniden kullanılabilmesi, hata/iptalde boş kalan klasör ve rapor yan dosyası üretilmemesi doğrulandı. Sonuç: `verification/photo-update-pytest-results.xml`.

Gerçek kullanıcı fotoğrafı: PNG, 1069×1472, 2.276.518 bayt. Yeni gerçek kayıpsız sonuç: 2.113.868 bayt (%7,1 küçülme, piksel ve metadata kontrolü geçti). Kullanıcının ayrıca onayladığı küçük dosya modunda sonuç: **273.857 bayt AVIF (~267 KB, %88 tasarruf)**. RGB SSIM 0,970224, kalite 82; boyut değişmedi. 256 KB hedefi kalite sınırı nedeniyle 11,4 KB aşıldı ve uygulama bunu açıkça belirtti. Bu sonuç kayıplıdır; piksel eşitliği iddiası yoktur.

Kaynak PNG'deki 23.654 baytlık özel `caBX` metadata'sı çıktı içindeki UUID/LRXM arşivinde baytlarıyla korundu. Arşivlenen imza verisi kaynak içindir; yeni görüntüye geçerli bir özgünlük imzası olarak sunulmaz. ICC/EXIF/XMP, uygun içerikte kendi yerel alanlarında ayrıca doğrulanır.

Kurulu **1.1.0 EXE**, aynı gerçek fotoğrafı arka arkaya iki kez işledi. İki çalışma da başarılı oldu; klasörde yalnızca **bir AVIF** kaldı. Otomatik JSON/log veya geçici klasör kalmadı. Paket kısa testi AVIF, PNG, JPEG, WebP, HEIF ve Qt arayüzüyle geçti. Uygulama içi ayrıntı penceresi dosya üretmeden açıldı; fotoğraf hedefi/biçimi yalnızca küçük dosya modu seçilince etkinleşti.

`video.py` ve `probe.py`, 1.0.1 kaynak arşiviyle bayt düzeyinde karşılaştırıldı ve aynı bulundu. Video kodlama/analiz/kalite ayarları değiştirilmedi. Önceki video testleri aşağıda tarihsel kayıt olarak korunur; fotoğraf değişikliği için uzun video tekrar kodlanmadı.

## 1.0.1 regresyon kontrolü

**44 test geçti (3,49 saniye).** Önceki 26 teste 18 `creation_time` testi eklendi. Dosya/video/ses akışı düzeyinde yinelenen eşit tarihler kabul edildi. Saat dilimi ve yazım farkları aynı zaman anı olarak karşılaştırıldı; eksik, geçersiz, çelişkili ve gerçekten değişmiş tarihler reddedildi. Saniyenin milyarda biri düzeyindeki değişim de hata verdi. Diğer metadata alanlarında tam eşitlik şartı korundu.

Gerçek FFmpeg ile tarih metadata'sı içeren bir MP4 yeniden kodlandı; MP4/MOV mdta yoluyla dönen değerler ve ses/video tarihleri doğrulandı. Sonuçlar `verification/creation-time-pytest-results.xml` içindedir. Aşağıdaki ilk sürüm kayıtları tarihsel test sonuçlarıdır.

Kullanıcının hata veren gerçek videosu da **1.0.1 EXE** üzerinden aynı Dengeli/Otomatik seçenekleriyle baştan sona işlendi. 108.721.329 → 53.575.168 bayt (%50,7 küçülme), 3840×2160 / 60 FPS, 600 kare / 10 saniye; maksimum PTS farkı 0 saniye. SSIM 0,993841, SSIM alt %5 0,9916, VMAF 4K 94,381973. Ses hash'leri, metadata ve bütün zorunlu kontroller geçti. `creation_time` çıktıda yinelenmiş olsa da bütün değerler kaynakla aynı tarihi gösterdi. Kaynak dosyanın SHA-256 değeri değişmedi. Sonuç: `verification/creation-time-actual-video.json`.

Yeni EXE'nin kurulu masaüstü uygulamasıyla ve yeniden çıkarılan paketle çalışması ayrıca kısa paket testiyle denetlenir. Masaüstü başlatıcısı 1.0.1 EXE'ye yönlendirildi; önceki EXE ve `Baslat-1.0.0.cmd` yedek olarak korundu.

Bu kayıtlar Windows üzerinde gerçekten çalıştırılan testlere aittir. Medya girdileri kısa, sentetik test desenleridir; tasarruf oranları gerçek kullanıcı videoları için tahmin değildir.

## Ortam

Windows x64, 32 GB sistem belleği, NVIDIA RTX 4080 Laptop GPU (~12 GB VRAM), sürücü 617.42. Python 3.12.14, FFmpeg 9.0.2, PySide6 6.8.3. Paket ayrı bir Python kurulumu kullanmadan sınandı.

## Otomatik testler

**26 test geçti (2,20 saniye).** VFR/PTS sapması, düşen/çoğaltılan kare, FPS değişimi, HDR metadata kaybı/çelişkisi, piksel derinliği, RAM nedeniyle eşzamanlılık azaltma, iptal, hatalı dosya, atomik ad çakışması, küçük PNG/alpha/ICC/metin/palet/16 bit, WebP görünmez RGB, HEIC/AVIF dolgu temizliği ve büyük/eşit çıktının korunması denetlendi. Ayrıntılar: `verification/pytest-results.xml`.

## Donanım yetenek testi

Her kombinasyonda gerçek boyutlarda 60 FPS girişten 3 kare kodlandı. Bu kısa yetenek testi uzun süreli performans veya kalite ölçümü değildir.

| Çözünürlük | AV1 NVENC | HEVC NVENC | H.264 NVENC |
| --- | --- | --- | --- |
| 1920 × 1080 | Geçti | Geçti | Geçti |
| 2048 × 1080 | Geçti | Geçti | Geçti |
| 2560 × 1440 | Geçti | Geçti | Geçti |
| 3840 × 2160 | Geçti | Geçti | Geçti |
| 4096 × 2160 | Geçti | Geçti | Geçti |
| 5120 × 2880 | Geçti | Geçti | Donanım reddetti |
| 6144 × 3160 | Geçti | Geçti | Donanım reddetti |
| 7680 × 4320 | Geçti | Geçti | Donanım reddetti |
| 1080 × 1920 | Geçti | Geçti | Geçti |
| 2222 × 1112 | Geçti | Geçti | Geçti |

30 denemenin 27’si desteklendi. H.264 NVENC 5K, 6K ve 8K girişleri reddetti; bu beklenen donanım sınırı hata olarak gizlenmedi. 5K H.264 tam işleminde otomatik libx264 yedeği ayrıca başarıyla çalıştı.

## Baştan sona medya doğrulaması

| Test | Kodlayıcı | Kaynak → çıktı (bayt) | Tasarruf | SSIM | VMAF |
| --- | --- | ---: | ---: | ---: | ---: |
| vfr-h264_nvenc | h264_nvenc | 5,145,037 → 1,523,030 | %70.4 | 0.998205 | 97.060 |
| 8k-av1-av1_nvenc | av1_nvenc | 24,244,593 → 4,659,662 | %80.8 | 0.996067 | Uygulanmadı |
| 5k-h264-fallback-libx264 | libx264 | 10,658,985 → 1,648,329 | %84.5 | 0.993975 | Uygulanmadı |
| hdr10-hevc_nvenc | hevc_nvenc | 2,702,733 → 561,130 | %79.2 | 0.999157 | Uygulanmadı |
| fractional-two-audio-rotation-h264_nvenc | h264_nvenc | 4,511,922 → 1,222,723 | %72.9 | 0.998703 | 97.959 |
| frozen-auto-av1_nvenc | av1_nvenc | 4,511,922 → 1,061,986 | %76.5 | 0.998530 | 98.150 |
| source-1080p-libsvtav1 | libsvtav1 | 4,535,195 → 901,825 | %80.1 | 0.997594 | 97.139 |
| source-1080p-libx265 | libx265 | 4,535,195 → 946,049 | %79.1 | 0.996715 | 96.075 |

- VFR: 36 kare, 1,5 saniye; bütün PTS değerleri korundu.
- 8K: 7680×4320, 30 FPS, 12 kare; tam çözünürlüklü SSIM ve kare doğrulaması geçti.
- 5K yedek: 5120×2880, 30 FPS, 12 kare; H.264 NVENC reddinden sonra libx264 geçti.
- HDR10: 1920×1080, 10 bit PQ/BT.2020, 12 kare; mastering display ve MaxCLL/MaxFALL korundu.
- Kesirli FPS testi: 30000/1001 FPS, 30 kare, 1,001 saniye; iki AAC ses akışı, dil etiketleri, bölüm bilgisi ve 90° döndürme korundu.
- Hazır EXE: otomatik codec araması AV1 NVENC’i seçti; aynı kesirli FPS/ses/metadata testinden çıkış kodu 0 ile geçti.
- Bütün bu videolarda ölçülen en büyük PTS sapması **0 saniye** oldu.

## Fotoğraf ve paket

320×180 alpha/ICC/metin içeren PNG 231.147 → 975 bayt; JPEG 1.616 → 910 bayt oldu. Çözülmüş pikseller ve ilgili metadata aynı kaldı. Zaten küçük WebP, HEIC ve AVIF örnekleri orijinal korundu durumuyla sonuçlandı. HEIC/AVIF’in sıfır dolgulu son kutularını kaldırma yolu ayrıca otomatik testte piksel ve bayt korumasıyla sınandı.

Paket içindeki EXE kendi PNG, JPEG, WebP, HEIC ve AVIF örneklerini üretti ve işledi; Qt arayüzü pencere açılmadan görüntüye işlendi. Sonuç `verification/frozen-self-test.json`, görüntü `verification/preview.png`.

## Yeniden çalıştırma

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python tests/integration_manual.py --work D:/LRXe8-tests --large --matrix
app/LRXe8-Media-Optimizer.exe self-test --output D:/LRXe8-package-test
```

`integration_manual.py` boş bir test klasörü ister. Standart 1080p otomatik codec testi bu betikle de tekrar çalıştırıldı. `--large` ve `--matrix` seçenekleri süreyi ve bellek ihtiyacını artırır; kullanılan GPU’ya göre destek sonuçları değişebilir.

## Sınırlar

Uzun gerçek dünya 6K/8K videoları, bütün HDR profilleri, her codec/container birleşimi ve tüm sürücü sürümleri sınanmadı. 8K yazılım kodlama için süre/bellek garantisi verilmez. Dinamik HDR/Dolby Vision, çoklu ana video ve taramalı video güvenli doğrulama yolu olmadan kabul edilmez. HEIC/AVIF görüntü yeniden kodlaması yapılmaz; yalnızca güvenle kaldırılabilen dolgu küçültülür. SSIM/VMAF, videoda piksel eşitliği veya bütün algısal kalite boyutları için garanti değildir.

Kaynak dosyalar değiştirilmedi. Raporlardaki makineye özgü çalışma klasörü `<TEST_WORKSPACE>` olarak maskelendi. Test girdileri ve ara dosyalar dağıtım paketine dahil edilmedi.
