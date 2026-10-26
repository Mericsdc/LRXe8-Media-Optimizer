# CODEX MASTER PROMPT — LRXe8 Media Optimizer

## Proje ve değişmez kurallar

Windows 11 üzerinde yerel çalışan profesyonel bir video/fotoğraf optimizasyon uygulaması geliştir. Kullanıcı dosyaları seçebilmeli, sürükleyip bırakabilmeli, kuyruğa alabilmeli, çıktı klasörü/kalite/codec ve eşzamanlılık seçebilmeli; gerçek işlem durumunu, tasarrufu, hata nedenini ve doğrulama raporlarını görebilmelidir.

Kaynak dosyalara yazma. Bütün adayları ayrı geçici çalışma alanında oluştur. Yalnızca bütün zorunlu kontrolleri geçen ve gerçekten daha küçük olan dosyayı benzersiz adla atomik olarak yayımla. Hata, desteklenmeme, iptal ve küçülmeme durumlarını başarıdan ayır. Tamamlanma durumu yalnızca FFmpeg çıkış koduna dayanmasın.

Önceden bir proje veya master prompt sağlanırsa onun mimarisini, kullanıcı arayüzünü, kalite modlarını, güvenlik ve test kurallarını koru; bu belgeyle çelişen yalnızca 4K'ya özgü video kurallarını evrenselleştir. Bu teslimde başlangıç kaynak kodu bulunmadığı için bağımsız ilk uygulama oluşturulmuştur.

## Evrensel video kapsamı

Çözünürlüğü bir sabit listeye sınırlandırma. Full HD 1920×1080, 2K 2048×1080, QHD 2560×1440, UHD 3840×2160, DCI 4K 4096×2160, 5K 5120×2880, 6K 6144×3160 ve diğer varyasyonları, 8K 7680×4320 ve codec sınırları içindeki özel boyutlar destek kapsamındadır. Gerçek genişlik/yüksekliği FFprobe ile algıla. Farklı en-boy oranlarını ve dikey videoları işle. Minimum kabul kuralını yön bağımsız uygula ve kullanıcıya açıkla; fotoğraflara uygulama.

Kaynak çözünürlüğü ve FPS değişmesin. Otomatik downscale, crop, padding ile görünen boyut değişikliği, kare düşürme/çoğaltma veya FPS düşürme yapma. VFR kaynağın gerçek kare gösterim zamanlarını koru. 29.97 gibi yuvarlanmış etiketler yerine 30000/1001 gibi rasyonel oranları ve gerçek PTS değerlerini kullan. Kaynak görünümünü korumadan döndürme metadata'sını piksellere uygulama.

Örnek koruma eşleştirmeleri: 1920×1080/30 → aynı; 2560×1440/60 → aynı; 3840×2160/60 → aynı; 5120×2880/30 → aynı; 7680×4320/60 → aynı. Codec/donanım desteklemediğinde yazılım seçeneği sun; hiçbir destekli yol yoksa nedenini açıkla ve orijinali koru.

## İçeriğe uyarlanabilir kodlama

Çözünürlük, FPS, kaynak bitrate, kaynak codec, görüntü ayrıntısı, hareket, SDR/HDR, kalite hedefi ve kodlayıcı verimliliğini birlikte değerlendir. 1080p ve 8K için tek bitrate/profil kullanma. Kalite odaklı CQ/CRF kodlama ve farklı sahnelerde örnek kodlamalar kullan. Kodlayıcılar arasında aynı sayısal kalite değerinin eşit kalite anlamına geldiğini varsayma.

Uyumluluk, dosya boyutu, kalite ve süreyi birlikte değerlendir. Küçük bir tahmini boyut avantajı için sınırsız hesaplama harcama; aday arama bütçesini görünür ve yapılandırılabilir tut. Seçilen kalite eşiğini düşürerek işi başarılı gösterme. Bütün dosyalarda küçülme veya küresel minimum dosya boyutu garantisi verme.

## Codec ve donanım

