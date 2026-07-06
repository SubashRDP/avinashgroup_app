# Approvals — User Guide

The Dynamic Approval System routes documents (Purchase Orders, Material
Requests, Leave Applications, …) through a chain of approvers before they are
submitted. This chapter explains what you see and do; setup is in
[chapter 8](08-admin-setup.md#approvals).

## How an approval flows

1. **You create the document** as usual. If it is under approval control, you
   will see an **Approval Hierarchy** table on the form.
2. **Add your approvers** (if your document type lets you choose them): each
   row is one level — Level 1 is approved first, then Level 2, and so on.
   Management may have configured additional *fixed approvers* that are
   automatically appended after your levels; you don't need to add those.
3. **Submit for Approval.** The document moves to *Pending Approval* and the
   Level-1 approver gets an email.
4. **Each approver approves in turn.** The document stays in *Pending
   Approval* until the last level approves — then it becomes *Approved* and is
   submitted.
5. If any approver **rejects**, the document becomes *Rejected* and is
   editable again. Fix it and submit again from the start.

## What you see on the form

- A **progress banner** at the top: `✔ Level 1 → ⏳ Level 2 (current) → ◯
  Level 3`, plus a line telling you whose turn it is — "Your approval is
  required at Level 2" or "Waiting for <name> at Level 2".
- While the document is pending and it is **not your turn**, the form is
  read-only and the Approve/Reject buttons are hidden. Only the current
  approver can act or edit.
- Hierarchy rows that are already approved are **locked** — you cannot edit or
  delete them.
- An **Approval History** table records every step (created, submitted,
  approved at each level, rejected) with user and timestamp.

## Approving and rejecting

- **Approve**: open the document, use the workflow action button (top right)
  → *Approve*. If you are an intermediate level, the document stays pending
  and moves to the next approver; if you are the last level, it is submitted.
- **Reject**: choosing *Reject* opens a mandatory **Reason for Rejection**
  box. The reason is saved on the document (or as a comment) so there is
  always an audit trail. You cannot reject without a reason.

## Emails

The next approver is emailed at every step. Rejection sends a distinct email
to the requester.

## Common questions

**Why did my document get approved instantly?**
No approval rule matched it (for example, its company or category has no
active rule). It is auto-approved with a history entry "Auto-approved (no
matching approval rule)". If that's wrong, ask your admin to check the
Dynamic Approval Setting.

**Why can't I edit a pending document?**
Only the current approver may change a pending document. You'll see
"Only <user> may make changes". Wait for the flow to finish, or ask the
current approver to reject it back to you.

**Can I skip a level?**
No — even the Administrator advances one level at a time.

**The document was rejected — now what?**
It is back in an editable state. Make the correction and submit for approval
again; the chain restarts from Level 1.

**Who chooses the approvers?**
Depends on the rule: your own hierarchy rows (Levels 1..N) are yours to fill;
fixed approvers configured by management are appended automatically after
them.
