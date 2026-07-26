# Create the 9.5 x 5.5in continuous form on a Windows PC and make it the
# printer's default paper, so the A5 Overlay invoices print 1:1.
#
#   RUN AS ADMINISTRATOR:
#       powershell -ExecutionPolicy Bypass -File windows_setup_form.ps1
#       powershell -ExecutionPolicy Bypass -File windows_setup_form.ps1 -PrinterName "EPSON LQ-310 ESC/P"
#
# Windows ships no Add-PrinterForm cmdlet, so this calls the Win32 spooler API
# (AddForm) through P/Invoke. Sizes in FORM_INFO_1 are in THOUSANDTHS of a
# millimetre, which is why 241.3mm is written 241300.
#
# Why exactly 241.3 x 139.7 and not a rounded 250 x 140:
#   - width  : a page narrower than the form gets centred by most drivers, which
#              shifts every value right and breaks alignment with the pre-printed
#              boxes.
#   - height : the form length tells the printer when to jump to the next form.
#              0.3mm of error per sheet is invisible on sheet 1 and 3mm out by
#              sheet 10, which reads as "the calibration drifted".

param(
    [string] $PrinterName = "",
    [string] $FormName    = "NGIForm",
    [double] $WidthMm     = 241.3,   # 9.5in
    [double] $HeightMm    = 139.7    # 5.5in
)

$ErrorActionPreference = "Stop"

# --- must be elevated: AddForm writes to the local print server ---------------
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Run this in an Administrator PowerShell — creating a form needs elevation."
}

# --- Win32 spooler ------------------------------------------------------------
Add-Type -Namespace Spooler -Name Api -MemberDefinition @"
[StructLayout(LayoutKind.Sequential)] public struct SIZEL { public int cx, cy; }
[StructLayout(LayoutKind.Sequential)] public struct RECTL { public int left, top, right, bottom; }
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct FORM_INFO_1 {
    public uint   Flags;
    [MarshalAs(UnmanagedType.LPWStr)] public string pName;
    public SIZEL  Size;
    public RECTL  ImageableArea;
}
[DllImport("winspool.drv", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern bool OpenPrinter(string pPrinterName, out IntPtr phPrinter, IntPtr pDefault);
[DllImport("winspool.drv", SetLastError = true)]
public static extern bool ClosePrinter(IntPtr hPrinter);
[DllImport("winspool.drv", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern bool AddForm(IntPtr hPrinter, uint Level, ref FORM_INFO_1 pForm);
[DllImport("winspool.drv", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern bool DeleteForm(IntPtr hPrinter, string pFormName);
"@

# thousandths of a millimetre
$w = [int][math]::Round($WidthMm  * 1000)
$h = [int][math]::Round($HeightMm * 1000)

$form = New-Object Spooler.Api+FORM_INFO_1
$form.Flags = 0                                   # 0 = user-defined form
$form.pName = $FormName
$form.Size  = New-Object Spooler.Api+SIZEL
$form.Size.cx = $w
$form.Size.cy = $h
# margins 0: the whole sheet is printable, the overlay places its own mm
$form.ImageableArea = New-Object Spooler.Api+RECTL
$form.ImageableArea.left   = 0
$form.ImageableArea.top    = 0
$form.ImageableArea.right  = $w
$form.ImageableArea.bottom = $h

$hPrinter = [IntPtr]::Zero
if (-not [Spooler.Api]::OpenPrinter($null, [ref] $hPrinter, [IntPtr]::Zero)) {
    Write-Error "OpenPrinter failed on the local print server (error $([Runtime.InteropServices.Marshal]::GetLastWin32Error()))."
}

try {
    # idempotent: drop any previous version so re-running fixes a wrong size
    [void][Spooler.Api]::DeleteForm($hPrinter, $FormName)

    if (-not [Spooler.Api]::AddForm($hPrinter, 1, [ref] $form)) {
        $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        Write-Error "AddForm failed (error $err)."
    }
    Write-Host ("Created form '{0}' = {1} x {2} mm, margins 0." -f $FormName, $WidthMm, $HeightMm) -ForegroundColor Green
}
finally {
    [void][Spooler.Api]::ClosePrinter($hPrinter)
}

# --- point a printer at it ----------------------------------------------------
if (-not $PrinterName) {
    $candidates = Get-Printer | Where-Object { $_.Name -match "LQ|Epson" }
    if ($candidates.Count -eq 1) {
        $PrinterName = $candidates[0].Name
    } else {
        Write-Host ""
        Write-Host "Form created. Now set it as the printer's default paper:" -ForegroundColor Yellow
        Get-Printer | Select-Object Name, DriverName | Format-Table -AutoSize
        Write-Host ("  .\windows_setup_form.ps1 -PrinterName ""<name from above>""")
        return
    }
}

try {
    Set-PrintConfiguration -PrinterName $PrinterName -PaperSize $FormName
    $cfg = Get-PrintConfiguration -PrinterName $PrinterName
    Write-Host ("'{0}' default paper is now: {1}" -f $PrinterName, $cfg.PaperSize) -ForegroundColor Green
}
catch {
    # Some Epson drivers ignore server forms and keep their own size list.
    Write-Host ""
    Write-Warning ("Could not set the paper size on '{0}' automatically: {1}" -f $PrinterName, $_.Exception.Message)
    Write-Host "Set it by hand: Printing preferences -> Paper Size -> $FormName."
    Write-Host "If it is not listed there, the driver ignores server forms — use its own"
    Write-Host "'User Defined' / 'Custom' size entry with the same 241.3 x 139.7 mm."
}

Write-Host ""
Write-Host "Check it worked: open an overlay PDF, Ctrl+P, More settings ->" -ForegroundColor Cyan
Write-Host "  Paper size = $FormName, Scale = Actual size (never Fit to page), Margins = None." -ForegroundColor Cyan
