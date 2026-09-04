# Copyright (c) 2026, Logikview Analytics and contributors
# For license information, please see license.txt

"""HR's exportable source of truth for Casual Leave balance - the same figure
and the same get_casual_leave_balance() calculation as the employee dashboard
tile and the Leave Management team view, so a number pulled here for manual
salary processing never disagrees with what an employee sees on their own
dashboard.

Distinguishes Accrued, Used, Advance/Loan and Current Available Balance as
separate columns rather than one blended figure - Current Available Balance
is the one to use for payroll; the others are there so HR can see how it was
arrived at."""

import frappe
from frappe.utils import getdate, today

from logikview_hr.casual_leave import ADVANCE_LIMIT, get_casual_leave_balance


def execute(filters=None):
	filters = frappe._dict(filters or {})
	as_of = getdate(filters.as_of_date or today())

	columns = [
		{"label": "Employee", "fieldname": "employee", "fieldtype": "Link",
		 "options": "Employee", "width": 100},
		{"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
		{"label": "Department", "fieldname": "department", "fieldtype": "Data", "width": 140},
		{"label": "Accrued to Date", "fieldname": "accrued", "fieldtype": "Float", "width": 120},
		{"label": "Taken", "fieldname": "taken", "fieldtype": "Float", "width": 90},
		{"label": "Advance/Loan Used", "fieldname": "advance_used", "fieldtype": "Float", "width": 130},
		{"label": "Current Available Balance", "fieldname": "balance", "fieldtype": "Float", "width": 170},
		{"label": "Advance Limit", "fieldname": "advance_limit", "fieldtype": "Float", "width": 100},
		{"label": "Annual Entitlement", "fieldname": "annual_entitlement", "fieldtype": "Float", "width": 120},
	]

	emp_filters = {"status": "Active"}
	if filters.department:
		emp_filters["department"] = filters.department

	data = []
	for e in frappe.get_all("Employee", filters=emp_filters,
	                        fields=["name", "employee_name", "department"],
	                        order_by="employee_name"):
		dept = (e.department or "")
		if dept.endswith(" - LA"):
			dept = dept[:-5]
		cl = get_casual_leave_balance(e.name, as_of=as_of)
		data.append({
			"employee": e.name, "employee_name": e.employee_name, "department": dept,
			"accrued": cl["accrued"], "taken": cl["taken"], "advance_used": cl["advance_used"],
			"balance": cl["balance"], "advance_limit": ADVANCE_LIMIT, "annual_entitlement": 12,
		})

	return columns, data
