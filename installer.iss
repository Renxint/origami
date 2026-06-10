; Origami — Inno Setup 安装脚本
; 用法: ISCC.exe installer.iss /DMyAppVersion=0.1.0

#define MyAppName "Origami"
#define MyAppNameCN "折纸"
#define MyAppPublisher "Renxint"
#define MyAppURL "https://gitee.com/Renxint/origami"
#define MyAppExeName "Origami.exe"

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
OutputDir=dist
OutputBaseFilename={#MyAppName}_v{#MyAppVersion}_setup
SetupIconFile=app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName} {#MyAppNameCN}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppNameCN} - 多功能内容下载工具
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce

[Files]
Source: "dist\{#MyAppName}_v{#MyAppVersion}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; VC++ 运行库（如需要）
; Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: VCRedistNeedsInstall

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "{#MyAppNameCN} - 多功能内容下载工具"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "{#MyAppNameCN} - 多功能内容下载工具"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}"
; 保留用户下载的数据，询问是否删除
Type: dirifempty; Name: "{userdocs}\OrigamiDownloads"

[Code]
function VCRedistNeedsInstall: Boolean;
begin
  Result := True;
end;
