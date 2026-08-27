# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt
#
# Override of frappe.desk.reportview.export_query — the CSV/Excel export behind the
# Report View "Export" button. Core export dumps the raw stored value for every
# column, so a Link column (e.g. Sales Invoice's "Customer Group") exports the linked
# record's id (e.g. "NGG-CGR-00002") even though the grid displays its title
# ("Dealer"). This override resolves Link columns to the linked record's display name
# before the file is written, for every doctype/report, the same way
# query_report.get_data_for_custom_field already does for the "Add Column" dialog.

import frappe
from frappe import _
from frappe.desk.reportview import get_form_params, parse_field

from avinashgroup_app.custom_code.Override.query_report import _link_display_map


@frappe.whitelist()
def export_query():
	"""export from report builder"""
	from frappe.desk.utils import pop_csv_params

	form_params = get_form_params()
	form_params["limit_page_length"] = None
	form_params["as_list"] = True
	csv_params = pop_csv_params(form_params)
	export_in_background = int(form_params.pop("export_in_background", 0))

	if export_in_background:
		user = frappe.session.user
		user_email = frappe.get_cached_value("User", user, "email")
		frappe.enqueue(
			"avinashgroup_app.custom_code.Override.reportview.run_report_view_export_job",
			user_email=user_email,
			form_params=form_params,
			csv_params=csv_params,
			queue="long",
			now=frappe.flags.in_test,
		)

		frappe.msgprint(
			_(
				"Your report is being generated in the background. You will receive an email on {0} with a download link once it is ready."
			).format(user_email)
		)
		return

	return _export_query(form_params, csv_params)


def run_report_view_export_job(user_email, form_params, csv_params):
	from frappe.desk.utils import send_report_email

	report_name, file_extension, content = _export_query(form_params, csv_params, populate_response=False)
	send_report_email(user_email, report_name, file_extension, content, attached_to_name=report_name)


def _export_query(form_params, csv_params, populate_response=True):
	from frappe.core.doctype.access_log.access_log import make_access_log
	from frappe.desk.reportview import append_totals_row, get_field_info, handle_duration_fieldtype_values
	from frappe.desk.utils import get_csv_bytes, provide_binary_file
	from frappe.model.db_query import DatabaseQuery
	from frappe.utils.xlsxutils import handle_html, make_xlsx

	doctype = form_params.pop("doctype")
	if isinstance(form_params["fields"], list):
		form_params["fields"].append("owner")
	elif isinstance(form_params["fields"], tuple):
		form_params["fields"] = form_params["fields"] + ("owner",)
	file_format_type = form_params.pop("file_format_type")
	title = form_params.pop("title", doctype)
	add_totals_row = 1 if form_params.pop("add_totals_row", None) == "1" else None
	translate_values = 1 if form_params.pop("translate_values", None) == "1" else None

	if selection := form_params.pop("selected_items", None):
		import json

		form_params["filters"] = {"name": ("in", json.loads(selection))}

	make_access_log(
		doctype=doctype,
		file_type=file_format_type,
		report_name=form_params.report_name,
		filters=form_params.filters,
	)

	db_query = DatabaseQuery(doctype)
	ret = db_query.execute(**form_params)

	if not frappe.permissions.can_export(doctype):
		if frappe.permissions.can_export(doctype, is_owner=True):
			for row in ret:
				if row[-1] != frappe.session.user:
					raise frappe.PermissionError(
						_("You are not allowed to export {} doctype").format(doctype)
					)
		else:
			raise frappe.PermissionError(_("You are not allowed to export {} doctype").format(doctype))

	ret = _resolve_link_columns(ret, db_query.fields, doctype)

	if add_totals_row:
		ret = append_totals_row(ret)

	fields_info = get_field_info(db_query.fields, doctype)

	labels = [info["label"] for info in fields_info]
	data = [[_("Sr"), *labels]]
	processed_data = []

	if frappe.local.lang == "en" or not translate_values:
		data.extend([i + 1, *list(row)] for i, row in enumerate(ret))
	elif translate_values:
		translatable_fields = [field["translatable"] for field in fields_info]
		processed_data = []
		for i, row in enumerate(ret):
			processed_row = [i + 1] + [
				_(value) if translatable_fields[idx] else value for idx, value in enumerate(row)
			]
			processed_data.append(processed_row)
		data.extend(processed_data)

	data = handle_duration_fieldtype_values(doctype, data, db_query.fields)

	if file_format_type == "CSV":
		file_extension = "csv"
		content = get_csv_bytes(
			[[handle_html(frappe.as_unicode(v)) if isinstance(v, str) else v for v in r] for r in data],
			csv_params,
		)
	elif file_format_type == "Excel":
		file_extension = "xlsx"
		content = make_xlsx(data, doctype).getvalue()

	if not populate_response:
		return title, file_extension, content

	provide_binary_file(_(title), file_extension, content)


def _resolve_link_columns(rows, fields, doctype):
	"""Swap each Link column's stored id for the linked record's display name."""
	rows = [list(row) for row in rows]
	if not rows:
		return rows

	for idx, key in enumerate(fields):
		try:
			parenttype, fieldname = parse_field(key)
		except ValueError:
			continue

		df = frappe.get_meta(parenttype or doctype).get_field(fieldname)
		if not (df and df.fieldtype == "Link" and df.options):
			continue

		ids = {row[idx] for row in rows if row[idx]}
		name_map = _link_display_map(df.options, list(ids))
		if not name_map:
			continue

		for row in rows:
			if row[idx] in name_map:
				row[idx] = name_map[row[idx]]

	return [tuple(row) for row in rows]
