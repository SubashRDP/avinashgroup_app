; Inno Setup script for Avinash Print Bridge
; Builds PrintBridgeSetup.exe — installs print_bridge.exe + upgrade + uninstall,
; the same shape as K40BridgeSetup.exe.
;
; Build manually on Windows with:
;   ISCC.exe installer.iss
; CI builds it via .github/workflows/build-print-bridge.yml (Inno Setup 6 is
; preinstalled on the runner).
;
; Replaces QZ Tray for raw ESC/P printing. Nothing to download at run time, no
; signing certificate, no override.crt — see print_bridge.py for why none of
; that is needed once the agent answers to one origin.

#define MyAppName "Avinash Print Bridge"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Raindrop"
#define MyAppExeName "print_bridge.exe"
; Every origin the ERP is served at. Production first, then the test sites.
; Keep in lockstep with DEFAULT_ORIGINS in print_bridge.py — the agent enforces
; the allow-list, these keys only suppress Chrome 142+'s local-network prompt.
#define ErpOrigin "https://ng-group.raindropinc.com"
#define TestOrigin1 "https://avinaslive1.raindropinc.com"
#define TestOrigin2 "https://sandboxavinas-demo.raindropinc.com"
#define TestOrigin3 "https://avinasdemo.raindropinc.com"

[Setup]
; AppId is a stable GUID — Inno uses it to recognise an existing install for
; upgrades. Don't change this between versions; only change AppVersion.
; Distinct from K40 Bridge's GUID: these are separate products.
AppId={{9C4E1B7A-2D68-4A35-B0F1-8E7C3A9D2F64}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AvinashPrintBridge
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=PrintBridgeSetup
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
; admin: the browser policy is HKLM and Add-Printer needs elevation.
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
Name: "autostart"; Description: "Start Print Bridge automatically at login"; GroupDescription: "Auto-start:"

[Files]
Source: "..\dist\print_bridge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
; Chrome 142 gates loopback requests behind the Local Network Access permission.
; Pre-granting the ERP origin means the user never sees that prompt. Declarative
; here rather than in Python so uninstall reverses it (uninsdeletevalue).
;
; Without these keys printing still works — Chrome just asks once and remembers.
; That is a real permission, unlike QZ Tray's prompt, which returned every
; session because the requests were never signed.
Root: HKLM; Subkey: "SOFTWARE\Policies\Google\Chrome\LocalNetworkAccessAllowedForUrls"; \
  ValueType: string; ValueName: "1"; ValueData: "{#ErpOrigin}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\Policies\Google\Chrome\LocalNetworkAccessAllowedForUrls"; \
  ValueType: string; ValueName: "2"; ValueData: "{#TestOrigin1}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\Policies\Google\Chrome\LocalNetworkAccessAllowedForUrls"; \
  ValueType: string; ValueName: "3"; ValueData: "{#TestOrigin2}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\Policies\Google\Chrome\LocalNetworkAccessAllowedForUrls"; \
  ValueType: string; ValueName: "4"; ValueData: "{#TestOrigin3}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\Policies\Microsoft\Edge\LocalNetworkAccessAllowedForUrls"; \
  ValueType: string; ValueName: "1"; ValueData: "{#ErpOrigin}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\Policies\Microsoft\Edge\LocalNetworkAccessAllowedForUrls"; \
  ValueType: string; ValueName: "2"; ValueData: "{#TestOrigin1}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\Policies\Microsoft\Edge\LocalNetworkAccessAllowedForUrls"; \
  ValueType: string; ValueName: "3"; ValueData: "{#TestOrigin2}"; Flags: uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\Policies\Microsoft\Edge\LocalNetworkAccessAllowedForUrls"; \
  ValueType: string; ValueName: "4"; ValueData: "{#TestOrigin3}"; Flags: uninsdeletevalue
; Firefox needs nothing: it exempted loopback from mixed content in 55 and has
; never shipped Local Network Access.

[Run]
; The LQ310-RAW queue is created from CurStepChanged below, not here — it needs
; the exit code checked, and running it in both places would do it twice.

; Register the login task (agent must run as the logged-in user — it serves the
; browser on that user's desktop session).
Filename: "schtasks"; \
  Parameters: "/Create /TN ""Avinash Print Bridge"" /TR ""\""{app}\{#MyAppExeName}\"""" /SC ONLOGON /RL LIMITED /F"; \
  Flags: runhidden waituntilterminated; \
  Tasks: autostart

Filename: "{app}\{#MyAppExeName}"; \
  Flags: nowait runascurrentuser; \
  Check: WizardSilent

Filename: "{app}\{#MyAppExeName}"; \
  Description: "Start Print Bridge now"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "schtasks"; Parameters: "/Delete /TN ""Avinash Print Bridge"" /F"; \
  Flags: runhidden; RunOnceId: "DelTask"

[UninstallDelete]
; Leave {localappdata}\AvinashPrintBridge — it holds config.json and the log,
; which are worth keeping across a reinstall.

[Code]
// Stop a running agent before overwriting it.
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM print_bridge.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM print_bridge.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;

// --configure fails when no Epson is attached. Say so instead of finishing
// green and leaving someone to discover it at the counter.
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    Exec(ExpandConstant('{app}\{#MyAppExeName}'), '--configure', '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
    if ResultCode <> 0 then
      MsgBox('The LQ310-RAW print queue could not be created.'#13#10#13#10 +
             'Usually this means the Epson printer is not attached or not ' +
             'powered on. Connect it, then re-run this installer.'#13#10#13#10 +
             'Details: %LOCALAPPDATA%\AvinashPrintBridge\print_bridge.log',
             mbError, MB_OK);
  end;
end;
