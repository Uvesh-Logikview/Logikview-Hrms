"""Row-level visibility: regular employees see only their own records; managers
also see their direct reports (needed for leave/expense approval); HR/admin see all.

Wired via `permission_query_conditions` (list filtering) and `has_permission`
(direct doc access) in hooks.py.
"""

import frappe

# roles that may see every employee's data
FULL_ACCESS_ROLES = {"HR Manager", "HR User", "System Manager"}


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
	return doc.get("employee") in _visible_employees(user)
