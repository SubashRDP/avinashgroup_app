# 13. Letters of credit (LC)

[Back to contents](README.md)

This chapter is for the accounts team. It covers import letters of credit: the bank promises our foreign supplier that it will pay for the goods.

## 13.1 The idea in one sentence

**One LC is one cost file.** Every rupee the import costs (the goods, bank charges, insurance, customs, clearing and freight) is booked on the LC form. When the goods reach us, the total moves into stock or fixed assets at full landed cost.

```
Draft → Open → In Transit → Arrived → Transferred → Closed
        (LC No.,   (Depart     (Reach      (Transfer to
         margin)    Date)       Date)       Stock / Asset)

Costs can be added at any time while the LC is open.
```

The LC is **not** made from a Purchase Order, and no Purchase Invoice is needed. The **History** table at the bottom of the form shows every step: its date, who did it, and its Journal Entry.

## 13.2 One-time setup (accountant)

1. Open **LC Settings**.
2. Click **Create Missing Accounts** and confirm. Each company gets:
   - **LC Margin**, for the margin money the bank blocks;
   - **LC Goods in Transit**, where every cost of an LC waits until the goods are transferred;
   - **Input VAT**, picked from the VAT account your purchases already use. Check it.
3. In the **Company Accounts** table, set **Firm Type** for each company: **Industry** (manufactures, for example Grihalaxmi) or **Trading**.
4. Check the **NRB Margin** and **NRB Limits** sections against the latest Nepal Rastra Bank circular and your bank.
5. **Daily Email Digest**: tick it to get a morning email of LC dates coming up.
6. Save.

Also make sure that the **Company** has an **Exchange Gain / Loss Account** (it is needed for usance LCs).

**Cost types.** The list **LC Cost Type** already holds the usual costs:

| Group | Costs |
|---|---|
| Bank Charges | LC Commission, SWIFT Charge, Amendment Charge, Documentation Charge |
| Insurance | Marine Insurance |
| Customs | Import Duty (ID), Excise Duty (ED) |
| VAT | Customs VAT (claimable, so it never goes into the cost) |
| Clearing | Customs Clearance, Load / Unload, Labour Charge, Clearance Charge, ICP Booking |
| Freight | Freight up to Border, Local Freight from Border |
| Other | Other Charge |

To add a cost that is not listed, add a new LC Cost Type and choose its group.

## 13.3 Making the LC

**Letter of Credit → New.** Fill in:

- **Company**, **LC No.** (the number the bank gave), **Supplier**;
- **LC Open Date**, **Expiry Date**;
- **Payment Terms**: **Sight** (the bank pays on the documents) or **Usance** (you accept the bill and the bank pays on the **Maturity Date**). For usance, give the **Usance Days** and the **Maturity Date**;
- **Incoterm** and its place, for example CIF Birgunj;
- **Currency** and **LC Amount**. The **Estimated Exchange Rate** is only for the margin estimate;
- **Issuing Bank Account**, and **Margin Taken at Opening** (what the bank blocked; leave it 0 if none).

**Goods table.** One row per kind of goods: **Item Group**, **Item**, **Description**, **Qty**, **UOM**, **Rate**. Then say where each row goes when it arrives:

- **Transfer To = Stock**, with a **Warehouse** (or set **Default Warehouse** above the table once);
- **Transfer To = Fixed Asset**, with an **Asset Category** (it fills from the item).

The item can be chosen later, but it is needed before the transfer.

**Share Costs By** says how the total cost is spread over the rows: **Value** (the usual choice) or **Quantity**.

Click **Submit**. The LC is now **Open**, and the margin entry is posted (Dr LC Margin / Cr Bank).

## 13.4 Booking the costs

Costs go straight into the **Costs** table on the LC form, one row for each bill or bank debit:

