; Inno Setup script for Avinash Backup Puller
; Builds BackupPullerSetup.exe, which installs backup_puller.exe and handles upgrade + uninstall.
;
; Build manually on Windows with:
;   ISCC.exe installer.iss
; CI builds it via .github/workflows/build-backup-puller.yml (Inno Setup 6 is preinstalled on the runner).

#define MyAppName "Avinash Backup Puller"
#define MyAppVersion "1.1.0"
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
; Admin: registers the background scheduled tasks, which run as SYSTEM so
; backups are pulled with no one signed in.
PrivilegesRequired=admin
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

[Dirs]
; Shared by the window (any user) and the SYSTEM background task.
Name: "{commonappdata}\AvinashBackupPuller"; Permissions: users-modify

[InstallDelete]
; 1.0.0 started its window at sign-in; the scheduled tasks replace that.
Type: files; Name: "{userstartup}\{#MyAppName}.lnk"

[Files]
Source: "..\dist\backup_puller.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Background pulls: every hour, and 2 minutes after every boot, as SYSTEM, so
; they run with the window closed and no one signed in. /F replaces the tasks
; on upgrade. A run still going when the next hour starts is left alone
; (Task Scheduler's default), and the app's own lock covers the rest.
Filename: "schtasks"; \
  Parameters: "/Create /TN ""{#MyAppName}"" /TR ""\""{app}\{#MyAppExeName}\"" --run-once"" /SC HOURLY /RU SYSTEM /RL HIGHEST /F"; \
  Flags: runhidden waituntilterminated
Filename: "schtasks"; \
  Parameters: "/Create /TN ""{#MyAppName} (Startup)"" /TR ""\""{app}\{#MyAppExeName}\"" --run-once"" /SC ONSTART /DELAY 0002:00 /RU SYSTEM /RL HIGHEST /F"; \
  Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "schtasks"; Parameters: "/Delete /TN ""{#MyAppName}"" /F"; Flags: runhidden; RunOnceId: "DelTask"
Filename: "schtasks"; Parameters: "/Delete /TN ""{#MyAppName} (Startup)"" /F"; Flags: runhidden; RunOnceId: "DelStartupTask"

[UninstallDelete]
; Settings and the pulled-backup history in %ProgramData%\AvinashBackupPuller are kept on purpose.
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
