"""Create the load-test user population.

100 System Users with functional (non-System-Manager) roles so that every
custom permission layer — fiscal_year_filter query conditions, globalfilter,
dynamic approval — actually executes for each of their requests instead of
being bypassed.

Run:
    bench --site avinas execute avinashgroup_app.loadtest.setup_users.make_users
    bench --site avinas execute avinashgroup_app.loadtest.setup_users.make_users --kwargs '{"count": 100}'

Credentials land in <site>/loadtest_users.csv (email,password,api_key,api_secret)
which loadtest/locustfile.py reads.

Cleanup:
    bench --site avinas execute avinashgroup_app.loadtest.setup_users.delete_users
"""

import csv
import os

import frappe

EMAIL_PATTERN = "loadtest{:03d}@avinash.test"
DEFAULT_PASSWORD = "LoadTest@12345"

# Functional roles covering all seeded transaction doctypes.
ROLES = [
    "Accounts User",
    "Accounts Manager",
    "Sales User",
    "Sales Manager",
    "Purchase User",
    "Purchase Manager",
    "Stock User",
    "Stock Manager",
    "HR User",
]


def _csv_path():
    return frappe.get_site_path("loadtest_users.csv")


def make_users(count=100, password=DEFAULT_PASSWORD):
    if not frappe.conf.allow_tests:
        frappe.throw("Refusing to create load-test users: site_config allow_tests is not set")

    # bypass frappe's 60-users/hour creation throttle for this bulk setup
    frappe.flags.in_import = True

    fiscal_years = [fy.name for fy in frappe.get_all("Fiscal Year")]
    rows = []
    for i in range(1, int(count) + 1):
        email = EMAIL_PATTERN.format(i)
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
        else:
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": "Load",
                    "last_name": f"Test {i:03d}",
                    "user_type": "System User",
                    "send_welcome_email": 0,
                    "enabled": 1,
                }
            )
            user.insert(ignore_permissions=True)

        existing_roles = {r.role for r in user.roles}
        for role in ROLES:
            if role not in existing_roles and frappe.db.exists("Role", role):
                user.append("roles", {"role": role})

        # Fresh API pair every run so the CSV always holds the live secret.
        api_secret = frappe.generate_hash(length=15)
        user.api_key = user.api_key or frappe.generate_hash(length=15)
        user.api_secret = api_secret
        user.new_password = password
        user.flags.ignore_permissions = True
        user.save()

        _ensure_fiscal_year_access(email, fiscal_years)
        rows.append([email, password, user.api_key, api_secret])

        if i % 20 == 0:
            frappe.db.commit()
            print(f"  {i}/{count} users ready")

    frappe.db.commit()

    path = _csv_path()
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["email", "password", "api_key", "api_secret"])
        writer.writerows(rows)
    os.chmod(path, 0o600)
    print(f"{len(rows)} load-test users ready. Credentials: {path}")


def _ensure_fiscal_year_access(email, fiscal_years):
    """Full-access Fiscal Year Access Control record so the permission SQL
    runs for these users but never denies them."""
    existing = frappe.db.exists("Fiscal Year Access Control", {"user": email})
    if existing:
        return
    doc = frappe.get_doc(
        {
            "doctype": "Fiscal Year Access Control",
            "user": email,
            "full_access": 1,
        }
    )
    doc.insert(ignore_permissions=True)


def delete_users():
    names = frappe.get_all(
        "User", filters={"email": ("like", "loadtest%@avinash.test")}, pluck="name"
    )
    for name in names:
        for acl in frappe.get_all("Fiscal Year Access Control", filters={"user": name}, pluck="name"):
            frappe.delete_doc("Fiscal Year Access Control", acl, ignore_permissions=True, force=True)
        frappe.delete_doc("User", name, ignore_permissions=True, force=True)
    frappe.db.commit()
    print(f"deleted {len(names)} load-test users")
