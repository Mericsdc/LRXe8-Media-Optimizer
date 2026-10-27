param([string]$Python = "$PSScriptRoot\.venv\Scripts\python.exe", [switch]$NoZip, [switch]$NoInstaller)
# Builds the Windows EXE, replaces app\ in this folder (old app\ is kept in build\),
# then writes dist\LRXe8-Media-Optimizer-<version>-Kurulum.exe (Inno Setup) and a
# portable ZIP. tools\ (FFmpeg, oxipng, jpegtran, ssimulacra2) and assets\ must exist.
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$version = (Select-String -LiteralPath "$projectRoot\lrxe8\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Push-Location -LiteralPath $projectRoot
try {
    New-Item -ItemType Directory -Force -Path "$projectRoot\build" | Out-Null
    # Windows file properties ("Dosya sürümü") for the EXE.
    $parts = ($version.Split('.') + @('0', '0', '0'))[0..3] -join ', '
    @"
VSVersionInfo(ffi=FixedFileInfo(filevers=($parts), prodvers=($parts)), kids=[
  StringFileInfo([StringTable('041F04B0', [StringStruct('CompanyName', 'LRXe8'),
    StringStruct('FileDescription', 'LRXe8 Media Optimizer'), StringStruct('FileVersion', '$version'),
    StringStruct('ProductName', 'LRXe8 Media Optimizer'), StringStruct('ProductVersion', '$version'),
    StringStruct('OriginalFilename', 'LRXe8-Media-Optimizer.exe')])]),
  VarFileInfo([VarStruct('Translation', [0x041F, 1200])])])
"@ | Set-Content -LiteralPath "$projectRoot\build\version-info.txt" -Encoding ascii

    # The Real-ESRGAN extension is loaded by file path (no package import), so
    # PyInstaller cannot see it: add it explicitly; its DLL dependencies follow.
    $esrgan = & $Python -c "import importlib.util, pathlib; p = pathlib.Path(importlib.util.find_spec('realesrgan_ncnn_py').submodule_search_locations[0]); print(next(p.glob('realesrgan_ncnn_vulkan_wrapper*')))"
    if (-not (Test-Path -LiteralPath $esrgan)) { throw 'realesrgan-ncnn-py kurulu değil (pip install -r requirements.txt)' }
    # OpenSSL must be the one Python's _ssl.pyd was built against. Other programs on
    # PATH (PostgreSQL, Git) ship older libssl/libcrypto with the same file names;
    # PyInstaller once bundled those and the update check died with
    # "DLL load failed while importing _ssl". Search Python's DLLs first and add them explicitly.
    $pythonDlls = & $Python -c "import os, sys; print(os.path.join(sys.base_prefix, 'DLLs'))"
    $env:PATH = "$pythonDlls;$env:PATH"
    $openssl = @('libssl-3-x64.dll', 'libcrypto-3-x64.dll') | ForEach-Object { '--add-binary'; "$pythonDlls\$_;." }
    # PyInstaller logs to stderr; Windows PowerShell would turn that into errors.
    $ErrorActionPreference = 'Continue'
    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed --log-level WARN --name LRXe8-Media-Optimizer `
        --icon "$projectRoot\assets\icon.ico" --version-file "$projectRoot\build\version-info.txt" `
        --hidden-import _cffi_backend --collect-binaries mozjpeg_lossless_optimization `
        --collect-submodules mozjpeg_lossless_optimization `
        --add-binary "$esrgan;realesrgan_ncnn_py" --collect-data realesrgan_ncnn_py `
        --add-binary "$env:SystemRoot\System32\msvcp140.dll;realesrgan_ncnn_py" `
        --add-binary "$env:SystemRoot\System32\vcomp140.dll;realesrgan_ncnn_py" `
        --exclude-module cv2 --exclude-module numpy @openssl `
        --distpath "$projectRoot\build\dist" --workpath "$projectRoot\build\work" --specpath "$projectRoot\build" `
        "$projectRoot\launch.py" 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($code -ne 0) { throw "PyInstaller failed ($code)" }
    $built = Join-Path $projectRoot 'build\dist\LRXe8-Media-Optimizer'
    $app = Join-Path $projectRoot 'app'
    if (Test-Path -LiteralPath $app) {
        $backup = Join-Path $projectRoot ("build\app-before-$version-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
        Move-Item -LiteralPath $app -Destination $backup
        Write-Output "Previous app folder kept in $backup"
    }
    Copy-Item -LiteralPath $built -Destination $app -Recurse
    Write-Output "EXE ready: $app\LRXe8-Media-Optimizer.exe"
    New-Item -ItemType Directory -Force -Path "$projectRoot\dist" | Out-Null

    if (-not $NoInstaller) {
        $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                  "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $iscc) { throw 'Inno Setup 6 bulunamadı: winget install JRSoftware.InnoSetup --scope user' }
        $ErrorActionPreference = 'Continue'
        & $iscc /Q "/DAppVersion=$version" "$projectRoot\installer\LRXe8.iss" 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($code -ne 0) { throw "Inno Setup failed ($code)" }
        Write-Output "Installer ready: $projectRoot\dist\LRXe8-Media-Optimizer-$version-Kurulum.exe"
    }

    if (-not $NoZip) {
        $stage = Join-Path $projectRoot "build\package\LRXe8-Media-Optimizer-$version"
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $stage | Out-Null
        foreach ($item in 'app', 'tools', 'assets', 'licenses', 'Baslat.cmd', 'README.md', 'CHANGELOG.md', 'THIRD-PARTY.md', 'TEST-REPORT.md', 'LICENSE', 'NOTICE') {
            Copy-Item -LiteralPath (Join-Path $projectRoot $item) -Destination $stage -Recurse
        }
        $zip = "$projectRoot\dist\LRXe8-Media-Optimizer-$version-win64.zip"
        if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
        # Compress-Archive is slow and fragile with large binaries; use the .NET API directly.
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip, [IO.Compression.CompressionLevel]::Optimal, $true)
        Remove-Item -LiteralPath (Join-Path $projectRoot 'build\package') -Recurse -Force
        Write-Output "Portable ZIP ready: $zip"
    }
} finally {
    Pop-Location
}