AV1 NVENC, HEVC NVENC, H.264 NVENC, SVT-AV1, libx265 ve libx264 yolları bulunsun. FFmpeg kodlayıcı listesi, kodlayıcının desteklediği piksel biçimleri ve kaynakla aynı boyut/bit derinliğinde gerçek kısa kodlama denemesi birlikte kullanılsın. Donanım model adından her çözünürlük/profil/codec kombinasyonunun desteklendiği sonucu çıkarılmasın.

Profil, bit derinliği, chroma, alpha, renk bilgileri, HDR ve container kısıtlarını kodlayıcı seçiminden önce/sonra denetle. Donanım desteklemezse seçili politika kapsamında yazılım yedeğine geç. Sonradan doğrulama hatası oluşursa diğer uygun adayları dene; sessiz çözünürlük veya kalite düşürme yapma.

## Tam çıktı doğrulaması

1. Kaynak ve çıktı genişlik/yüksekliği, SAR/DAR ve yön bilgisi aynı olmalı.
2. Kare sayısı, CFR/VFR zamanları, ortalama FPS ve son karenin süresi korunmalı. PTS'leri sunum sırasında karşılaştır; B-kareli videolarda DTS/paket süresini doğrudan gösterim aralığı sanma. Zaman tabanı yuvarlaması dışında tolerans tanıma; süreye oranlı geniş toleranslarla kayıp kare gizleme.
3. Video süresi ve ses/video/altyazı başlangıç ilişkileri korunmalı.
4. Ses akışları, dil/disposition, örnek hızı, kanal düzeni, bölümler, gerekli metadata ve ekler korunmalı. Akışların gerçekten kopyalandığını içerik hash'leriyle doğrula.
5. SDR/HDR, transfer fonksiyonu, renk primaries/matrix/range, bit derinliği, chroma konumu ve gerekli statik/dinamik HDR verisi istenmeden değişmemeli. Doğrulanamayan özel HDR yollarını açıkça reddet.
6. Uygun içerikte VMAF ve SSIM kullan. Model/çözünürlük/renk alanını raporla. Metrikleri piksel eşitliği veya algısal kusursuzluk garantisi sayma. Örnek ölçümü son çıktının tam ölçümü yerine koyma.
7. Son dosya gerçekten daha küçük olmalı ve kaynağın işlem başı/sonu SHA-256 değeri aynı kalmalı.

Eksik metrik, bozuk medya, başarısız decoder, yetersiz bellek/disk veya desteklenmeyen metadata olduğunda durum başarısız/korundu olarak açıkça raporlansın; doğrulama atlanarak tamamlandı denmesin.

## Performans ve kaynak sınırları

Hedef Windows 11, NVIDIA RTX 4080, AMD Ryzen 9, 32 GB RAM. Gerçek GPU/VRAM/boş RAM'i algıla; Laptop GPU ve masaüstü GPU'yu aynı kapasitede varsayma. 1080p, 1440p, 4K, 6K, 8K ve özel boyutlarda RAM/VRAM tampon tahmini yap. Yüksek çözünürlüklerde eşzamanlı işi azalt, işletim sistemi için rezerv bırak, CPU thread sınırı uygula. Yazılım yedeği daha büyük bellek bütçesi istemeli.

Tüm videoyu veya tüm frame JSON'unu RAM'e yükleme; kare zamanlarını ve metrikleri diske akıtarak karşılaştır. İptal ve zaman aşımı alt süreçleri gerçekten sonlandırmalı. Kaynak bekleme sonsuz sürmemeli. Çok yüksek çözünürlüklü yazılım kodlamanın ciddi süre/bellek gerektirebileceğini arayüz ve raporda belirt.

## Fotoğraf kuralları

