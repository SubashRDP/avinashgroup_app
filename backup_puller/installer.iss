; Inno Setup script for Avinash Backup Puller
; Builds BackupPullerSetup.exe, which installs backup_puller.exe and handles upgrade + uninstall.
;
; Build manually on Windows with:
;   ISCC.exe installer.iss
; CI builds it via .github/workflows/build-backup-puller.yml (Inno Setup 6 is preinstalled on the runner).

#define MyAppName "Avinash Backup Puller"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Raindrop"
#define MyAppExeName "backup_puller.exe"

[Setup]
; AppId is a stable GUID: Inno uses it to recognise an existing install for upgrades.
; Don't change this between versions; only change AppVersion.
AppId={{799F57C8-2F56-4A79-980D-20222A1F14C0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AvinashBackupPuller
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=BackupPullerSetup
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
; Per-user install, no admin needed. Settings live in %APPDATA%\AvinashBackupPuller
; and the API secrets are encrypted for this Windows user, so it is a per-user app anyway.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
CloseApplications=force
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousTasks=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Additional icons:"
Name: "autostart"; Description: "Start automatically when I sign in to Windows (recommended, so backups are pulled every hour)"; GroupDescription: "Auto-start:"

[Files]
Source: "..\dist\backup_puller.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--minimized"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Settings and the pulled-backup history in %APPDATA%\AvinashBackupPuller are kept on purpose.
; Backups on the hard disk / fallback folder are never touched.

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM backup_puller.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM backup_puller.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
