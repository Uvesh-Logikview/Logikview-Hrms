"""Leave notifications.

The stock notification only reaches `leave_approver`, which is HR for everyone
here - so the employee's own manager, who is the FIRST approver in the two-level
workflow, never heard about a new request. This notifies them in-app.
"""

import frappe
from frappe.utils import getdate


def _user_of(employee):
	return frappe.db.get_value("Employee", employee, "user_id") if employee else None


def _notify(user, subject, message, doc):
	if not user or user == frappe.session.user:
		return
	frappe.get_doc({
		"doctype": "Notification Log", "for_user": user, "type": "Alert",
		"document_type": doc.doctype, "document_name": doc.name,
		"subject": subject, "email_content": message,
	}).insert(ignore_permissions=True)


def notify_manager_on_apply(doc, method=None):
	"""Tell the reporting manager as soon as a leave request is raised."""
	manager = frappe.db.get_value("Employee", doc.employee, "reports_to")
	user = _user_of(manager)
	if not user:
		return

	# only on the first pass (creation / while still awaiting the manager)
	state = (doc.get("workflow_state") or "").lower()
	if state and "applied" not in state and "open" not in state:
		return
	if method == "on_update":
		before = doc.get_doc_before_save()
		if before:                       # already existed - don't repeat on every save
			return

	dates = f"{getdate(doc.from_date).strftime('%d %b')} - {getdate(doc.to_date).strftime('%d %b %Y')}"
	days = doc.get("total_leave_days") or ""
	_notify(user,
	        f"Leave request awaiting your approval - {doc.employee_name}",
	        f"{doc.employee_name} has applied for <b>{doc.leave_type}</b> ({dates}"
	        + (f", {days} day(s)" if days else "") + ")."
	        + (f"<br>Reason: {frappe.utils.escape_html(doc.description)}" if doc.get("description") else ""),
	        doc)
