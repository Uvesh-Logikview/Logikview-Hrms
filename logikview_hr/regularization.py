"""Regularization (Attendance Request) helpers.

When HR writes a warning/note on a regularization, the employee is told about it
in-app (there is no SMTP on this bench).
"""

import frappe
from frappe.utils import getdate


def notify_warning(doc, method=None):
	"""Send the employee a notification when HR adds or changes the warning note."""
	note = (doc.get("custom_hr_warning") or "").strip()
	if not note:
		return

	before = doc.get_doc_before_save()
	if before and (before.get("custom_hr_warning") or "").strip() == note:
		return  # unchanged - don't nag on every save

	user = frappe.db.get_value("Employee", doc.employee, "user_id")
	if not user or user == frappe.session.user:
		return

	day = getdate(doc.from_date).strftime("%d %b %Y") if doc.from_date else ""
	category = doc.get("custom_late_category")
	subject = f"Note from HR on your regularization ({day})"
	message = (
		(f"<b>{category}</b><br>" if category else "")
		+ f"HR has added a note on your regularization for <b>{day}</b>:<br><br>"
		+ frappe.utils.escape_html(note).replace("\n", "<br>")
	)

	frappe.get_doc({
		"doctype": "Notification Log",
		"for_user": user,
		"type": "Alert",
		"document_type": doc.doctype,
		"document_name": doc.name,
		"subject": subject,
		"email_content": message,
	}).insert(ignore_permissions=True)
