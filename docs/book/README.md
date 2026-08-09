# The Avinash Group App Handbook

A **learning path** through everything built in this app — as opposed to
`docs/technical/` (reference: what each thing is) and `docs/user_guide/`
(task-oriented: how to use it).

Read in order. Parts I and II are short and everything else depends on them.

| # | File | Contains |
| --- | --- | --- |
| 0 | [Preface](00-preface.md) | why this book exists, how to read it, the map of the repo |
| I | [Foundations](01-foundations.md) | **1.** the bench, sites, venvs, the replica, the seven companies · **2.** the eight Frappe mechanisms this app is built from |
| II | [The domain](02-domain.md) | **3.** BS dates, fiscal years, VAT-on-excise, and the five things the IRD demands |
| III | [The transaction core](03-transaction-core.md) | **4.** numbering · **5.** the Sales Invoice pipeline & atomic save-submit · **6.** CBMS / IRD e-billing |
| IV | [Getting ink on paper](04-printing.md) | **7.** why raw ESC/P, coordinates, overlays, the wkhtmltopdf problem · **8.** the print bridge, copy titles, sheet counting |
| V | [Platform services](05-platform-services.md) | **9.** SMS rules, dynamic approval, access control, audit · **10.** biometric attendance, self-healing, BS payroll · **11.** reports |
| VI | [Legacy, lessons & playbooks](06-legacy-and-lessons.md) | **12.** importing the old software's history · **13.** the 32 rules this app taught · **14.** playbooks + where to look things up |

**If you have one hour:** Chapter 2, Chapter 13, and whichever playbook in
Chapter 14 matches the problem in front of you.

Written 2026-08-06 against the code in this repo on that date. Where this book
and an older note in `docs/` disagree, check the code.
