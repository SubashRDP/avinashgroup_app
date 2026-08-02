# A5 Overlay invoice printing — the flow

Visual companion to `how_overlay_print_works.md`. One diagram of the whole
chain, from the desk Print button to the 684 × 396 pt PDF the pre-printed form
soaks up.

## The pipeline

```mermaid
flowchart TD
    A["Desk <b>Print</b> button"] --> B{"ngi_print.js<br/>is_chrome_format()"}
    B -->|"format's pdf_generator == 'chrome'"| C["/api/method/…/download_pdf"]
    B -->|"not a chrome format"| Z["browser print dialog<br/>(A4 portrait — mm lost)"]

    C --> D["hooks.py override_whitelisted_methods<br/>→ chrome_pdf.download_pdf"]
    D --> E["print_utils.get_print<br/>reads Print Format .pdf_generator = 'chrome'"]
    E --> F["before_print hook<br/>→ print_count.before_print"]

    F --> G["Jinja renders the Print Format html"]
    G --> G1["wrapper: {% set form = 'grishma' %}<br/>{% include nepal_gas_invoice_a5_overlay.html %}"]

    G1 --> H["overlay template §1–7"]
    H --> H1["§1 Knobs (wrapper + &…= URL, values ADD):<br/>ox/oy shift whole print · fh form pitch (fixes a WALK)<br/>rot orient · guide=1 outline test · amt_r · page"]
    H --> H2["§2 Geometry: fw/fh form space vs pw/ph page<br/>rot = one CSS transform on .ov-rot"]
    H --> H3["§3 Coordinates: P = overlay_pos(form, page)"]
    H --> H4["§5 Macros at()/atr() emit positioned boxes<br/>ox/oy added inside → move everything"]
    H --> H5["§7 Sheets: for each copy title × each page of items"]

    H3 --> I["overlay.py<br/>_form_module('grishma') → escp_grishma"]
    I --> I1["escp_grishma.py — single source of truth<br/>X0_MM/Y0_MM, POS dict (true mm), COPY_LABEL_ANCHOR"]
    H5 --> J["print_count.invoice_copy_titles(doc)<br/>TAX INVOICE / INVOICE / COPY OF INVOICE n"]

    H1 --> K["pdf_generator hook → chrome_pdf.render()"]
    H2 --> K
    H4 --> K
    I1 --> K
    J --> K

    K --> L["headless chrome --print-to-pdf<br/>--run-all-compositor-stages-before-draw<br/>--virtual-time-budget=10000"]
    L --> M["@page { size: 241.3mm 139.7mm; margin: 0 }"]
    M --> N["<b>684 × 396 pt PDF</b><br/>= 241.3 × 139.7 mm, no /Rotate, 1:1"]
    N --> O["printer adds values onto the<br/>pre-printed continuous form"]

    style Z fill:#5a1e1e,color:#fff
    style N fill:#1e4620,color:#fff
    style O fill:#1e4620,color:#fff
    style I1 fill:#3a3a1e,color:#fff
```

## The two load-bearing facts

```mermaid
flowchart LR
    subgraph one["1. Absolute mm, no layout"]
        direction TB
        a1["Nothing flows"] --> a2["every left/top is a<br/>true mm from escp_*.py POS"]
    end
    subgraph two["2. Chrome, not wkhtmltopdf"]
        direction TB
        b1["distro wkhtmltopdf renders<br/>every length at 0.7688×"] --> b2["one wrong generator →<br/>whole form shrinks to top-left"]
    end
```

## The counter branch (Stage 3c)

`before_print` runs on **every** render — preview included — but only the
*actual print* costs a sheet.

```mermaid
flowchart TD
    P["before_print (every render)"] --> Q["always stamp<br/>doc.flags.print_prev_sheets<br/>(template shows NEXT print's titles)"]
    P --> R{"docstatus == 1<br/>AND is_actual_print()?"}
    R -->|"preview / draft"| S["free — counter untouched"]
    R -->|"download_pdf, print_by_server,<br/>trigger_print=1, …"| T["atomic UPDATE print_count += n<br/>on Sales Invoice Print Count"]
    T --> U["explicit frappe.db.commit()<br/>(GET request would otherwise roll back)"]
```

## Where to look when it breaks

| Symptom | Node in the flow |
| --- | --- |
| Whole form shrunk top-left | wkhtmltopdf got it — check `pdf_generator` on the record + `chrome_pdf` Error Log |
| Print rotated / sideways | driver, not the format — PDF has no `/Rotate`. Use `&rot=` |
| Everything a few mm off | `ox`/`oy` (§1 knobs), never a field number |
| One field off | that form's `escp_*.py` POS entry |
| Right columns pulled inboard | the A5 clamps — check `page` is not `'a5'` |
| Title half a label off | `COPY_LABEL_ANCHOR` disagrees with the emit site |
| Nothing changes for a branch | `Company Print Template` still routes to a Dot Matrix format |
| Print **walks** down the roll sheet after sheet | `fh` form pitch ≠ true perforation distance — `ox`/`oy` cannot fix a walk |

## Calibrating on a machine

Use the **`Overlay Print Test`** desk page (`page/overlay_print_test/` + `printing/test_bench.py`) — it builds live print URLs with the knob params (`&ox=`, `&oy=`, `&fh=`, `&rot=`, `&guide=1`) so a form can be dialled in without editing anything. Once right, bake `ox`/`oy`/`fh` into the wrapper Print Format's `{% set %}` line.
