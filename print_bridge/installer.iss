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
#define MyAppVersion "0.3.3"
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
Name: "autostart"; Description: "Start Print Bridge automatically (at boot and at every sign-in)"; GroupDescription: "Auto-start:"

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

; The autostart task is registered from CurStepChanged (see [Code]), not here.
; It needs TWO triggers, which schtasks /Create cannot express (one trigger per
; /Create), and its exit code checked so a failure is said out loud:
;
;   - At BOOT, as SYSTEM: the agent runs before and without anyone logging in.
;   - At any user's SIGN-IN: covers powering on after "Shut down". With Fast
;     Startup (the Windows 10/11 default) a shutdown is a kernel hibernate, not
;     a boot, so the next power-on fires no boot trigger — that was v0.3.2's
;     "works after install, dead after every shutdown". Restart IS a real boot,
;     which is why only shutdowns looked broken.
;
; Both triggers run the task as SYSTEM (elevated, so it can self-heal the
; LQ310-RAW queue with Add-Printer — see _ensure_default_queue). The browser
; reaches it either way: 127.0.0.1 is machine-wide, not per-session. If both
; triggers ever fire, Task Scheduler's IgnoreNew policy skips the second start,
; and the agent itself exits quietly when port 8663 is already bound.
;
; schtasks' defaults were also wrong for a long-lived agent: a task it creates
; is KILLED after 72 hours of running. Registration below sets no time limit.

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
; Leave {commonappdata}\AvinashPrintBridge — it holds config.json and the log,
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

// Register the autostart task: boot trigger + any-user sign-in trigger, as
// SYSTEM, with NO execution time limit. See the [Run] comment for why both
// triggers exist and why schtasks /Create couldn't do this. PowerShell's
// ScheduledTasks module is the only stock tool that can; the whole command
// uses single quotes inside so the one pair of double quotes around -Command
// survives the command line.
procedure RegisterAutostartTask();
var
  ResultCode: Integer;
  PS: String;
begin
  PS := '$ErrorActionPreference=''Stop'';'
    + '$a = New-ScheduledTaskAction -Execute ''' + ExpandConstant('{app}\{#MyAppExeName}') + ''';'
    + '$t = @((New-ScheduledTaskTrigger -AtStartup), (New-ScheduledTaskTrigger -AtLogOn));'
    + '$p = New-ScheduledTaskPrincipal -UserId ''SYSTEM'' -RunLevel Highest;'
    + '$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries'
    + ' -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero);'
    + 'Register-ScheduledTask -TaskName ''Avinash Print Bridge'''
    + ' -Action $a -Trigger $t -Principal $p -Settings $s -Force | Out-Null';
  if (not Exec('powershell.exe',
               '-NoProfile -ExecutionPolicy Bypass -Command "' + PS + '"',
               '', SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    MsgBox('The auto-start task could not be registered (exit code ' +
           IntToStr(ResultCode) + ').'#13#10#13#10 +
           'Print Bridge will NOT start by itself after a shutdown or restart ' +
           'until this is fixed. Re-run this installer; if it fails again, ' +
           'report the exit code above.',
           mbError, MB_OK);
end;

// --configure fails when no Epson is attached. Say so instead of finishing
// green and leaving someone to discover it at the counter.
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('autostart') then
      RegisterAutostartTask();
    Exec(ExpandConstant('{app}\{#MyAppExeName}'), '--configure', '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
    if ResultCode <> 0 then
      MsgBox('The LQ310-RAW print queue could not be created.'#13#10#13#10 +
             'Usually this means the Epson printer is not attached or not ' +
             'powered on. Connect it, then re-run this installer.'#13#10#13#10 +
             'Details: %PROGRAMDATA%\AvinashPrintBridge\print_bridge.log',
             mbError, MB_OK);
  end;
end;
