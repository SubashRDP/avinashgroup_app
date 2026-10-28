# 12. Post-dated cheques (PDC)

[Back to contents](README.md)

This chapter is for the accounts team. It covers cheques customers give us with a future date, and cheques we write to suppliers with a future date.

> **Most cheques here are entered straight into Payment Entry.** Keep doing that. If one of those cheques bounces, follow **12.14**. Sections 12.1–12.13 are for real post-dated cheques, the ones the bank cannot cash until a later date.

## 12.1 The idea in one sentence

**A post-dated cheque is not money in the bank yet.** When it comes in, it goes into **Cheques in Hand**. It moves to the bank only when the bank says it has cleared. If it bounces, the customer owes the money again.

Each cheque is one **PDC Cheque** form, and every step after that is a button on the form:

```
Customer's cheque:  Received → Deposited → Cleared
                                   └→ Bounced → Re-deposit / Replace / Return
Our cheque:         Issued   → Cleared
                        └→ Bounced / Stopped
```

The **History** table at the bottom of the form shows every step: its date, who did it, and its Journal Entry.

## 12.2 One-time setup (accountant)

1. Open **PDC Settings**.
2. Click **Create Missing Accounts** and confirm. The system adds three accounts to each company:
   - **Cheques in Hand**, for customers' cheques not yet cleared;
   - **Cheques Issued**, for our cheques not yet cleared;
   - **Cheque Bounce Charges**.

   If you want to use accounts you already have, change them in the **Company Accounts** table.
3. Check the **Rules** section:
   - **Allow Unallocated Amount (Advance)**: tick it if a cheque may be for more than the invoices it pays. The extra amount becomes an advance.
   - **Block Duplicate Cheque Number per Party**: keep it ticked.
   - **Cheque Valid For (Months)**: 6. A cheque older than this cannot be deposited.
4. **Daily Email Digest**: tick it to get a morning email listing cheques due for deposit. Choose the role that should receive it.
5. **SMS to Party**: see 12.11.
6. Save.

## 12.3 Receiving a cheque from a customer

**Fast way:** open the customer's **Sales Invoice** and click **Create → PDC Cheque**. Everything except the cheque details is filled in for you.

**Or:**

1. Open **PDC Cheque → New**.
2. Fill in these fields:
   - **Cheque Type**: Received
   - **Company**
   - **Posting Date**: the day you got the cheque
   - **Party**: the customer
   - **Cheque No**
   - **Cheque Date**: the date written on the cheque
   - **Amount**
   - **Drawer's Bank** and **Branch**: the customer's bank
3. Click **Get Outstanding Invoices**. The customer's oldest unpaid invoices are listed and filled up to the cheque amount. Change the **Allocated** amounts if the customer said which invoices the cheque is for.
4. Save, then **Submit**. The status becomes **In Hand**. The invoices now show as paid, and the money sits in *Cheques in Hand*.
5. To give the customer a receipt, use **Print** and choose **PDC Cheque Receipt**.

## 12.4 Depositing cheques

On or after the cheque date:

- **One cheque:** open it, click **Actions → Deposit**, choose the date and the bank account, then confirm. The status becomes **Deposited**. No money moves yet.
- **Many cheques:** open the **PDC Cheque** list and filter **Status = In Hand**. Cheques whose date has come show in red as **Due for Deposit**. Tick them and click **Actions → Deposit Selected**, choose the date and the bank, then confirm. The message lists any cheque that could not be deposited, and why. A common reason is "Too early".
- **Deposit slip:** open any deposited cheque and click **Deposit Slip**. The slip lists every cheque deposited to that bank on that day, with the total. Print it for the bank counter.

The system refuses to deposit a cheque before its date, or after it is more than 6 months old ("Stale cheque"). For a stale cheque, ask the customer for a new one (see 12.7).

## 12.5 When the bank clears it

Open the cheque, click **Actions → Clear** and choose the date the bank statement shows. The status becomes **Cleared** and the money moves into the bank account. You do not need to clear it again in Bank Reconciliation.

To clear many cheques at once, tick them in the list and use **Actions → Clear Selected**.

If you never used Deposit, **Clear** on an In Hand cheque does both steps at once.

## 12.6 When a cheque bounces

