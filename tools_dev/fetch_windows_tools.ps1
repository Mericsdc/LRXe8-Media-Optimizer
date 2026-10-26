# Downloads the external tools the Windows build bundles into tools\ (they are
# too large for the Git repository). Run once on a fresh clone, then Build.ps1.
#   powershell -ExecutionPolicy Bypass -File tools_dev\fetch_windows_tools.ps1
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $root 'tools'
$temp = Join-Path $root 'build\downloads'
New-Item -ItemType Directory -Force -Path $tools, $temp | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Fetch([string]$url, [string]$name) {
    $file = Join-Path $temp $name
    if (-not (Test-Path -LiteralPath $file)) {
        Write-Output "İndiriliyor: $url"
        Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing
    }
    Write-Output ("  SHA-256 {0}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash)
    return $file
}

# FFmpeg 9.0.2 full build (libvmaf, x264, x265, SVT-AV1, NVENC) — Gyan.dev
if (-not (Test-Path "$tools\ffmpeg\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe")) {
    $zip = Fetch 'https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-full_build.zip' 'ffmpeg.zip'
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, "$tools\ffmpeg")
    Remove-Item "$tools\ffmpeg\ffmpeg-9.0.2-full_build\bin\ffplay.exe" -ErrorAction SilentlyContinue
}

# oxipng 10.2.1 — lossless PNG
if (-not (Test-Path "$tools\oxipng\oxipng-10.2.1-x86_64-pc-windows-msvc\oxipng.exe")) {
    $zip = Fetch 'https://github.com/oxipng/oxipng/releases/download/v10.2.1/oxipng-10.2.1-x86_64-pc-windows-msvc.zip' 'oxipng.zip'
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, "$tools\oxipng")
}

# ssimulacra2 from libjxl 0.12.0 — visually lossless photo check (only this tool + licences)
if (-not (Test-Path "$tools\jxl\ssimulacra2.exe")) {
    $zip = Fetch 'https://github.com/libjxl/libjxl/releases/download/v0.12.0/jxl-x64-windows-static.zip' 'jxl.zip'
    $archive = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        New-Item -ItemType Directory -Force -Path "$tools\jxl\licenses" | Out-Null
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName -eq 'x64-windows-static/bin/ssimulacra2.exe') {
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, "$tools\jxl\ssimulacra2.exe", $true)
            } elseif ($entry.FullName -like 'x64-windows-static/licenses/*' -and $entry.Name) {
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, "$tools\jxl\licenses\$($entry.Name)", $true)
            }
        }
    } finally { $archive.Dispose() }
}

# jpegtran is optional: MozJPEG (Python package) already does lossless JPEG optimisation.
# To add it, install libjpeg-turbo 3.2.0 (vc-x64) and copy bin\jpegtran.exe, jpeg62.dll, turbojpeg.dll to tools\jpeg\bin.
Write-Output "Araçlar hazır: $tools"
