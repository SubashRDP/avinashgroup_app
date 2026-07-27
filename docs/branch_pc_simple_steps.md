# Invoice printing — setup steps for the billing computer

**Print this page and keep it near the computer.**

Do these steps **once** on each computer that prints invoices. About 15 minutes.
After that, printing is normal every day.

You need:

- The Epson printer connected by USB cable and switched on
- The pre-printed invoice forms loaded in the printer
- **Google Chrome** (do not use Firefox — it prints the wrong size)
- The Windows administrator password

Do the steps **in order**. Do not skip Step 4.

---

## Step 1 — Find the correct printer name

A computer often shows **more than one** printer for the same machine. Only one
of them can print our invoice. First we find out which.

1. Click the **Start** button.
2. Type: `powershell`
3. Right-click **Windows PowerShell** → click **Run as administrator**.
4. Click **Yes** when Windows asks.
5. Type this line exactly, then press **Enter**:

```
Get-Printer | Select-Object Name, DriverName, PortName | Format-Table -AutoSize
```

You will see a list like this:

```
Name                          DriverName                    PortName
EPSON LQ-310 ESC/P2 (Copy 1)  EPSON LQ-310 ESC/P2           USB005
EPSON LQ-310 ESC/P2           EPSON LQ-310 ESC/P2           LPT1:
EPSON LQ-310                  Epson ESC/P V4 Class Driver   USB005
```

**Choose the line where:**

- `DriverName` contains **ESC/P** — and does **NOT** contain *Class Driver*
- `PortName` starts with **USB**

In the example above, the correct one is the first line:
`EPSON LQ-310 ESC/P2 (Copy 1)`

**Write the name here — you will need it in Step 3:**

```
Printer name: ______________________________________________
```

> **If every line says "Class Driver":** stop here and tell the IT team. That
> driver cannot print our form size, and no setting will fix it. The printer
> driver has to be changed first.

Keep the PowerShell window open.

---

## Step 2 — Create the paper size

Our form is **24.13 cm wide and 13.97 cm tall**. Windows does not know this
size, so we add it.

1. Hold the **Windows key** and press **R**.
2. Type: `printui /s /t1`
3. Press **Enter**. A window called *Print Server Properties* opens.
4. Tick the box **Create a new form**.
5. Fill in the boxes:

   | Box | What to type |
   | --- | --- |
   | Form name | `NGIForm` |
   | Units | choose **Metric** |
   | Width | `24.13cm` |
   | Height | `13.97cm` |
   | Left, Right, Top, Bottom margins | `0` (all four) |

6. Click **Save Form**.
7. Click **Close**.

> Type the numbers exactly. Do **not** round to 25 cm or 14 cm. Even a small
> difference makes each invoice print a little lower than the one before.

---

## Step 3 — Tell the printer to use this paper

This is the step people miss. There are two places to set the paper, and we
need the one called **Printing Defaults**.

1. Hold the **Windows key** and press **R**.
2. Type: `control printers`
3. Press **Enter**.
4. Find the printer with the **exact name you wrote down in Step 1**.
5. Right-click it → click **Printer properties**.
6. Click the **Advanced** tab at the top.
7. Click the **Printing Defaults...** button at the bottom.
8. Find **Paper Size** and choose **NGIForm**.
9. Find **Orientation** and choose **Portrait**.
10. Click **OK**. Click **OK** again to close the other window.

> **If NGIForm is not in the list:** look for **User Defined** or **Custom** in
> the same drop-down. Choose it and type the same numbers: 241.3 mm wide,
> 139.7 mm tall.

**Orientation stays Portrait** even though the paper is wider than it is tall.
Choosing Landscape here turns the invoice sideways.

---

## Step 4 — Close Chrome completely

Chrome only reads the paper list when it starts. Closing the window is **not
enough** — it keeps running in the background.

1. Go back to the PowerShell window from Step 1.
2. Type this line and press **Enter**:

```
taskkill /F /IM chrome.exe
```

It is normal to see a message saying the process was not found, if Chrome was
already closed.

---

## Step 5 — Print a test sheet

Use a **spare invoice** for this, not a customer's invoice.

1. Open Chrome and log in to the site.
2. Go to this address:

   `https://ng-group.raindropinc.com/app/overlay-print-test`

3. In the **Invoice** box, choose any invoice.
4. Click the **Guide** button. A PDF opens in a new tab.
5. Press **Ctrl + P**.
6. Click **More settings** and check all of these:

   | Setting | Must be |
   | --- | --- |
   | Destination | the printer name from **Step 1** |
   | Paper size | **NGIForm** |
   | Scale | **Actual size** — never *Fit to page* |
   | Margins | **None** |
   | Pages per sheet | **1** |

7. Click **Print**.

---

## Step 6 — Look at the test sheet

The test sheet prints **lines and boxes instead of a normal invoice**. That is
correct.

- **Blue line** — this is the edge of the paper. It should sit exactly on the
  edges of your pre-printed form.
- **Red boxes** — these show where each value will print. They should sit
  inside the printed boxes on the form.

**If the blue line sits on the form edges, this computer is finished.** Print
one normal invoice (without the Guide button) to confirm.

---

## Step 7 — If something looks wrong

| What you see | What it means | What to do |
| --- | --- | --- |
| Nothing prints, page comes out blank | Paper size is wrong | Do Steps 2 and 3 again |
| Only A4 and Letter in the Chrome paper list | Wrong printer chosen in Chrome | Step 5, choose the name from Step 1 |
| Everything small in one corner | Scale is wrong | Step 5, set Scale to **Actual size** |
| Printing sideways or upside down | Orientation is wrong | Step 3, set **Portrait** |
| Everything moved the same amount | Only alignment | Report it — see Step 8 |
| Each sheet prints a little higher than the last | Paper height is wrong | Step 2, height must be exactly 13.97 cm |
| Looks right in Chrome, wrong in Firefox | Firefox is not supported | Use Chrome only |

---

## Step 8 — Send us these three things

Even if it looks correct, please send this. It tells us whether the computers
are set up the same way.

1. **A photo of the test sheet.** Put the sheet flat on a table and take the
   photo from straight above, not at an angle.

2. **Print 5 test sheets one after another**, without touching the paper.
   Then answer this question:

   > Is the gap at the top of the **5th** sheet the same as the **1st** sheet,
   > or is it slowly moving?

   This one answer tells us where the problem is. Please do not skip it.

3. **The printer name** you wrote down in Step 1.

4. **The Chrome version on this computer.** In Chrome, type this in the address
   bar and press Enter:

   `chrome://version`

   The first line says *Google Chrome* and a number, like `144.0.7559.109`.
   Send that number.

Send all four to the IT team together.