1. Open the cheque and click **Actions → Bounce**.
2. Fill in:
   - **Bounce Date**
   - **Reason**: copy it from the bank's return memo, for example "Insufficient Funds".
   - **Bank Charges**: what the bank took from our account. Leave it 0 if there was none.
   - **Recover Charges From Party**: tick it if the customer must pay the charge. Leave it unticked to book the charge as our expense.
3. Click **Record Bounce**.

The status becomes **Bounced**. The invoices the cheque paid are **unpaid again**, and the customer's balance goes up by the cheque amount (plus the charge, if you ticked it). This works the same whether the cheque bounced before or after it showed as cleared.

## 12.7 After a bounce: re-deposit, replace or return

| What happened | What to do |
|---|---|
| The customer says "present it again" | **Actions → Re-deposit**, then choose the date and the bank. The status goes back to **Deposited**, and the invoices are paid again. Clear it as usual when the bank confirms. |
| The customer gives a new cheque | **Actions → Replace**. A new cheque form opens with the same customer and invoices. Type the new **Cheque No** and **Cheque Date**, then Save and Submit. The old cheque becomes **Replaced** and links to the new one. |
| We give the paper cheque back | **Actions → Return to Party**. The status becomes **Returned**. No money moves, because the bounce already made the invoices unpaid. |

## 12.8 Returning a cheque we never deposited

If the customer pays another way and wants the cheque back: open the cheque, click **Actions → Return to Party**, choose the date, then confirm. The invoices become unpaid again, ready for the new payment.

## 12.9 Cheques we write to suppliers

1. **Fast way:** on a submitted **Purchase Invoice**, click **Create → PDC Cheque**. Or make a new **PDC Cheque** with **Cheque Type = Issued**.
2. Choose the **Supplier** and our **Company Bank Account**, the account the cheque is written on. Fill in **Cheque No**, **Cheque Date**, **Amount** and the invoices.
3. Submit. The status becomes **Issued**, the invoices show as paid, and the amount waits in *Cheques Issued*.
4. When the money leaves our bank, click **Actions → Clear**.
5. If the supplier's bank returns it, click **Actions → Bounce**. If we take the cheque back before it is presented, click **Actions → Stop / Take Back**. Either way, the invoices are unpaid again.

## 12.10 Fixing a mistake

| Mistake | Fix |
|---|---|
| Wrong details, and the cheque is still **In Hand** or **Issued** with no other step done | **Cancel** the cheque, then **Amend** it and correct it. |
| A step was done by mistake (wrong date, wrong bank, cleared too early) | **Actions → Undo Last Step** (Accounts Manager only). This cancels the last step's Journal Entry and puts the cheque back as it was. Repeat to go back further. |
| A replacement cheque was made by mistake | Cancel the *new* cheque. The old one goes back to Bounced or Returned. |

What the system will not let you do:

- **cancel a Sales or Purchase Invoice** that a live cheque pays. Return or cancel the cheque first.
- **cancel a cheque's Journal Entry** from the Journal Entry form. Use Undo Last Step on the cheque.

## 12.11 SMS to customers

This is set in **PDC Settings → SMS to Party (via Sparrow SMS)**. Nothing is sent until all of these are true:

1. **Send SMS to Party** is ticked;
2. the message itself is ticked:
   - **On Cheque Received**
   - **Reminder Before Cheque Date**, with **Days Before** set
   - **On Cheque Cleared**
   - **On Cheque Bounced**
3. Sparrow SMS is switched on in **Sparrow SMS Settings**.

Each message has its own text box. You can change the wording. Keep words in `{{ }}`, such as `{{ doc.cheque_no }}` and `{{ doc.amount }}`, exactly as they are, because they are filled in for each cheque.

The phone number comes from **Mobile No** on the cheque (filled from the customer; change it if needed). Every SMS, sent or failed, is listed in **Sparrow SMS Log**. A failed SMS never stops the cheque step.

Reminders go out every morning at 8:25, once per cheque.

## 12.12 Reports

Open the **PDC** workspace (sidebar). The cards at the top show:

- cheques in hand;
- cheques due this week;
- issued cheques not yet cleared;
- cheques bounced this month.

| Report | Use it to |
|---|---|
| **PDC Register** | See every cheque in a cheque-date range, with totals by status |
| **PDC Maturity** | See which cheques are due soon or overdue: Overdue, 0–7, 8–30, 31–60 and 61+ days. Choose **Show: Party** for one line per customer |
| **PDC Bounce Analysis** | See which customers bounce cheques and how often, with the most common reason. Use it before accepting a new PDC from a customer |

