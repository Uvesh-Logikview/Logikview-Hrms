"""Link-field queries that restrict pickers to the people who may actually be
chosen (the stock fields list every user in the system)."""

import frappe

APPROVER_ROLES = ("Expense Approver", "HR Manager", "HR User")


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def approver_query(doctype, txt, searchfield, start, page_len, filters):
	"""Users who are authorised to approve: reporting managers / team leads /
	project managers (anyone with direct reports), the directors, and HR."""
	txt = f"%{txt or ''}%"
	return frappe.db.sql("""
		select distinct u.name, u.full_name
		from `tabUser` u
		inner join `tabHas Role` r on r.parent = u.name and r.parenttype = 'User'
		where u.enabled = 1
		  and u.name not in ('Administrator', 'Guest')
		  and r.role in %(roles)s
		  and (u.name like %(txt)s or u.full_name like %(txt)s)
		order by u.full_name
		limit %(start)s, %(page_len)s""",
		{"roles": APPROVER_ROLES, "txt": txt, "start": start, "page_len": page_len})


@frappe.whitelist()
def default_employee():
	"""The employee to preselect on a new form: only when the user has exactly one
	to choose from (a regular employee sees just themselves). HR/admin, who pick
	from everyone, get no default."""
	from logikview_hr.permissions import _has_full_access, _visible_employees

	user = frappe.session.user
	if _has_full_access(user):
		return None
	visible = _visible_employees(user)
	return visible[0] if len(visible) == 1 else None


def grant_approver_roles():
	"""Give the Expense Approver role to everyone who genuinely approves:
	anyone with direct reports, the two directors, and HR."""
	emps = set(frappe.get_all("Employee", filters={"reports_to": ["!=", ""]}, pluck="reports_to"))
	try:
		s = frappe.get_single("Logikview Appraisal Settings")
		emps.update([s.director_one, s.director_two])
	except Exception:
		pass
	emps.discard(None)

	users = {u for u in (frappe.db.get_value("Employee", e, "user_id") for e in emps) if u}
	users.update(frappe.get_all("Has Role", filters={"role": ["in", ["HR Manager", "HR User"]],
	                                                 "parenttype": "User"}, pluck="parent"))
	granted = []
	for u in users:
		if u in ("Administrator", "Guest") or not frappe.db.get_value("User", u, "enabled"):
			continue
		if frappe.db.exists("Has Role", {"parent": u, "role": "Expense Approver", "parenttype": "User"}):
			continue
		row = frappe.new_doc("Has Role")
		row.parent, row.parenttype, row.parentfield = u, "User", "roles"
		row.role = "Expense Approver"
		row.db_insert()          # bypass User.save() so this can run without a worker
		granted.append(u)
	frappe.clear_cache()
	frappe.db.commit()
	return granted