Gerçek kayıpsız sıkıştırma varsayılan olsun. Bu modda kaynak çözünürlüğü, bütün piksel örnekleri, alpha, ICC ve gerekli metadata korunsun. 1080p minimumu fotoğraflara uygulanmasın. PNG, JPEG, WebP, HEIC, AVIF ve güvenli yolu bulunan diğer biçimleri işle. PNG filtrelerini ve güçlü sıkıştırmayı; JPEG baseline/progressive ve WebP efor adaylarını gerçek çıktı boyutuyla karşılaştır.

JPEG'i `quality=100` ile yeniden kaydederek kayıpsız sayma. HEIC/AVIF yüksek bit derinliğini 8 bit RGB karşılaştırmasıyla doğrulanmış sayma. Yeniden kodlama güvenli değilse kodlanmış görüntü ve metadata baytlarını değiştirmeyen container optimizasyonu kullan veya orijinali koru. Çıktı eşit/büyükse kaydetme. Doğrulama başarısızsa kayıplı yönteme geçme.

Kullanıcının 23 Ekim 2026 tarihli isteğiyle ayrıca **isteğe bağlı küçük dosya modu** sağla. Varsayılan kayıpsız moddan otomatik geçiş yapma. Bu modun kayıplı olduğunu belirt, hedef KB ve çıktı biçimi seçtir; kaynak çözünürlüğü/alpha/ICC ve gerekli metadata'yı doğrula. 8 bit SDR içerikte AVIF/WebP kalite adaylarını karşılaştır; RGB SSIM eşiği geçmeden çıktı kaydetme. Hedef boyut kaliteyle birlikte sağlanamıyorsa daha büyük sonucu açıkça bildir veya orijinali koru. Özgün biçime özel metadata'yı çıktı içinde arşivle; orijinal imzaları düzenlenmiş çıktıya geçerli imza olarak sunma. Her dosyada MB → KB garantisi verme.

## Arayüz ve güvenlik

Türkçe masaüstü arayüzü; dosya ekleme/sürükleme, çoklu dosya kuyruğu, kalite ve codec tercihleri, yazılım yedeği seçimi, kaynak sınırı, çıktı klasörü, aşama bilgisi, geçen süre, doğrulanmış tasarruf ve raporlara erişim sağla. Ağ yüklemesi yapma. Shell string birleştirme kullanmadan dış süreçleri argüman listeleriyle başlat. Kaynak veya mevcut çıktıları silme/üzerine yazma. İşe özel geçici alan kullan.

Normal işlemlerde çıktı klasörüne yalnızca küçülen medya dosyası bırak. Otomatik rapor/log/yan dosya üretme; ayrıntıları bellekte tutup uygulamada göster. İptal ve hatada geçici adayları temizle. Birebir aynı çıktı varsa tekrar dosya oluşturma; farklı mevcut dosyayı koru. Kullanıcının çalışan video motorunu koru; fotoğraf geliştirmesi için video kodlama/kalite ayarlarını değiştirme.

## Test ve teslim

Çözünürlük test matrisi örnek listedeki tüm boyutları, en az bir dikey ve özel boyutu içersin. CFR, kesirli FPS, VFR, B-kareleri, çoklu ses, sessiz video, SDR, HDR, desteklenmeyen codec/profil, bozuk dosya, iptal, yetersiz kaynak, metadata kaybı, çıktı büyümesi ve dosya adı çakışmasını sınayacak testler kur.

Fotoğraflarda küçük çözünürlük, alpha altındaki RGB, ICC/EXIF/XMP, palette/bit derinliği, HEIC/AVIF içerik koruma ve yeniden optimizasyonun dosyayı büyütmemesi test edilsin. Gerçek FFmpeg entegrasyonu ile birim testlerini ayır. Donanıma özgü denemeleri sürücü/araç sürümüyle raporla. Kısa sentetik testleri uzun gerçek medya üzerinde genel güvenilirlik kanıtı olarak sunma.

Çalıştırılabilir Windows paketi, kaynak kodları, bağımlılık sürümleri, testler, kullanım belgesi, doğrulama raporu ve açık destek sınırları teslim et. Uygulanmamış veya test edilmemiş bir özelliği tamamlanmış gibi gösterme.
