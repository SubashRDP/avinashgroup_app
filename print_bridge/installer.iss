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
#define MyAppVersion "0.5.0"
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

[Dirs]
; The agent creates this itself on first run, but RegisterAutostartTask logs
; there from [Code] before the agent has ever run — the dir must already exist.
Name: "{commonappdata}\AvinashPrintBridge"

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
; It needs TWO triggers — carried in a task XML given to schtasks /Create /XML,
; since one /Create can only express one trigger — and its exit code checked so
; a failure is said out loud:
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
; schtasks' /Create defaults were also wrong for a long-lived agent: a task it
; creates is KILLED after 72 hours of running. The XML sets no time limit.
;
; Why not PowerShell's Register-ScheduledTask (v0.3.3's approach): powershell.exe
; is only found via PATH — it lives in System32\WindowsPowerShell\v1.0, not
; System32 — and the first till it met had a PATH that couldn't find it (Exec
; failed, error 2). schtasks.exe and cmd.exe are in System32 itself, which
; CreateProcess searches BEFORE PATH, so they work on that same machine.

Filename: "{app}\{#MyAppExeName}"; \
  Flags: nowait runascurrentuser; \
  Check: WizardSilent

Filename: "{app}\{#MyAppExeName}"; \
  Description: "Start Print Bridge now"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "schtasks"; Parameters: "/Delete /TN ""Avinash Print Bridge"" /F"; \
  Flags: runhidden; RunOnceId: "DelTask"
; Only exists on machines where the XML registration failed and the two-task
; fallback ran (see RegisterAutostartTask). Deleting a missing task is a no-op.
Filename: "schtasks"; Parameters: "/Delete /TN ""Avinash Print Bridge Logon"" /F"; \
  Flags: runhidden; RunOnceId: "DelTaskLogon"

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
// SYSTEM, with NO execution time limit — all carried in a task XML handed to
// schtasks /Create /XML. See the [Run] comment for why the triggers exist and
// why this is schtasks-not-PowerShell. Output goes to task_register.log so a
// failure can be diagnosed from a WhatsApp'd file, and the last word is a
// /Query: the only test that matters is whether the task exists afterwards.
procedure RegisterAutostartTask();
var
  ResultCode: Integer;
  Exe, XmlFile, LogFile, Schtasks: String;
begin
  Exe := ExpandConstant('{app}\{#MyAppExeName}');
  XmlFile := ExpandConstant('{tmp}\print_bridge_task.xml');
  LogFile := ExpandConstant('{commonappdata}\AvinashPrintBridge\task_register.log');
  Schtasks := ExpandConstant('{sys}\schtasks.exe');
  // ASCII-only content, so the ANSI file SaveStringToFile writes is also the
  // valid UTF-8 the header declares. S-1-5-18 is SYSTEM by SID — locale-proof.
  SaveStringToFile(XmlFile,
    '<?xml version="1.0" encoding="UTF-8"?>' + #13#10 +
    '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">' + #13#10 +
    '  <Triggers>' + #13#10 +
    '    <BootTrigger><Enabled>true</Enabled></BootTrigger>' + #13#10 +
    '    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>' + #13#10 +
    '  </Triggers>' + #13#10 +
    '  <Principals>' + #13#10 +
    '    <Principal id="Author">' + #13#10 +
    '      <UserId>S-1-5-18</UserId>' + #13#10 +
    '      <RunLevel>HighestAvailable</RunLevel>' + #13#10 +
    '    </Principal>' + #13#10 +
    '  </Principals>' + #13#10 +
    '  <Settings>' + #13#10 +
    '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>' + #13#10 +
    '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>' + #13#10 +
    '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>' + #13#10 +
    '    <StartWhenAvailable>true</StartWhenAvailable>' + #13#10 +
    '    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>' + #13#10 +
    '    <Enabled>true</Enabled>' + #13#10 +
    '  </Settings>' + #13#10 +
    '  <Actions Context="Author">' + #13#10 +
    '    <Exec><Command>"' + Exe + '"</Command></Exec>' + #13#10 +
    '  </Actions>' + #13#10 +
    '</Task>' + #13#10,
    False);
  // cmd.exe only for the > redirect; {cmd} is a full path, immune to PATH.
  Exec(ExpandConstant('{cmd}'),
       '/C ""' + Schtasks + '" /Create /TN "Avinash Print Bridge" /XML "' + XmlFile +
       '" /F > "' + LogFile + '" 2>&1"',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if ResultCode <> 0 then
  begin
    // Fallback: two single-trigger tasks — all the /Create CLI can express.
    // Loses only the no-72h-limit setting; starting at all beats not starting.
    Exec(ExpandConstant('{cmd}'),
         '/C ""' + Schtasks + '" /Create /TN "Avinash Print Bridge" /TR "\"' + Exe +
         '\"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F >> "' + LogFile + '" 2>&1"',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{cmd}'),
         '/C ""' + Schtasks + '" /Create /TN "Avinash Print Bridge Logon" /TR "\"' + Exe +
         '\"" /SC ONLOGON /RL HIGHEST /F >> "' + LogFile + '" 2>&1"',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
  Exec(Schtasks, '/Query /TN "Avinash Print Bridge"',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if ResultCode <> 0 then
    MsgBox('The auto-start task could not be registered.'#13#10#13#10 +
           'Print Bridge will NOT start by itself after a shutdown or restart ' +
           'until this is fixed. Send this file for diagnosis:'#13#10 +
           LogFile, mbError, MB_OK);
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
    // Exit codes are configure()'s contract (see print_bridge.py): 3 = no Epson
    // attached right now, which is NOT a failure — the agent creates the queue
    // by itself on any later start or print with the printer connected. Tills
    // are set up before the printer arrives often enough that scaring the
    // installer into "re-run this" was wrong.
    if ResultCode = 3 then
      MsgBox('Setup is complete. The Epson printer is not attached right now, ' +
             'so the print queue was not created yet - that is fine. It is ' +
             'created automatically the first time a print happens with the ' +
             'printer connected and switched on. Nothing to re-run.',
             mbInformation, MB_OK)
    else if ResultCode <> 0 then
      MsgBox('The LQ310-RAW print queue could not be created.'#13#10#13#10 +
             'Usually this means the Epson printer is not attached or not ' +
             'powered on. Connect it, then re-run this installer.'#13#10#13#10 +
             'Details: %PROGRAMDATA%\AvinashPrintBridge\print_bridge.log',
             mbError, MB_OK);
  end;
end;
