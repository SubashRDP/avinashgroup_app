# 9. Accounts setup for payroll (for the accountant)

[Back to contents](README.md)

This chapter is for the accountant. It explains where payroll takes its accounts from, what must be in place before a company's payroll can be submitted, and how to read the payroll journal.

## 9.1 Three sections, three accounts

The chart of accounts keeps every staff cost three ways. Each employee belongs to one section through their **Department → Payroll Section**:

| Payroll Section | Sheet label | Example account (NGI) |
|---|---|---|
| Admin & Accounts | O/O | 547101 - Salary Expenses - O/O - NGI |
| Marketing | S/D | 547102 - Salary Expenses - S/D - NGI |
| Plant | F/P | 547103 - Salary Expenses - F/P - NGI |

When the slips are submitted, each person's earnings are booked to **their section's account** for each salary component.

## 9.2 Accounts on each Salary Component

Every salary component that appears on a slip needs one **Accounts** row **per company that pays it**.

1. Open **Salary Component** and open the component (for example "Gas Allowance").
2. In the **Accounts** table, find or add the row for the company. It has:

| Column | What to put |
|---|---|
| **Company** | The company |
| **Account** | The **Admin & Accounts (O/O)** account. For a deduction, the liability account (see 9.3) |
| **Marketing (S/D)** | The S/D account of the **same company** |
| **Plant (F/P)** | The F/P account of the **same company** |
| **Default Rate** | Only for company-rate allowances: the company's rate (Gas 1,690; HRA 25 meaning 25%; Tea 235 per day; Meal 75 per meal). Leave 0 for others |

3. Save.

**Rules**
- Marketing (S/D) and Plant (F/P) must belong to the row's company. Otherwise: "**Accounts row N: … is not an account of …**".
- If S/D or F/P is left **blank**, that section's cost goes to the row's **Account** (O/O). Nothing fails, but the section split is lost.
- If S/D or F/P is filled for a component, then **every** employee paid that component must have a Department with a Payroll Section. Otherwise submission stops with "**Set Payroll Section on the Department of these employees…**".
- If a component has **no row** for the company at all, submission stops with "**Please set account in Salary Component …**".
- Changing the **Default Rate** changes the rate for every employee who has no own rate, from the next payroll.

## 9.3 Deduction accounts

| Component | Account (NGI example) | Section accounts |
|---|---|---|
| SSF | 347302 - SSF Payable | Not used |
| Income Tax | 348102 - 11112 TDS-Remuneration Income Tax | Not used |
| Salary Advance | 148003 - Staff Advance | Not used |
| Late Fine | The salary expense accounts (O/O, S/D, F/P) | Yes — the fine reduces that section's salary cost |

SSF on the slip is the full 31% (employer 20% + employee 11%). The employer's 20% is also an **earning**, **SSF Addition**, booked to the section's salary expense. So SSF Payable receives the full 31%.

## 9.4 Current state (9 October 2026)

| Company | Accounts rows | What is missing before payroll can be submitted |
|---|---|---|
| **NGI** | 23 components, all with O/O, S/D and F/P | Complete. All earnings go to 547101 / 547102 / 547103 Salary Expenses |
| **NGN** | 11 components | **Tea & Conveyance** and **Meal** have a rate but **no account**. **Education Allowance**: the Marketing (S/D) column holds the **O/O** account (547101) — change it to 547102 Salary Expenses - S/D - NGN. Several other components have no row |
| **NGG** | 1 (Meal, rate only, no account) | Accounts for every component paid |
| **NGK** | none | Accounts for every component paid |

Proposal agreed so far: every earning to the three Salary Expenses accounts (547101 / 547102 / 547103). The chart also has separate allowance accounts for some items (for example Meal Allowance 547130 / 547131 / 547132). There is **no Tea & Conveyance account** in the chart yet. Decide whether to use the general Salary Expenses accounts or separate ones, and fill the rows the same way for every company.

## 9.5 The payroll payable account

| Where | Value |
|---|---|
| **Company → Default Payroll Payable Account** | 347301 - Salary Payable - (company) |
| **Account Type** on that account | **Empty.** If it has any type (for example "Payable" or "Liability"), submission stops with "**Account type cannot be set for payroll payable account …, please remove and try again**" |
| Each **Salary Structure Assignment → Payroll Payable Account** | The same account. An assignment with a different or blank payable account is **silently left out** of a Payroll Entry that uses this account |

On 9 October 2026 the four payroll companies (NGI, NGN, NGG, NGK) have 347301 as default with no account type. GLMI, GEPL and SGU have none (they do not run payroll yet).

If a Payroll Entry cannot find the company's default payable account, it shows "**Set Default Payroll Payable Account on Company …, or choose one on this entry.**"

## 9.6 The staff advance account

HRMS requires the Employee Advance account to be **Receivable**. On 9 October 2026 the 148003 Staff Advance account is **Payable** at NGN, NGG, NGK and GLMI, and blank at NGI, GEPL and SGU. Change the Account Type to **Receivable** before anyone records an advance (Chapter 8).

## 9.7 The payroll journal

When HR clicks **Submit Salary Slip** on a Payroll Entry, the system posts one **Journal Entry** (the accrual journal):

| Side | Lines |
|---|---|
| **Debit** | Each earning (Basic, SSF Addition, allowances, tea, meal, overtime…) to its section's expense account, totalled per account and cost centre |
| **Credit** | SSF → SSF Payable; Income Tax → TDS-Remuneration; Late Fine → back to the section's salary expense; Salary Advance → Staff Advance (against each Employee Advance) |
| **Credit** | **Net pay** → 347301 Salary Payable |

The journal's **JV Type** and **Document No** are filled automatically (the next number in the company's Journal Entry series for the fiscal year), so the journal is not refused for missing them.

Then **Make Bank Entry** on the Payroll Entry posts the payment: debit Salary Payable, credit the bank.

**Proving it:** run **Avinas Salary Statement** for the month (Slips = Submitted). A green **Matches Journal** card means each section's gross on the sheet equals the journal's expense debits for that section, and net pay equals the credit to Salary Payable. A red card shows exactly which section differs and by how much (Chapter 7, section 7.1).

Example of a real difference (NGN, Bhadra 2083): Education Allowance's S/D account pointed at the O/O account, so **11,250** of S/D cost was booked to O/O. The sheet showed S/D 11,250 higher than the journal, and O/O 11,250 lower.

## 9.8 Statutory deposits

From the **Salary Tax and SSF Deposit** report (Chapter 7):
- **SSF (31%)** to the Social Security Fund by the **15th** of the next BS month;
- **SST (1%)** and **remuneration tax** to IRD by the **25th** of the next BS month.

Salary TDS also appears in **Advance Tax TDS Details** under the TDS-Remuneration head, as "No Subledger".

These deadlines and the SST / remuneration-tax split are still waiting for the accountant's confirmation.