## 12.13 Messages you may see

| Message | Meaning | What to do |
|---|---|---|
| *Set the cheque holding accounts for … in PDC Settings first* | That company has no row in PDC Settings | Ask the accountant to do 12.2 |
| *Cheque … is dated …; it cannot be presented on …* (Too early) | The cheque date has not come yet | Wait for the date |
| *Cheque … is stale* | The cheque is older than its validity | Ask for a replacement cheque |
| *Cheque … of … is already entered as …* (Duplicate cheque) | That cheque number is already in the system for this customer | Open the existing cheque instead |
| *… has only … outstanding* | You allocated more than the invoice still owes | Lower the Allocated amount |
| *… is settled by post-dated cheque …* | You tried to cancel an invoice a cheque pays | Return or cancel the cheque first |
| *This entry belongs to PDC Cheque …* | You tried to cancel a cheque's Journal Entry | Use Undo Last Step on the cheque |
| *Cheque … is Deposited. Undo its later steps first* | Cancel works only before the first step | Use Undo Last Step until the cheque is In Hand, then Cancel |

## 12.14 When a cheque entered in Payment Entry bounces

You enter cheques in **Payment Entry** as usual. Nothing about that changes. When the bank returns one:

1. Open that **Payment Entry** and click **Cheque → Cheque Bounced**.
2. Fill in:
   - **Bounce Date**: the date on the bank's return memo.
   - **Reason**: for example *Insufficient Funds*.
   - **Bank Charges**: what the bank deducted, or 0.
   - **Recover Charges From Party**: tick it if the customer must pay the charge.
   - **Journal Type**: the type, and so the numbering series, of the bounce Journal Entry. It starts as the type set in PDC Settings. If the system says the type "has no numbering rule" for your company, pick another or ask the accountant to add one.
3. Click **Record Bounce**.

What happens:

- One new **Journal Entry** reverses the payment on the bounce date. The invoices it paid are **unpaid again**, and the bank is credited (plus the charge, if any).
- The Payment Entry itself is **not** changed or cancelled. It shows a red **Cheque Bounced** mark.
- The Payment Entry and its bounce are connected:
  - the Payment Entry's **Connections** section (below the form) lists the cheque record and every bounce or re-present **Journal Entry**;
  - each of those Journal Entries shows the Payment Entry in its **Cheque Payment Entry** field.
- A **cheque record** (PDC Cheque) is made for it. Open it with **Cheque → Cheque Record**. Every later step happens there, and its **History** table shows each one with its Journal Entry.

Then do one of these:

| What happened next | What to do |
|---|---|
| The customer says "present the same cheque again" | On the cheque record: **Actions → Re-present**, then choose the date. The invoices are paid again and the money is back in the bank. |
| The customer pays again (new cheque, cash, transfer) | On the Payment Entry: **Cheque → Replace With New Payment**, or on the record: **Actions → Replace With New Payment**. A new Payment Entry opens with the customer and the unpaid invoices filled in. Type the new cheque no and date, then Save and Submit. The old cheque shows **Replaced**. |
| The new cheque is post-dated | On the record: **Actions → Replace With PDC Cheque** (see 12.3). |
| We hand the bounced cheque back | On the record: **Actions → Return to Party**. No money moves. |
| The bounce was recorded by mistake | On the Payment Entry: **Cheque → Undo Bounce** (Accounts Manager), then confirm. The bounce Journal Entry is cancelled, the invoices are paid again, and the Cheque Bounced mark goes away. If the cheque was already re-presented, returned or replaced after the bounce, undo those first on the cheque record (**Actions → Undo Last Step**, newest first). |

Things the system stops:

- **Cancelling the original Payment Entry** after its cheque bounced. That would reverse the payment twice. Undo the bounce first.
- **Bouncing the same cheque twice.** If the customer re-presents it and it bounces again, use **Actions → Bounce** on the cheque record.
- **Using the new bounce on a Payment Entry bounced with the old button.** Those were already reversed the old way.
- **Cancelling the new Payment Entry** of a replacement is allowed. The old cheque goes back to **Bounced**.

Bounced Payment Entry cheques show in **PDC Bounce Analysis** with all the others. If **SMS on Cheque Bounced** is on in PDC Settings, the customer gets the bounce SMS.

One-time setup: for bank charges, the company needs a row in **PDC Settings → Company Accounts** (**Create Missing Accounts** adds it).

