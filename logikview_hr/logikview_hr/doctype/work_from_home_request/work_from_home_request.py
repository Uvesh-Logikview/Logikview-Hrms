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
		if self.employee:
			self.second_reporting_officer = frappe.db.get_value(
				"Employee", self.employee, "custom_reporting_manager_2")

		if self.from_date and self.to_date:
			if getdate(self.to_date) < getdate(self.from_date):
				frappe.throw(frappe._("To Date cannot be before From Date"))
			self.total_days = date_diff(self.to_date, self.from_date) + 1

		self._check_overlap()
		self._check_policy()

		if not self.workflow_state:
			self.workflow_state = "Pending Manager Approval"

	def _check_policy(self):
		"""Company WFH policy: not on a Monday or Friday, and at most one WFH day
		in any given week. HR/admin can override."""
		from logikview_hr.regularization import _has_full_access
		if _has_full_access(frappe.session.user) or not (self.from_date and self.to_date):
			return

		from frappe.utils import add_days, date_diff, get_weekday

		blocked = []
		day = getdate(self.from_date)
		for _ in range(date_diff(self.to_date, self.from_date) + 1):
			if get_weekday(day) in ("Monday", "Friday"):
				blocked.append(f"{day.strftime('%d %b')} ({get_weekday(day)})")
			day = getdate(add_days(day, 1))
		if blocked:
			frappe.throw(
				frappe._("Work from home is not allowed on Mondays or Fridays: {0}")
				.format(", ".join(blocked)), title=frappe._("Not allowed by policy"))

		# max 1 WFH day per week (Mon-Sun), counting other live requests
		day = getdate(self.from_date)
		for _ in range(date_diff(self.to_date, self.from_date) + 1):
			week_start = add_days(day, -day.weekday())
			week_end = add_days(week_start, 6)
			used = frappe.db.sql("""
				select count(*) from `tabWork From Home Request`
				where employee = %(employee)s and name != %(name)s
				  and workflow_state != 'Rejected'
				  and from_date <= %(week_end)s and to_date >= %(week_start)s""",
				{"employee": self.employee, "name": self.name or "",
				 "week_start": week_start, "week_end": week_end})[0][0]
			if used or date_diff(self.to_date, self.from_date) >= 1:
				if used:
					frappe.throw(
						frappe._("You may take at most 1 work-from-home day per week. "
						         "You already have a request in the week of {0}.")
						.format(getdate(week_start).strftime("%d %b %Y")),
						title=frappe._("Weekly limit reached"))
				frappe.throw(
					frappe._("You may take at most 1 work-from-home day per week, "
					         "so please raise a single-day request."),
					title=frappe._("Weekly limit reached"))
			day = getdate(add_days(day, 1))

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
		# a brand-new request has no "before" snapshot, but its workflow_state
		# still just changed (from nothing to Pending Manager Approval) - that
		# case was being treated as "nothing changed" and skipped, so the
		# manager was never told a request existed in the first place
		before = self.get_doc_before_save()
		if before and before.workflow_state == self.workflow_state:
			return
		_notify_state_change(self)


def _user_of(employee):
	return frappe.db.get_value("Employee", employee, "user_id") if employee else None


def _hr_users():
	users = frappe.get_all("Has Role", filters={"role": ["in", ["HR Manager", "HR User"]],
	                                            "parenttype": "User"}, pluck="parent")
	return [u for u in set(users) if u and u != "Administrator"
	        and frappe.db.get_value("User", u, "enabled")]


def _notify(users, subject, message, docname, dedup_key=None):
	"""In-app + email (see logikview_hr.notify)."""
	from logikview_hr.notify import notify
	notify(users, subject, message, "Work From Home Request", docname, dedup_key=dedup_key)


def _notify_state_change(doc):
	dates = f"{getdate(doc.from_date).strftime('%d %b')} - {getdate(doc.to_date).strftime('%d %b %Y')}"
	state = doc.workflow_state

	if state == "Pending Manager Approval":
		_notify([_user_of(doc.reporting_officer), _user_of(doc.get("second_reporting_officer"))],
		        f"WFH request awaiting your approval - {doc.employee_name}",
		        f"{doc.employee_name} has requested to work from home ({dates}).<br>"
		        f"Reason: {frappe.utils.escape_html(doc.reason or '')}", doc.name)
	elif state == "Pending HR Approval":
		# HR needs to know it's their turn; the employee does not get a mail
		# here - they get exactly one, on final approval/rejection below
		_notify(_hr_users(),
		        f"WFH request approved by manager - {doc.employee_name}",
		        f"{doc.employee_name}'s work-from-home request ({dates}) was approved by their "
		        f"manager and needs HR sign-off.", doc.name)
	elif state in ("Approved", "Rejected"):
		# final decision - only the employee, not the manager(s) who already
		# got their own "approved by manager" / earlier-stage notice
		_notify([_user_of(doc.employee)],
		        f"Your WFH request was {state.lower()}",
		        f"Your work-from-home request ({dates}) was <b>{state.lower()}</b>."
		        + (f"<br>HR: {frappe.utils.escape_html(doc.hr_comment)}" if doc.hr_comment else ""),
		        doc.name)


def send_pending_approval_reminders():
	"""Daily: nudge the manager/TL for every request still sitting at
	Pending Manager Approval - the one-time notice on creation is easy to miss
	in a busy inbox, so this repeats until they act."""
	day = frappe.utils.today()
	for doc in frappe.get_all("Work From Home Request",
	                         filters={"workflow_state": "Pending Manager Approval"},
	                         fields=["name", "employee_name", "reporting_officer",
	                                 "second_reporting_officer", "from_date", "to_date", "reason"]):
		dates = f"{getdate(doc.from_date).strftime('%d %b')} - {getdate(doc.to_date).strftime('%d %b %Y')}"
		_notify([_user_of(doc.reporting_officer), _user_of(doc.get("second_reporting_officer"))],
		        f"Reminder: WFH request awaiting your approval - {doc.employee_name}",
		        f"{doc.employee_name}'s work-from-home request ({dates}) is still awaiting your "
		        f"approval.<br>Reason: {frappe.utils.escape_html(doc.reason or '')}",
		        doc.name, dedup_key=f"pending-reminder-{day}")
