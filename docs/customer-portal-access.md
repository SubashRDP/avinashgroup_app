# Customer Portal Access

One record per dealer **login**, with a table of every customer record that
dealer buys under (a dealer often has 2-3 customers, different names, different
locations). Desk: `/app/customer-portal-access`, or **Create → Portal Access**
on any Customer.

## What saving does

1. Creates (or adopts) a **User**: Website User, role `Customer`, `mobile_no` =
   the login mobile. Email is the dealer's real one, or `<mobile>@portal.invalid`.
2. Writes one `Portal User` row on each listed Customer (rows inserted directly,
   the Customer is never saved). Removing a customer removes its row.
3. First save issues a password automatically (see below).
4. Untick **Portal Access Enabled** → User disabled + sessions killed. Delete the
   record → rows removed, User disabled but kept.

Refused: a customer already in another login's record, a customer linked by hand
to a different user on its Portal Users tab, a staff (System User) account, a
mobile that isn't 10 digits starting with 9.

## Passwords

Stored only as a hash in `__Auth`; nobody can read one back. **Send New
Password** makes a random one (`Kemaro-4827` shape), sets it, logs out old
sessions and texts it via Sparrow SMS (`Sparrow SMS Log`, `sent_via = Portal
Password`, password masked). If the SMS fails or SMS is off for the login, the
password is shown **once** to the operator to hand over.

Dealers log in with the mobile number: needs System Settings *Allow Login using
Mobile Number*, set by patch `enable_login_with_mobile_number`.

## Who

System Manager and Sales Manager (doctype permissions).

## Deploy

`bench --site <site> migrate` (new doctypes + patch + Sparrow SMS Log option).
