; Origami — Inno Setup 安装脚本
; 用法: python build.py --installer

#define MyAppName "Origami"
#define MyAppNameCN "Origami - 多功能内容下载工具"
#define MyAppPublisher "Renxint"
#define MyAppURL "https://gitee.com/Renxint/origami"
#define MyAppExeName "Origami.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=dist_out
OutputBaseFilename={#MyAppName}_v{#MyAppVersion}_setup
SetupIconFile=app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName} v{#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppNameCN}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
WizardSizePercent=120,100
WizardResizable=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce

[InstallDelete]
; 升级时删除旧版本文件，但保留用户数据
Type: files; Name: "{app}\Origami.exe"
Type: files; Name: "{app}\Origami_v*.exe"
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\unins000.*"
; 不删: settings.json, data/, output/ — 用户数据保留

[Files]
Source: "dist_out\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "{#MyAppNameCN}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "{#MyAppNameCN}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 运行时生成的日志/临时文件（卸载时清理）
Type: files; Name: "{app}\_*.log"
Type: files; Name: "{app}\_*.txt"
Type: files; Name: "{app}\_*.png"
Type: files; Name: "{app}\_*.json"
Type: files; Name: "{app}\qt.conf"
Type: filesandordirs; Name: "{app}\_update"
; 保留: settings.json, output/ — 用户数据不删
