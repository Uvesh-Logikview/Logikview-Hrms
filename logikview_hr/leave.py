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
	"""In-app + email (see logikview_hr.notify)."""
	if not user or user == frappe.session.user:
		return
	from logikview_hr.notify import notify
	notify([user], subject, message, doc.doctype, doc.name)


def _hr_users():
	users = frappe.get_all("Has Role", filters={"role": ["in", ["HR Manager", "HR User"]],
	                                            "parenttype": "User"}, pluck="parent")
	return [u for u in set(users) if u and u != "Administrator"
	        and frappe.db.get_value("User", u, "enabled")]


def notify_manager_on_apply(doc, method=None):
	"""Tell the reporting manager as soon as a leave request is raised."""
	mgrs = frappe.db.get_value("Employee", doc.employee,
	                           ["reports_to", "custom_reporting_manager_2"], as_dict=True) or {}
	users = [u for u in (_user_of(mgrs.get("reports_to")),
	                     _user_of(mgrs.get("custom_reporting_manager_2"))) if u]
	if not users:
		return

	# only while still awaiting the manager (this hook only fires on after_insert,
	# so it's the first pass by construction)
	state = (doc.get("workflow_state") or "").lower()
	if state and "applied" not in state and "open" not in state:
		return

	# NB: HRMS already emails the leave_approver (HR) from its own template, so
	# adding them here just delivers the same request twice.

	dates = f"{getdate(doc.from_date).strftime('%d %b')} - {getdate(doc.to_date).strftime('%d %b %Y')}"
	days = doc.get("total_leave_days") or ""
	for user in set(users):
		_notify(user,
	        f"Leave request awaiting your approval - {doc.employee_name}",
	        f"{doc.employee_name} has applied for <b>{doc.leave_type}</b> ({dates}"
	        + (f", {days} day(s)" if days else "") + ")."
	        + (f"<br>Reason: {frappe.utils.escape_html(doc.description)}" if doc.get("description") else ""),
	        doc)
