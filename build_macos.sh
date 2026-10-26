#!/usr/bin/env bash
# LRXe8 Media Optimizer — macOS derlemesi (.app + .dmg).
# Mac'te bu klasörde çalıştırın:   bash build_macos.sh
# Apple Silicon (M1–M4) ve Intel, macOS 12+. İnternet bağlantısı gerekir (araçlar indirilir).
# Sonuç: dist/LRXe8-Media-Optimizer-<sürüm>-macOS-<mimari>.dmg
set -euo pipefail
cd "$(dirname "$0")"
VERSION=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' lrxe8/__init__.py)
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then FFARCH=arm64; OXIARCH=aarch64; else FFARCH=amd64; OXIARCH=x86_64; fi
WORK=build-mac
TOOLS="$PWD/$WORK/tools"
APP_NAME="LRXe8 Media Optimizer"
mkdir -p "$WORK" "$TOOLS"
say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mHATA: %s\033[0m\n' "$*"; exit 1; }

say "LRXe8 Media Optimizer $VERSION · macOS $(sw_vers -productVersion) · $ARCH"

# ------------------------------------------------------------------ Python 3.12
say "Python 3.12"
PY=""
for candidate in python3.12 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 \
                 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12; do
  if command -v "$candidate" >/dev/null 2>&1; then PY=$(command -v "$candidate"); break; fi
done
if [ -z "$PY" ]; then
  if command -v brew >/dev/null 2>&1; then
    brew install python@3.12
    PY="$(brew --prefix)/bin/python3.12"
  else
    fail "Python 3.12 gerekli. https://www.python.org/downloads/macos/ adresinden kurun (veya Homebrew: https://brew.sh) ve tekrar çalıştırın."
  fi
fi
"$PY" -m venv "$WORK/venv"
# shellcheck disable=SC1091
source "$WORK/venv/bin/activate"
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements-mac.txt
# Only the compiled Real-ESRGAN module and its models are used; skip OpenCV/NumPy.
python -m pip install -q --no-deps realesrgan-ncnn-py==2.0.0

# ------------------------------------------------------------------ FFmpeg
say "FFmpeg 9 (libvmaf, x265, SVT-AV1, x264) · martin-riedl.de statik derlemesi"
if [ ! -x "$TOOLS/ffmpeg/ffmpeg" ] || [ ! -x "$TOOLS/ffmpeg/ffprobe" ]; then
  page=$(curl -fsSL https://ffmpeg.martin-riedl.de/)
  dir=$(printf '%s' "$page" | grep -oE "/download/macos/$FFARCH/[0-9]+_9\.[0-9.]+/" | head -1 || true)
  if [ -z "$dir" ] && [ "$FFARCH" = "arm64" ]; then dir="/download/macos/arm64/1789931890_9.0.2/"; fi
  [ -n "$dir" ] || fail "FFmpeg 9 indirme adresi bulunamadı (https://ffmpeg.martin-riedl.de)."
  mkdir -p "$TOOLS/ffmpeg"
  for prog in ffmpeg ffprobe; do
    curl -fsSL -o "$WORK/$prog.zip" "https://ffmpeg.martin-riedl.de${dir}${prog}.zip"
    expected=$(curl -fsSL "https://ffmpeg.martin-riedl.de${dir}${prog}.zip.sha256" | awk '{print $1}')
    actual=$(shasum -a 256 "$WORK/$prog.zip" | awk '{print $1}')
    [ "$expected" = "$actual" ] || fail "$prog.zip SHA-256 doğrulaması başarısız."
    unzip -o -q "$WORK/$prog.zip" -d "$TOOLS/ffmpeg"
  done
fi
chmod +x "$TOOLS/ffmpeg/ffmpeg" "$TOOLS/ffmpeg/ffprobe"
xattr -dr com.apple.quarantine "$TOOLS/ffmpeg" 2>/dev/null || true
"$TOOLS/ffmpeg/ffmpeg" -hide_banner -filters 2>/dev/null | grep -q libvmaf || fail "Bu FFmpeg'de libvmaf yok."
for encoder in libx265 libsvtav1 libx264; do
  "$TOOLS/ffmpeg/ffmpeg" -hide_banner -encoders 2>/dev/null | grep -q "$encoder" || fail "Bu FFmpeg'de $encoder yok."
done
"$TOOLS/ffmpeg/ffmpeg" -hide_banner -version | head -1

# ------------------------------------------------------------------ oxipng
say "oxipng 10.2.1 (kayıpsız PNG)"
if [ ! -x "$TOOLS/oxipng/oxipng" ]; then
  name="oxipng-10.2.1-$OXIARCH-apple-darwin"
  curl -fsSL -o "$WORK/oxipng.tar.gz" "https://github.com/oxipng/oxipng/releases/download/v10.2.1/$name.tar.gz"
  rm -rf "$WORK/oxipng-extract" && mkdir -p "$WORK/oxipng-extract" "$TOOLS/oxipng"
  tar -xzf "$WORK/oxipng.tar.gz" -C "$WORK/oxipng-extract"
  cp "$(find "$WORK/oxipng-extract" -type f -name oxipng | head -1)" "$TOOLS/oxipng/oxipng"
fi
chmod +x "$TOOLS/oxipng/oxipng"
xattr -dr com.apple.quarantine "$TOOLS/oxipng" 2>/dev/null || true
"$TOOLS/oxipng/oxipng" --version

# ------------------------------------------------------------------ ssimulacra2 (optional)
say "ssimulacra2 (fotoğrafta 'Daha küçük' modu için; isteğe bağlı)"
if [ ! -x "$TOOLS/jxl/ssimulacra2" ]; then
  if command -v brew >/dev/null 2>&1; then brew install cmake libpng jpeg-turbo >/dev/null || true; fi
  if command -v cmake >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
    ( rm -rf "$WORK/libjxl" "$WORK/libjxl-build" &&
      git clone -q --depth 1 --branch v0.12.0 --recurse-submodules --shallow-submodules \
          https://github.com/libjxl/libjxl.git "$WORK/libjxl" &&
      cmake -S "$WORK/libjxl" -B "$WORK/libjxl-build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
          -DBUILD_SHARED_LIBS=OFF -DJPEGXL_ENABLE_DEVTOOLS=ON -DJPEGXL_ENABLE_BENCHMARK=OFF \
          -DJPEGXL_ENABLE_EXAMPLES=OFF -DJPEGXL_ENABLE_MANPAGES=OFF -DJPEGXL_ENABLE_SJPEG=OFF \
          -DJPEGXL_ENABLE_OPENEXR=OFF -DJPEGXL_ENABLE_JPEGLI=OFF -DJPEGXL_ENABLE_DOXYGEN=OFF >/dev/null &&
      cmake --build "$WORK/libjxl-build" --target ssimulacra2 -j "$(sysctl -n hw.ncpu)" >/dev/null &&
      mkdir -p "$TOOLS/jxl" &&
      cp "$(find "$WORK/libjxl-build" -type f -name ssimulacra2 -perm -u+x | head -1)" "$TOOLS/jxl/ssimulacra2" &&
      cp "$WORK/libjxl/LICENSE" "$TOOLS/jxl/LICENSE.libjxl" ) ||
      echo "  ssimulacra2 derlenemedi: 'Daha küçük' fotoğraf modu bu Mac'te kapalı olur; diğer her şey çalışır."
  else
    echo "  cmake/git yok (Homebrew ile: brew install cmake). 'Daha küçük' fotoğraf modu kapalı olur."
  fi
fi

# ------------------------------------------------------------------ app bundle
say "Uygulama paketleniyor (PyInstaller)"
rm -rf "$WORK/dist" "$WORK/work"
# The Real-ESRGAN extension is loaded by file path, so PyInstaller must be told about it.
ESRGAN=$(python -c "import importlib.util, pathlib; p = pathlib.Path(importlib.util.find_spec('realesrgan_ncnn_py').submodule_search_locations[0]); print(next(p.glob('realesrgan_ncnn_vulkan_wrapper*')))")
[ -f "$ESRGAN" ] || fail "realesrgan-ncnn-py modülü bulunamadı."
python -m PyInstaller --noconfirm --clean --windowed --log-level WARN --name "$APP_NAME" \
  --icon "$PWD/assets/icon.icns" --osx-bundle-identifier com.lrxe8.mediaoptimizer \
  --add-data "$TOOLS:tools" --add-data "$PWD/assets:assets" \
  --hidden-import _cffi_backend --collect-binaries mozjpeg_lossless_optimization \
  --collect-submodules mozjpeg_lossless_optimization \
  --add-binary "$ESRGAN:realesrgan_ncnn_py" --collect-data realesrgan_ncnn_py \
  --exclude-module cv2 --exclude-module numpy \
  --distpath "$WORK/dist" --workpath "$WORK/work" --specpath "$WORK" "$PWD/launch.py"
APP="$WORK/dist/$APP_NAME.app"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$APP/Contents/Info.plist"
plutil -replace CFBundleVersion -string "$VERSION" "$APP/Contents/Info.plist"
plutil -replace NSHumanReadableCopyright -string "LRXe8" "$APP/Contents/Info.plist"
# Ad-hoc signature (required for arm64 binaries; no Apple developer account needed).
codesign --force --deep --sign - "$APP"

say "Paket testi (fotoğraflar, kısa video, arayüz)"
rm -rf "$WORK/selftest"
if "$APP/Contents/MacOS/$APP_NAME" self-test --output "$WORK/selftest"; then
  echo "  Paket testi geçti."
else
  echo "  Paket testi başarısız; ayrıntı: $(find "$WORK/selftest" -name self-test.json | head -1)"
  exit 1
fi

# ------------------------------------------------------------------ dmg
say "DMG oluşturuluyor"
STAGE="$WORK/dmg"
rm -rf "$STAGE" && mkdir -p "$STAGE" dist
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="dist/LRXe8-Media-Optimizer-$VERSION-macOS-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -quiet -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
say "Hazır: $DMG"
echo "Açın ve uygulamayı Applications (Uygulamalar) klasörüne sürükleyin."