| Column | What to enter |
|---|---|
| **Date** | the date of the bank debit or the bill |
| **Cost** | for example SWIFT Charge, Amendment Charge, Documentation Charge, Freight up to Border |
| **Amount** | without VAT |
| **VAT** | the VAT on the bill, if any |
| **Paid Via** | **Bank**: paid now, from **Paid From** (the LC's bank fills in by itself). **Party**: owed to the **Party**, for example the transporter, insurer or clearing agent |

Then click **Save** (on a draft) or **Update** (on a submitted LC). Each new row posts its own entry: Dr LC Goods in Transit (and Dr Input VAT for the VAT) / Cr the bank or the party. Rows typed into a draft (the LC commission at opening, say) post when you submit.

- A posted row (it shows its **Journal Entry**) cannot be changed. If it is wrong, **delete the row** and click Update: its entry is cancelled. Then add the right row.
- Once the goods are transferred, a cost row can no longer be deleted.

**Customs.** Book Import Duty and Excise Duty as costs. Book the VAT paid at customs as **Customs VAT**: all of it goes to Input VAT, and none of it goes into the cost.

**Margin top-up:** **LC → Deposit Margin**.

## 13.5 Paying for the goods

**Sight LC: Goods → Pay Goods.** Enter the amount in the LC currency, the **bank rate** from the debit advice, and the **margin used**. The margin used fills itself: a share of the margin held, or all of it on the last payment. The goods' value (amount × bank rate) goes into LC Goods in Transit. You can pay in parts, up to the LC amount plus tolerance.

**Usance LC:**

1. **Goods → Accept Bill** when you accept the documents. Give the amount, the rate on the day you accept, and the maturity date. The goods go into the cost at that rate, and the supplier shows the bill as payable.
2. **Goods → Pay at Maturity** when the bank pays. Give the bank rate and the margin used. Any difference from the acceptance rate goes to **Exchange Gain / Loss**, not into the cost. The dialog shows the difference before you confirm.

## 13.6 Shipment and customs

These fields can be changed on the submitted LC. Edit them, then click **Update**:

- **Mode of Transport**, **B/L / AWB / CN No.**, **Port of Loading**, **Nepal Customs Point**, **Latest Shipment Date**;
- **Depart Date**: the status becomes **In Transit**;
- **Reach Date**: the status becomes **Arrived**;
- **Pragyapan No.** and date, and **Customs Proof Given to Bank On**.

An amendment from the bank (a new amount, expiry or maturity) is also just an edit and **Update**. Book its charge as **Amendment Charge**.

## 13.7 Transfer to stock or fixed asset

When the goods have reached us and all the costs are booked: **Goods → Transfer to Stock / Asset**.

The dialog shows each goods row with its share of the landed cost and its cost per unit. Fix anything it lists in red first, then click **Transfer**:

- the **Stock** rows become one **Stock Entry (Material Receipt)** at their landed rates;
- the **Fixed Asset** rows post one Journal Entry to the asset account, and make a **draft Asset** each. Open each Asset, fill in the **Location** and the depreciation details, and submit it.

LC Goods in Transit for this LC is now empty, and the status is **Transferred**.

## 13.8 Closing

**LC → Close LC.** Any margin still held comes back to the bank account. If a cost was booked after the transfer, choose an account to clear it to (usually an expense). The LC is then **Closed**.

## 13.9 Mistakes

A wrong cost row: delete it from the Costs table and Update (see 13.4).

**LC → Undo Last Step** (Accounts Manager) reverses the newest step: its Journal Entry is cancelled, and a transfer's Stock Entry and draft Assets are removed. Undo again for the step before. A transfer cannot be undone once one of its Assets is submitted. Cancel the Asset first.

A Journal Entry or Stock Entry made by an LC cannot be cancelled from its own form. Use Undo on the LC.

**Cancel** the LC itself only when nothing has been booked after opening. Undo every step first.

## 13.10 Reports and prints

| What | Where | Shows |
|---|---|---|
| **LC Cost Sheet** | LC → View → Cost Sheet, or the report list | Every cost by group, the total landed cost, and each item's landed cost and per-unit rate |
| **LC Register** | Reports | Every LC: paid, still to pay, dates, landed cost, margin, status |
| **LC Maturity** | Reports | Accepted usance bills not paid yet, with days left and value at today's rate |
| **LC Margin and Charges** | Reports | Per company and bank: margin, cost by group, how much is in stock or still in transit |
| **LC Summary** print | Print on the LC | Terms, goods with landed cost, cost summary |
| **LC Cost Sheet** print | Print on the LC | The detailed cost sheet to file with the LC |

The **daily email** lists LCs whose latest shipment date or expiry is close, usance bills maturing, and customs proof due at the bank.
