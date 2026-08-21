"""Doctype overrides for Logikview.

Wired through `override_doctype_class` in hooks.py.
"""

from hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request import (
	CompensatoryLeaveRequest,
)


class LogikviewCompensatoryLeaveRequest(CompensatoryLeaveRequest):
	"""HRMS refuses a comp-off claim unless the employee is marked present on every
	day in the range ("You are not present all day(s) between compensatory leave
	request days"). That blocks legitimate claims here - someone who works a
	holiday often has no check-in for it, and attendance for the day may not have
	been written yet. Logikview allows the request; approval is the control, since
	it still has to pass the reporting manager and HR.
	"""

	def validate_attendance(self):
		return
