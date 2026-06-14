; Origami — Inno Setup 安装脚本
; 用法: python build.py --installer
; 前置: 先装 Inno Setup 6 → https://jrsoftware.org/isdl.php

#define MyAppName "Origami"
#define MyAppNameCN "Origami - 多功能内容下载工具"
#define MyAppPublisher "Renxint"
#define MyAppURL "https://gitee.com/Renxint/origami"
#define MyAppExeName "Origami_v0.3.1.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
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
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppNameCN}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
; 深色主题安装向导
WizardSizePercent=120,100
WizardResizable=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce

[Files]
Source: "dist_out\{#MyAppName}_v{#MyAppVersion}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "{#MyAppNameCN}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "{#MyAppNameCN}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_update"
Type: filesandordirs; Name: "{app}\settings.json"
; 用户下载内容保留不删（在输出目录中）
