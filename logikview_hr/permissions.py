"""Row-level visibility: regular employees see only their own records; managers
also see their direct reports (needed for leave/expense approval); HR/admin see all.

Wired via `permission_query_conditions` (list filtering) and `has_permission`
(direct doc access) in hooks.py.
"""

import frappe

# roles that may see every employee's data
FULL_ACCESS_ROLES = {"HR Manager", "HR User", "System Manager"}

# system-managed records: employees may only READ their own — never create/edit/delete
# (check-ins & attendance are created by the check-in server script, not by hand)
READ_ONLY_FOR_EMPLOYEE = {"Employee Checkin", "Attendance", "Leave Allocation"}


def _has_full_access(user):
	return bool(FULL_ACCESS_ROLES & set(frappe.get_roles(user)))


def _visible_employees(user):
	"""Own employee + direct reports (so managers can approve their team)."""
	emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not emp:
		return []
	allowed = {emp}
	allowed.update(frappe.get_all("Employee", filters={"reports_to": emp}, pluck="name"))
	return list(allowed)


def _in_clause(names):
	return ", ".join(frappe.db.escape(n) for n in names)


# ---------------- Employee doctype (matched on `name`) ----------------
def employee_query(user):
	user = user or frappe.session.user
	if _has_full_access(user):
		return ""
	names = _visible_employees(user)
	return f"`tabEmployee`.name in ({_in_clause(names)})" if names else "1=0"


def employee_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _has_full_access(user):
		return True
	return doc.name in _visible_employees(user)


# ---------- doctypes with an `employee` link field ----------
def _linked_query(user, table):
	user = user or frappe.session.user
	if _has_full_access(user):
		return ""
	names = _visible_employees(user)
	return f"`{table}`.`employee` in ({_in_clause(names)})" if names else "1=0"


def attendance_query(user):
	return _linked_query(user, "tabAttendance")


def leave_application_query(user):
	return _linked_query(user, "tabLeave Application")


def employee_checkin_query(user):
	return _linked_query(user, "tabEmployee Checkin")


def expense_claim_query(user):
	return _linked_query(user, "tabExpense Claim")


def attendance_request_query(user):
	return _linked_query(user, "tabAttendance Request")


def leave_allocation_query(user):
	return _linked_query(user, "tabLeave Allocation")


def employee_linked_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _has_full_access(user):
		return True
	# check-ins / attendance / allocations are system-managed: read-only for employees
	if doc.doctype in READ_ONLY_FOR_EMPLOYEE and ptype and ptype not in ("read", "select"):
		return False
	return doc.get("employee") in _visible_employees(user)


# ---------------- Logikview Appraisal ----------------
# Visible to: the employee, their reporting officer, the director(s) in the chain,
# and HR/admin. Everyone else is filtered out.
def appraisal_query(user):
	user = user or frappe.session.user
	if _has_full_access(user):
		return ""
	emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not emp:
		return "1=0"
	e = frappe.db.escape(emp)
	t = "`tabLogikview Appraisal`"
	return (f"({t}.`employee`={e} or {t}.`reporting_officer`={e} "
	        f"or {t}.`first_director`={e} or {t}.`second_director`={e} "
	        f"or {t}.`cc_director`={e})")


def appraisal_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _has_full_access(user):
		return True
	emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not emp:
		return False
	return emp in (doc.get("employee"), doc.get("reporting_officer"),
	               doc.get("first_director"), doc.get("second_director"),
	               doc.get("cc_director"))
