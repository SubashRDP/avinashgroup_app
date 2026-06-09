; Inno Setup script for K40 Bridge
; Builds K40BridgeSetup.exe which installs k40_bridge.exe + handles upgrade + uninstall.
;
; Build manually on Windows with:
;   ISCC.exe installer.iss
; CI builds it via .github/workflows/build-exe.yml (Inno Setup 6 is preinstalled on the runner).

#define MyAppName "K40 Bridge"
#define MyAppVersion "1.0.5"
#define MyAppPublisher "Raindrop"
#define MyAppExeName "k40_bridge.exe"

[Setup]
; AppId is a stable GUID — Inno uses it to recognise an existing install for upgrades.
; Don't change this between versions; only change AppVersion.
AppId={{B7D2A9F4-3E5C-4F12-9D8B-6A1C5E0F7A3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\K40Bridge
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=K40BridgeSetup
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
; Force close any running k40_bridge.exe before overwriting (upgrade path)
CloseApplications=force
RestartApplications=no
; Show "Setup found a previous version" page on upgrade
UsePreviousAppDir=yes
UsePreviousTasks=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Additional icons:"
Name: "autostart"; Description: "Start K40 Bridge automatically when Windows boots"; GroupDescription: "Auto-start:"

[Files]
Source: "..\dist\k40_bridge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\K40 Bridge"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall K40 Bridge"; Filename: "{uninstallexe}"
Name: "{autodesktop}\K40 Bridge"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Register the Task Scheduler entry (auto-start at boot + restart on failure)
; Done via schtasks for simplicity. Runs only if the user kept the "autostart" task ticked.
Filename: "schtasks"; \
  Parameters: "/Create /TN ""K40 Bridge"" /TR ""\""{app}\{#MyAppExeName}\"" --background"" /SC ONSTART /RL HIGHEST /F"; \
  Flags: runhidden waituntilterminated; \
  Tasks: autostart

; Launch the bridge after install. Two entries on purpose:
;   1. Silent path  → always relaunch (no flags). Used by self-update from
;      inside the running bridge, where /SILENT skips postinstall items.
;   2. Wizard path  → checkbox on Finished page for interactive installs.
Filename: "{app}\{#MyAppExeName}"; \
  Parameters: "--background"; \
  Flags: nowait runascurrentuser; \
  Check: WizardSilent

Filename: "{app}\{#MyAppExeName}"; \
  Description: "Launch K40 Bridge now"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove the Task Scheduler entry on uninstall
Filename: "schtasks"; Parameters: "/Delete /TN ""K40 Bridge"" /F"; \
  Flags: runhidden; RunOnceId: "DelTask"

[UninstallDelete]
; Don't auto-delete the user's config folder — they may have credentials/data they want to keep.
; If you want to remove EVERYTHING, uncomment the line below:
; Type: filesandordirs; Name: "{userappdata}\K40Bridge"

[Code]
// Stop the running bridge before installing (in case CloseApplications=force misses the tray icon)
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM k40_bridge.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM k40_bridge.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
