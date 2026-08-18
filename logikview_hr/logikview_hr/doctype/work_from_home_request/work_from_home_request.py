# Copyright (c) 2026, Logikview Analytics and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, getdate


class WorkFromHomeRequest(Document):
	def validate(self):
		if not self.employee:
			self.employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		if self.employee and not self.reporting_officer:
			self.reporting_officer = frappe.db.get_value("Employee", self.employee, "reports_to")

		if self.from_date and self.to_date:
			if getdate(self.to_date) < getdate(self.from_date):
				frappe.throw(frappe._("To Date cannot be before From Date"))
			self.total_days = date_diff(self.to_date, self.from_date) + 1

		self._check_overlap()

		if not self.workflow_state:
			self.workflow_state = "Pending Manager Approval"

	def _check_overlap(self):
		if not (self.employee and self.from_date and self.to_date):
			return
		clash = frappe.db.sql("""
			select name from `tabWork From Home Request`
			where employee = %(employee)s and name != %(name)s
			  and workflow_state != 'Rejected'
			  and from_date <= %(to_date)s and to_date >= %(from_date)s
			limit 1""", {
			"employee": self.employee, "name": self.name or "",
			"from_date": self.from_date, "to_date": self.to_date,
		})
		if clash:
			frappe.throw(frappe._("You already have a work-from-home request covering these dates ({0})")
			             .format(clash[0][0]))

	def on_update(self):
		before = self.get_doc_before_save()
		if not before or before.workflow_state == self.workflow_state:
			return
		_notify_state_change(self)


def _user_of(employee):
	return frappe.db.get_value("Employee", employee, "user_id") if employee else None


def _hr_users():
	users = frappe.get_all("Has Role", filters={"role": ["in", ["HR Manager", "HR User"]],
	                                            "parenttype": "User"}, pluck="parent")
	return [u for u in set(users) if u and u != "Administrator"
	        and frappe.db.get_value("User", u, "enabled")]


def _notify(users, subject, message, docname):
	for user in {u for u in users if u}:
		frappe.get_doc({
			"doctype": "Notification Log", "for_user": user, "type": "Alert",
			"document_type": "Work From Home Request", "document_name": docname,
			"subject": subject, "email_content": message,
		}).insert(ignore_permissions=True)


def _notify_state_change(doc):
	dates = f"{getdate(doc.from_date).strftime('%d %b')} - {getdate(doc.to_date).strftime('%d %b %Y')}"
	state = doc.workflow_state

	if state == "Pending Manager Approval":
		_notify([_user_of(doc.reporting_officer)],
		        f"WFH request awaiting your approval - {doc.employee_name}",
		        f"{doc.employee_name} has requested to work from home ({dates}).<br>"
		        f"Reason: {frappe.utils.escape_html(doc.reason or '')}", doc.name)
	elif state == "Pending HR Approval":
		_notify(_hr_users(),
		        f"WFH request approved by manager - {doc.employee_name}",
		        f"{doc.employee_name}'s work-from-home request ({dates}) was approved by their "
		        f"manager and needs HR sign-off.", doc.name)
		_notify([_user_of(doc.employee)],
		        "Your WFH request was approved by your manager",
		        f"Your work-from-home request ({dates}) is now with HR for final approval.", doc.name)
	elif state in ("Approved", "Rejected"):
		_notify([_user_of(doc.employee), _user_of(doc.reporting_officer)],
		        f"Your WFH request was {state.lower()}",
		        f"Your work-from-home request ({dates}) was <b>{state.lower()}</b>."
		        + (f"<br>HR: {frappe.utils.escape_html(doc.hr_comment)}" if doc.hr_comment else ""),
		        doc.name)
