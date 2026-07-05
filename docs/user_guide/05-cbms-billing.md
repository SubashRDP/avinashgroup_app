# CBMS / IRD e-Billing — User Guide

For accounts staff. CBMS is the IRD's Central Billing Monitoring System —
every sales invoice must be reported to it. In this system that happens
**automatically**; this chapter tells you what to watch and what to do when
something needs attention.

## What happens automatically

- When you **submit a Sales Invoice**, a **CBMS Bill** record is created and
  sent to IRD in the background. You never wait for it — submission is never
  blocked by CBMS.
- When you submit a **Sales Return** (credit note), a **CBMS Bill Return** is
  created and sent — after the original invoice's bill has reached IRD (the
  system enforces the order for you).
- Every 5 minutes the system automatically **retries failures** and **catches
  any invoice that was missed**. You normally don't need to do anything.

## The one field you fill in

On a **Sales Return**, fill **Reason for Return** — it is reported to IRD. If
you leave it blank, "Goods Returned" is sent.

## Monitoring

Open the **CBMS Bill** (and **CBMS Bill Return**) list and filter by **Sync
Status**:

| Status | Meaning |
|--------|---------|
| **Synced** | reported to IRD — done |
| **Pending** | queued; will be sent within minutes |
| **Failed** | IRD rejected it — open the record and read **Sync Response** |

Each record shows the attempt count, last attempt time, and IRD's last
response message. All fields are read-only — you never edit CBMS records.

## Fixing failures

| Sync Response | What to do |
|---------------|-----------|
| `100: API credentials do not match` | the IRD username/password in **CBMS Config** is wrong — fix it there; the retry job re-sends automatically |
| Return stuck **Pending** | its original invoice's CBMS Bill isn't Synced yet — resolve the original first; the return recovers by itself |
| `104: Model invalid` | something in the invoice data was rejected (e.g. bad PAN) — check the customer's tax id and the invoice values, then ask your admin |
| An invoice has **no CBMS Bill at all** | the catch-up job creates it within 5 minutes; if it still doesn't appear, ask your admin to check the Error Log |

There is no button for an instant retry — the system retries every 5 minutes
on its own. An administrator can trigger an immediate retry from the bench
console if ever needed.

## Cancelling invoices

**A synced invoice cannot be cancelled** — you'll get an error saying it has
already been reported to IRD. This is by design: corrections must be made
with a **Sales Return** (credit note), which is itself reported to IRD.
Invoices that are still Pending/Failed (not yet at IRD) can be cancelled
normally.

## Setup (admin, once per company)

Create one **CBMS Config** per company: tick *Enable CBMS Sync*, set the
go-live **Enable From Date** (invoices dated before it are never sent), and
enter the company's IRD **Username/Password**. There is no test mode — the
config talks to the real IRD system, so only enable it when the credentials
are the production ones.
