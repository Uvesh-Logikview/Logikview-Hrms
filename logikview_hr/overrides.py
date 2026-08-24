"""Doctype overrides for Logikview.

Wired through `override_doctype_class` in hooks.py.
"""

import frappe
from frappe import _
from frappe.utils import getdate
from hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request import (
	CompensatoryLeaveRequest,
)
from hrms.hr.utils import throw_overlap_error, validate_active_employee, validate_dates


class LogikviewCompensatoryLeaveRequest(CompensatoryLeaveRequest):
	"""HRMS refuses a comp-off claim unless the employee is marked present on every
	day in the range ("You are not present all day(s) between compensatory leave
	request days"). That blocks legitimate claims here - someone who works a
	holiday often has no check-in for it, and attendance for the day may not have
	been written yet. Logikview allows the request; approval is the control, since
	it still has to pass the reporting manager and HR.

	HRMS's own overlap check also only excludes cancelled requests (docstatus 2),
	but the Comp Off Approval workflow's "Rejected" state leaves the document at
	docstatus 0 (there's no way to jump straight to cancelled from an unsubmitted
	document), so a rejected request blocked the employee from ever re-applying
	for the same dates. validate() is reimplemented here instead of calling
	super(), so the overlap check below can exclude "Rejected" requests too.
	"""

	def validate_attendance(self):
		return

	def _active_overlap(self):
		name = self.name or ("New " + self.doctype)
		return frappe.db.sql(
			"""
			select name from `tabCompensatory Leave Request`
			where name != %(name)s and employee = %(employee)s and docstatus < 2
			and workflow_state != 'Rejected'
			and (work_from_date between %(from_date)s and %(to_date)s
			     or work_end_date between %(from_date)s and %(to_date)s
			     or (work_from_date < %(from_date)s and work_end_date > %(to_date)s))
			""",
			{"employee": self.employee, "from_date": self.work_from_date,
			 "to_date": self.work_end_date, "name": name},
			as_dict=1,
		)

	def validate(self):
		validate_active_employee(self.employee)
		validate_dates(self, self.work_from_date, self.work_end_date)
		if self.half_day:
			if not self.half_day_date:
				frappe.throw(_("Half Day Date is mandatory"))
			if not getdate(self.work_from_date) <= getdate(self.half_day_date) <= getdate(self.work_end_date):
				frappe.throw(_("Half Day Date should be in between Work From Date and Work End Date"))
		conflicting = self._active_overlap()
		if conflicting:
			throw_overlap_error(self, self.employee, conflicting[0].name,
			                     self.work_from_date, self.work_end_date)
		self.validate_holidays()
		self.validate_attendance()
		if not self.leave_type:
			frappe.throw(_("Leave Type is mandatory"))
