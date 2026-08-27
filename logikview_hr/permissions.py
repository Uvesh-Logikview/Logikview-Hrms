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

# employees may create/edit their own request, but never delete it outright -
# base DocPerm grants delete=1 on these (so the doctype's own "withdraw" flow
# works before HR involvement), which also happened to let an employee erase
# an already-decided record. Rejecting/cancelling is the correct undo, not
# deleting history.
NO_DELETE_FOR_EMPLOYEE = {"Attendance Request", "Compensatory Leave Request",
                          "Work From Home Request"}


def _has_full_access(user):
	return bool(FULL_ACCESS_ROLES & set(frappe.get_roles(user)))


def _visible_employees(user):
	"""Own employee + direct reports (so managers can approve their team)."""
	emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not emp:
		return []
	allowed = {emp}
	allowed.update(frappe.get_all("Employee", filters={"reports_to": emp}, pluck="name"))
	# an employee may have a second reporting manager; they approve for the same people
	allowed.update(frappe.get_all("Employee",
	                              filters={"custom_reporting_manager_2": emp}, pluck="name"))
	return list(allowed)


def _in_clause(names):
	return ", ".join(frappe.db.escape(n) for n in names)


# ---------------- Employee doctype (matched on `name`) ----------------
def employee_query(user):
	user = user or frappe.session.user
	if _has_full_access(user):
		return ""
	names = set(_visible_employees(user))
	# records the user has been assigned a task on
	names.update(frappe.get_all("ToDo", filters={
		"allocated_to": user, "reference_type": "Employee", "status": ["!=", "Cancelled"],
	}, pluck="reference_name"))
	names = [n for n in names if n]
	return f"`tabEmployee`.name in ({_in_clause(names)})" if names else "1=0"


def _assigned_to_me(doctype, name, user):
	"""True if the user has an open assignment (ToDo) on this document. Someone
	given a task on a record has to be able to open that record, otherwise the
	assignment is invisible to them."""
	return bool(frappe.db.exists("ToDo", {
		"allocated_to": user, "reference_type": doctype,
		"reference_name": name, "status": ["!=", "Cancelled"],
	}))


def employee_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _has_full_access(user):
		return True
	if doc.name in _visible_employees(user):
		return True
	# read-only peek at a colleague's record you've been assigned a task on
	return ptype in (None, "read", "select") and _assigned_to_me("Employee", doc.name, user)


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


def employee_document_query(user):
	"""Your own documents; HR sees everyone's."""
	return _linked_query(user, "tabEmployee Document")


def comp_off_query(user):
	"""Own requests + the ones you approve."""
	return _linked_query(user, "tabCompensatory Leave Request")


def wfh_request_query(user):
	"""Own requests + the ones you approve (your direct reports)."""
	return _linked_query(user, "tabWork From Home Request")


def employee_linked_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _has_full_access(user):
		return True
	# check-ins / attendance / allocations are system-managed: read-only for employees
	if doc.doctype in READ_ONLY_FOR_EMPLOYEE and ptype and ptype not in ("read", "select"):
		return False
	if ptype == "delete" and doc.doctype in NO_DELETE_FOR_EMPLOYEE:
		return False
	emp = doc.get("employee")
	if not emp:
		# Attaching a file happens before the document is saved, so Frappe checks
		# permission against an unsaved doc whose employee link isn't set yet.
		# Refusing here blocked employees from uploading their own documents; the
		# row-level query still limits what they can see, and the controller fills
		# in the employee on save.
		return True
	return emp in _visible_employees(user)


# ---------------- hidden service accounts ----------------
# Accounts that should not show up in the User list (or in user pickers) for
# anyone except themselves and the Administrator.
HIDDEN_USERS = ("logikviewhr@logikview.com",)


def user_query(user):
	user = user or frappe.session.user
	if user == "Administrator" or user in HIDDEN_USERS or _has_full_access(user):
		return ""
	# regular employees: only their own account, not the whole company directory
	return f"`tabUser`.name = {frappe.db.escape(user)}"


def user_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if user == "Administrator" or user in HIDDEN_USERS or _has_full_access(user):
		return True
	# doctype-level checks (no specific document, e.g. "can this role ever read
	# User at all") come through with doc=None - let the base role permission
	# decide those; a None here used to hit doc.name and blow up, which some
	# Frappe versions then silently treat as "permission granted"
	if doc is None:
		return True
	if doc.name in HIDDEN_USERS:
		return False
	return doc.name == user


# ---------------- Logikview Appraisal ----------------
# Visible to: the employee, their reporting officer, the director(s) in the chain,
# and HR/admin. Everyone else is filtered out.

# A director is only involved once the manager has finished their review, so
# they only see appraisals that have actually reached them. Without this every
# director saw all ~18 appraisals, including ones still sitting with the
# employee, which buried the handful actually waiting on them. Completed is
# kept so they retain the history of what they signed off.
DIRECTOR_VISIBLE_STATES = ("Pending Director Review", "Pending Final Director", "Completed")


def appraisal_query(user):
	user = user or frappe.session.user
	if _has_full_access(user):
		return ""
	emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not emp:
		return "1=0"
	e = frappe.db.escape(emp)
	t = "`tabLogikview Appraisal`"
	states = ", ".join(frappe.db.escape(s) for s in DIRECTOR_VISIBLE_STATES)
	as_director = (f"(({t}.`first_director`={e} or {t}.`second_director`={e} "
	               f"or {t}.`cc_director`={e}) and {t}.`workflow_state` in ({states}))")
	return f"({t}.`employee`={e} or {t}.`reporting_officer`={e} or {as_director})"


def appraisal_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _has_full_access(user):
		return True
	if ptype == "delete":
		return False
	emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not emp:
		return False
	if emp in (doc.get("employee"), doc.get("reporting_officer")):
		return True
	# same director rule as the list query, so a direct link can't sidestep it
	if emp in (doc.get("first_director"), doc.get("second_director"), doc.get("cc_director")):
		return doc.get("workflow_state") in DIRECTOR_VISIBLE_STATES
	return False
