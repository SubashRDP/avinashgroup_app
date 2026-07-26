# Windows PC setup for printing invoices on the pre-printed form

Follow this once per billing computer. About 15 minutes.

**What you are setting up:** the invoice prints onto the continuous
**9.5 × 5.5 inch** pre-printed form. The system prints only the *values* — the
boxes and headings are already on the paper — so everything depends on the
paper size being exactly right.

**You need:** the printer connected and on, **Google Chrome**, and
Administrator rights.

> **Use Chrome, not Firefox.** Firefox prints PDFs by converting them to an
> image first, which loses the exact millimetres. Chrome sends the real PDF to
> the printer.

---

## Step 1 — Find the right print queue

**This is the step everyone gets wrong.** A PC usually ends up with several
queues for the same printer, and only one of them can do the job.

Open **PowerShell as Administrator** (right-click Start → Terminal
(Administrator)) and run:

```powershell
Get-Printer | Select-Object Name, DriverName, PortName | Format-Table -AutoSize
Get-PrinterDriver | Select-Object Name, MajorVersion | Format-Table -AutoSize
```

You are looking for a queue whose **DriverName** is the real Epson driver —
something like `EPSON LQ-310 ESC/P2` — and whose **MajorVersion is 3**.

A real example, from a laptop that had this exact problem:

```
Name                          DriverName                    PortName
EPSON LQ-310 ESC/P2 (Copy 1)  EPSON LQ-310 ESC/P2           USB005   <-- USE THIS
EPSON LQ-310 ESC/P2           EPSON LQ-310 ESC/P2           LPT1:    <-- dead, no printer on LPT1
EPSON LQ-310                  Epson ESC/P V4 Class Driver   USB005   <-- cannot work
```

The right queue is the one with **the Epson driver *and* a USB port**.

> ### Why the V4 one cannot work
> `Epson ESC/P V4 Class Driver` (MajorVersion **4**) is the generic driver
> Windows installs automatically. V4 drivers **ignore custom paper sizes
> completely** and only offer A4 and Letter. If Chrome shows you just A4 and
> Letter, you are on this driver. No setting, script, or registry change will
> add your form — the driver has to be replaced.

**Write down the exact queue name.** Everything below uses it. In the examples
it is `EPSON LQ-310 ESC/P2 (Copy 1)` — substitute yours.

### If there is no MajorVersion 3 Epson driver

Download the real driver from Epson, for your exact model:

- LQ-310: <https://download-center.epson.com/softwares/?device_id=LQ-310&os=WIN1164&language=en&region=US>
- LX-310: <https://download-center.epson.com/softwares/?device_id=LX-310&os=WIN1164&language=en&region=US>
- Or the regional page: <https://www.epson.co.in/Support/Printers/Dot-Matrix-Printers/LQ-Series/Epson-LQ-310/s/SPT_C11CC25321>

Take the item called **Printer Driver**. If Windows 11 only offers a V4
package, choose the **Windows 7 / 8 64-bit** package instead — those are v3 and
install fine on Windows 10 and 11.

Then install it and make a queue on it (use the USB port from step 1):

```powershell
pnputil /add-driver C:\epson\*.inf /install /subdirs
Get-PrinterDriver | Where-Object Name -match "LQ|LX" | Select-Object Name, MajorVersion
Add-Printer -Name "LQ310-Form" -DriverName "EPSON LQ-310 ESC/P2" -PortName "USB005"
```

---

## Step 2 — Create the paper size

Exactly **241.3 × 139.7 mm** (9.5 × 5.5 in). Do not round to 25 cm or 14 cm —
see *Why the exact size matters* at the end.

Run this in Administrator PowerShell (creates the Windows form):

```powershell
powershell -ExecutionPolicy Bypass -File setup_form.ps1
```

(The script is at the end of this document.) Or do it by hand: **Win + R** →
`printui /s /t1` → Forms tab → tick **Create a new form** → name `NGIForm`,
Units **Metric**, Width `24.13cm`, Height `13.97cm`, all margins `0` →
**Save Form**.

---

## Step 3 — Point the queue at that paper

Two places must agree. **Printing Defaults** is the one Chrome reads —
Preferences alone is not enough.

```powershell
rundll32 printui.dll,PrintUIEntry /p /n "EPSON LQ-310 ESC/P2 (Copy 1)"
```

→ **Advanced** tab → **Printing Defaults…** → **Paper Size** → `NGIForm` →
OK out of every dialog.

Then the per-user copy:

```powershell
rundll32 printui.dll,PrintUIEntry /e /n "EPSON LQ-310 ESC/P2 (Copy 1)"
```

→ **Paper Size** → `NGIForm` → also set **Orientation: Portrait** → OK.

> If `NGIForm` is not in the list, use the driver's own **User Defined**
> (or *Custom*) entry in the same dropdown: 241.3 × 139.7 mm, name it, Save,
> then select it.
>
> Note: `Set-PrintConfiguration -PaperSize` does **not** work for this — that
> cmdlet only accepts Windows' built-in size names, not custom forms.

Make it the default printer so nobody picks the wrong queue:

```powershell
Get-CimInstance Win32_Printer -Filter "Name='EPSON LQ-310 ESC/P2 (Copy 1)'" |
    Invoke-CimMethod -MethodName SetDefaultPrinter
```

---

## Step 4 — Restart Chrome properly

Chrome reads the printer's paper list once at startup. Closing the window is
not enough:

```powershell
taskkill /F /IM chrome.exe
```

Reopen Chrome, open any invoice PDF, **Ctrl+P**, **More settings**:

| Setting | Must be |
| --- | --- |
| Destination | **the queue from step 1** — not the V4 one |
| Paper size | `NGIForm` |
| Scale | **Actual size** — never *Fit to page* |
| Margins | None |
| Pages per sheet | 1 |

---

## Step 5 — Test print

Load a real pre-printed form. Open the invoice in ERP, pick the print format
for **the roll you have loaded**, and add `&guide=1` to the end of the address
in the PDF tab:

```
...&format=Nepal%20Gas%20Udyog%20Invoice%20A5%20Overlay&guide=1
```

Print that one page. It prints outlines instead of a normal invoice:

- **Blue outline** = the sheet edge. On the form's own edges → paper size is
  correct and this PC is done.
- **Red boxes** = where each value lands. All shifted the same way → report how
  far and in which direction, in mm. That is a one-line change on our side.

Then print a normal invoice without `&guide=1`.

---

## If something goes wrong

| What you see | What it means | What to do |
| --- | --- | --- |
| **Only A4 and Letter in Chrome** | You are on the V4 class driver, or Chrome is pointed at the V4 queue | Step 1 — pick the MajorVersion 3 queue |
| **Blank sheet, nothing printed** | Paper size does not match the form, and scaling is off. Wrong size prints *nothing*, not something small | Redo steps 2–3, check the numbers |
| **Everything small in one corner** | *Fit to page* is on | Scale → **Actual size** |
| **Printed sideways / up-and-down** | Paper is portrait-shaped, or Orientation is Landscape | Step 3: 241.3 × 139.7, Portrait |
| **Everything shifted the same amount** | Just alignment | Report the mm and direction |
| **One value wrong, rest fine** | Not a PC problem | Report which field |
| **Each sheet creeps down the page** | Form *height* wrong | Must be exactly 139.7 mm |
| **Prints fine in Chrome, wrong in Firefox** | Firefox rasterises PDFs | Use Chrome |
| **PDF does not open when printing** | Popup blocker | Allow popups for the ERP site |

---

## Why the exact size matters

**Width.** If the form is wider than the invoice page, the driver centres the
page on it and every value shifts sideways — the pre-printed boxes do not move
with it. 25 cm instead of 24.13 cm pushes everything about 4 mm right.

**Height.** The form length tells the printer when to jump to the next form.
140 mm instead of 139.7 mm puts each sheet 0.3 mm lower than the one before —
invisible on sheet 1, 3 mm out by sheet 10, and it looks like the alignment
broke by itself.

---

## The script

Save as `setup_form.ps1`, run as Administrator (step 2).

```powershell
param(
    [string] $PrinterName = "",
    [string] $FormName    = "NGIForm",
    [double] $WidthMm     = 241.3,   # 9.5in
    [double] $HeightMm    = 139.7    # 5.5in
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Run this in an Administrator PowerShell - creating a form needs elevation."
}

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

# FORM_INFO_1 sizes are in thousandths of a millimetre
$w = [int][math]::Round($WidthMm  * 1000)
$h = [int][math]::Round($HeightMm * 1000)

$form = New-Object Spooler.Api+FORM_INFO_1
$form.Flags = 0
$form.pName = $FormName
$form.Size  = New-Object Spooler.Api+SIZEL
$form.Size.cx = $w
$form.Size.cy = $h
$form.ImageableArea = New-Object Spooler.Api+RECTL
$form.ImageableArea.left   = 0
$form.ImageableArea.top    = 0
$form.ImageableArea.right  = $w
$form.ImageableArea.bottom = $h

$hPrinter = [IntPtr]::Zero
if (-not [Spooler.Api]::OpenPrinter($null, [ref] $hPrinter, [IntPtr]::Zero)) {
    Write-Error "OpenPrinter failed (error $([Runtime.InteropServices.Marshal]::GetLastWin32Error()))."
}

try {
    [void][Spooler.Api]::DeleteForm($hPrinter, $FormName)   # so re-running fixes a wrong size
    if (-not [Spooler.Api]::AddForm($hPrinter, 1, [ref] $form)) {
        Write-Error "AddForm failed (error $([Runtime.InteropServices.Marshal]::GetLastWin32Error()))."
    }
    Write-Host ("Created form '{0}' = {1} x {2} mm, margins 0." -f $FormName, $WidthMm, $HeightMm) -ForegroundColor Green
}
finally {
    [void][Spooler.Api]::ClosePrinter($hPrinter)
}

Write-Host ""
Write-Host "Next: set this form on the queue (step 3), then restart Chrome (step 4)." -ForegroundColor Cyan
Write-Host "  rundll32 printui.dll,PrintUIEntry /p /n ""<your queue name>""" -ForegroundColor Cyan
```
