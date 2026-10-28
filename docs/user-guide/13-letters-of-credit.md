# 13. Letters of credit (LC)

[Back to contents](README.md)

This chapter is for the accounts team. It covers import letters of credit: the bank promises our foreign supplier that it will pay when the shipping documents arrive.

## 13.1 The idea in one sentence

**One LC is one Letter of Credit form, and every step after the application is a button on the form.** Each step that moves money posts its own Journal Entry.

```
Applied → Opened by bank → shipments → Settled → Closed
              (margin)        └ Documents Received → (Accept, usance only) → Settle → Customs Proof
```

The **History** table at the bottom of the form shows every step: its date, who did it, and its Journal Entry.

## 13.2 One-time setup (accountant)

1. Open **LC Settings**.
2. Click **Create Missing Accounts** and confirm. The system adds two accounts to each company:
   - **LC Margin**, for the margin money the bank blocks;
   - **LC Charges Clearing**, where bank charges wait until they are added to the stock's cost.
3. In the **Company Accounts** table, set **Firm Type** for each company:
   - **Industry**, if it manufactures, for example Grihalaxmi;
   - **Trading**, if it only buys and sells.
4. Check the **NRB Margin** and **NRB Limits** sections against the latest Nepal Rastra Bank circular and your bank. Change them when NRB changes them.
5. **Daily Email Digest**: tick it to get a morning email of LC dates coming up. Choose the role that should receive it.
6. Save.

Also check these:

- The **Company** has an **Exchange Gain / Loss Account**.
- A supplier who bills in USD or INR has a **payable account in that currency** in the Supplier's Accounts table.

## 13.3 Applying for an LC

**Fast way:** open the submitted foreign-currency **Purchase Order** and click **Create → Letter of Credit**.

The Purchase Order also shows an orange line when Nepal Rastra Bank rules say the import needs an LC. That is above INR 3 crore from India, or above the draft / TT limit from other countries.

**Or:**

1. Open **Letter of Credit → New**.
2. Fill in:
   - **Company**
   - **Application Date**
   - **Beneficiary (Supplier)**
   - **LC Currency** and **LC Amount**, with **Tolerance + / −** if the LC allows a margin either way
   - **Drafts At**: *Sight* (paid when the documents arrive) or *Usance* (paid a number of days later). For usance, give the **Usance Days** and what they are counted from.
   - **Expiry Date**, **Latest Shipment Date**, **Presentation Period** (21 days unless the LC says otherwise)
   - **Partial Shipment**, **Transhipment**, ports, and the **Nepal Customs Point**, for example Birgunj
   - **Issuing Bank Account**: our account at the bank opening the LC
   - **Bi.Bi.Ni Form** and its number
   - **BCI Report Reference** and **Date**. These are needed for a sight LC of USD 50,000 or more, and the report must be less than a year old.
3. Check the **Documents Required** checklist. It starts with the usual six documents; change it to match the LC.
4. Save, then **Submit**. The status becomes **Applied**.

If the bank takes its LC opening commission now, use **LC → Add Bank Charge**.

## 13.4 When the bank opens the LC

Click **LC → Mark Opened by Bank** and give:

- the **Bank LC Number** and **Issue Date**;
- the **Margin** the bank blocked from our account, and that account.

The status becomes **Opened**. The margin moves into *LC Margin*.

## 13.5 Charges, more margin and amendments

- **Add Bank Charge**: for any charge the bank takes, such as SWIFT, confirmation or a discrepancy fee. It goes to *LC Charges Clearing*.
- **Deposit Margin**: for more margin the bank blocks later.
- **Amend**: when the bank amends the LC, for example a new amount, a later expiry or a later shipment date.
  - Change only what the amendment changes.
  - Enter the amendment charge, if any.
  - The **Amendments** table keeps the old and new value of every change.

## 13.6 Shipments

1. When the supplier ships, click **Shipment → Add Shipment**. Give:
   - the B/L, airway bill or consignment note number;
   - the shipment date;
   - the amount.

   The system refuses a shipment:
   - after the latest shipment date;
   - after expiry;
   - over the LC amount plus tolerance.
2. When the bank hands over the documents, click **Shipment → Documents Received**. Write down any discrepancies the bank listed. If they came later than the presentation period, the system notes it itself.
3. **Usance only:** click **Shipment → Accept**. The maturity date is worked out for you.
4. Make the Purchase Receipt or Purchase Invoice as usual, in the LC currency. Then click **Shipment → Link Receipt / Invoice**. You can also pick them when adding the shipment.

## 13.7 Settling a shipment

When the bank debits our account to pay the supplier, click **Shipment → Settle** and give:

- the **Bank Rate** on the bank's debit advice;
- the **Margin Used**. Leave it blank for this shipment's share, or all of it on the last shipment.

The dialog shows the entry before you save:

- **Total debit:** what the bank took, margin included.
- **Supplier cleared:** how much is cleared from the supplier, at the Purchase Invoice's own rate.
- **Exchange:** the exchange loss or gain.

## 13.8 Customs proof

The bank wants proof that the goods cleared customs. When you give it to the bank, click **Shipment → Customs Proof** and enter:

- the customs declaration (Pragyapan) number;
- the customs clearance date;
- the day you handed the proof to the bank.

The shipment shows the date the proof is due.

## 13.9 Bank charges into the stock's cost

Click **Create → Landed Cost Voucher**. A draft comes up with:

- the LC's linked receipts;
- the bank charges not yet added to stock.

Add customs duty, freight and clearing charges to the same voucher if you like, then submit it.

## 13.10 Closing the LC

When every shipment is settled, click **LC → Close**. Any margin the bank still holds comes back to the bank account. The status becomes **Closed**, or **Expired** if it is past the expiry date.

## 13.11 Made a mistake?

**LC → Undo Last Step** undoes the newest step. It cancels that step's Journal Entry and puts the form back as it was. Undo one step at a time, newest first. Only an Accounts Manager can undo.

**Cancel** works only while the LC is still just *Applied*.

## 13.12 Reports

| Report | Shows |
|---|---|
| **LC Register** | Every open LC: how much is shipped, settled and still available, the ship-by and expiry dates |
| **LC Maturity** | Usance bills waiting to be paid, and how many days are left |
| **LC Margin and Charges** | Per bank: margin held, and charges not yet added to stock |
| **LC Cost Sheet** | For one LC: what each shipment really cost after bank rate, charges and duty |

Print an LC with **Print → LC Summary**.
