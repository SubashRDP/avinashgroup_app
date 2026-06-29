// On saving a Customer/Supplier, warn if another party of the same type in the
// same company (custom_company) already uses the same name or tax_id. The save
// is paused and only goes through if the user clicks "Yes" on the confirm dialog.

frappe.ui.form.on("Customer", {
	validate(frm) {
		return check_party_duplicates(frm, "Customer", "customer_name");
	},
});

frappe.ui.form.on("Supplier", {
	validate(frm) {
		return check_party_duplicates(frm, "Supplier", "supplier_name");
	},
});

async function check_party_duplicates(frm, doctype, name_field) {
	const company = frm.doc.custom_company;
	if (!company) return;

	// Duplicate name -> ask "Do you want to create it again?"
	const name_value = (frm.doc[name_field] || "").trim();
	if (name_value) {
		const dup = await find_duplicate(doctype, name_field, name_value, company, frm.doc.name);
		if (dup) {
			const ok = await confirm_save(
				__("{0} {1} already exists for company {2} ({3}).", [
					doctype,
					name_value.bold(),
					company.bold(),
					party_link(doctype, dup),
				]),
				__("Do you want to create it again?")
			);
			if (!ok) {
				frappe.validated = false;
				return;
			}
		}
	}

	// Duplicate tax_id -> ask "Do you want to continue?"
	const tax_id = (frm.doc.tax_id || "").trim();
	if (tax_id) {
		const dup = await find_duplicate(doctype, "tax_id", tax_id, company, frm.doc.name);
		if (dup) {
			const ok = await confirm_save(
				__("Tax ID {0} already exists for company {1} ({2} {3}).", [
					tax_id.bold(),
					company.bold(),
					doctype,
					party_link(doctype, dup),
				]),
				__("Do you want to continue?")
			);
			if (!ok) {
				frappe.validated = false;
				return;
			}
		}
	}
}

// Show a Yes/No confirm and resolve to true only when the user clicks Yes.
function confirm_save(message, question) {
	return new Promise((resolve) => {
		frappe.confirm(
			message + "<br><br>" + question,
			() => resolve(true),
			() => resolve(false)
		);
	});
}

async function find_duplicate(doctype, field, value, company, current_name) {
	const r = await frappe.db.get_value(
		doctype,
		{ [field]: value, custom_company: company, name: ["!=", current_name || ""] },
		"name"
	);
	return r && r.message && r.message.name ? r.message.name : null;
}

function party_link(doctype, name) {
	const route = frappe.router.slug(doctype);
	return `<a href="/app/${route}/${encodeURIComponent(name)}">${name.bold()}</a>`;
}
