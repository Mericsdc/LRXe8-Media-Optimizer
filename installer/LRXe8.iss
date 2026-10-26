; LRXe8 Media Optimizer — Windows kurulum betiği (Inno Setup 6.7+).
; Derleme: Build.ps1 (app\ klasörünü üretir, sonra bu betiği ISCC ile derler).
; Yönetici izni gerekmez: varsayılan olarak kullanıcının kendi klasörüne kurar.

#ifndef AppVersion
  #define AppVersion "2.1.0"
#endif
#define AppName "LRXe8 Media Optimizer"
#define AppExe "LRXe8-Media-Optimizer.exe"
#define Root ".."

[Setup]
AppId={{4DE744A8-E82E-43B1-BAE4-3C3E824F8A84}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=LRXe8
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Kurulum
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#Root}\dist
OutputBaseFilename=LRXe8-Media-Optimizer-{#AppVersion}-Kurulum
SetupIconFile={#Root}\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern dark
WizardImageFile=wizard-100.bmp,wizard-250.bmp
WizardSmallImageFile=small-100.bmp,small-250.bmp
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
; Compress in a separate 64-bit process: the 32-bit compiler runs out of memory on FFmpeg.
LZMAUseSeparateProcess=yes
CloseApplications=yes
; Tell Explorer to refresh icons: an update keeps the same EXE path, so Windows
; would otherwise keep showing the previous version's cached logo.
ChangesAssociations=yes
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Messages]
turkish.WelcomeLabel2=Bu sihirbaz [name/ver] uygulamasını bilgisayarınıza kuracak.%n%nVideo ve fotoğrafları kaliteyi bozmadan küçültür. Her şey bu bilgisayarda işlenir; orijinal dosyalarınız asla değiştirilmez.%n%nYönetici izni gerekmez.

[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Kısayollar:"

[InstallDelete]
; Güncellemede eski Python/Qt çalışma dosyaları kalmasın.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Root}\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\tools\*"; DestDir: "{app}\tools"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Root}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Root}\THIRD-PARTY.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "Video ve fotoğrafları kaliteyi bozmadan küçült"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{#AppName} uygulamasını şimdi aç"; Flags: nowait postinstall skipifsilent
; In-app updates run the installer with /SILENT: reopen the app when it is done.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
