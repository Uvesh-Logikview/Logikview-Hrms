import json

import frappe

# Replicates the hrsystem/snaphire desk: the check-in card + Employee Details
# shortcuts on the standard Home workspace, and the same trimmed sidebar
# (is_hidden on non-HR workspaces) shown to every role.

CARD = "Checkin button functionality"
CALENDAR = "Attendance Calendar"
DASHBOARD = "Attendance Dashboard"

# Workspaces visible in the sidebar (everything else is hidden) — matches hrsystem.
VISIBLE = {
	"Home",
	"HR",
	"Recruitment",
	"Employee Lifecycle",
	"Performance",
	"Shift & Attendance",
	"Expense Claims",
	"Leaves",
	"Salary Payout",
	"Tax & Benefits",
}

# Employee Details shortcuts on Home (order matters; label must match the
# shortcut_name used in the workspace content).
SHORTCUTS = [
	{"type": "DocType", "link_to": "Employee", "label": "Employee", "color": "Blue",
	 "doc_view": "List", "stats_filter": '[["Employee","status","=","Active",false]]'},
	{"type": "DocType", "link_to": "Attendance", "label": "Attendance", "color": "",
	 "doc_view": "", "stats_filter": "[]"},
	{"type": "DocType", "link_to": "Leave Application", "label": "Leave Application", "color": "Grey",
	 "doc_view": "List", "stats_filter": "[]"},
	{"type": "DocType", "link_to": "Employee Checkin", "label": "Employee Checkin", "color": "Blue",
	 "doc_view": "List", "stats_filter": "[]"},
	{"type": "DocType", "link_to": "Attendance Request", "label": "Attendance Request", "color": "Blue",
	 "doc_view": "List", "stats_filter": "[]"},
	{"type": "DocType", "link_to": "Expense Claim", "label": "Expense Claim", "color": "Blue",
	 "doc_view": "List", "stats_filter": "[]"},
	{"type": "DocType", "link_to": "Logikview Appraisal", "label": "Appraisal", "color": "Green",
	 "doc_view": "List", "stats_filter": "[]"},
	{"type": "DocType", "link_to": "Fun Friday Idea", "label": "Fun Friday", "color": "Orange",
	 "doc_view": "List", "stats_filter": "[]"},
]


def _home_content():
	blocks = [
		{"id": "lvh_card", "type": "custom_block", "data": {"custom_block_name": CARD, "col": 12}},
		{"id": "lvh_hdr", "type": "header",
		 "data": {"text": '<span class="h4"><b>Employee Details</b></span>', "col": 12}},
	]
	for i, s in enumerate(SHORTCUTS):
		blocks.append({"id": f"lvh_sc{i}", "type": "shortcut",
		               "data": {"shortcut_name": s["label"], "col": 4}})
	# Team attendance report — role-gated to HR/admin (block carries its own title),
	# so only HR Manager / System Manager see it on Home; employees don't.
	blocks.append({"id": "lvh_dash_home", "type": "custom_block",
	               "data": {"custom_block_name": DASHBOARD, "col": 12}})
	blocks.append({"id": "lvh_cal_hdr", "type": "header",
	               "data": {"text": '<span class="h4"><b>Attendance Calendar</b></span>', "col": 12}})
	blocks.append({"id": "lvh_cal", "type": "custom_block",
	               "data": {"custom_block_name": CALENDAR, "col": 12}})
	return json.dumps(blocks)


def _setup_home():
	ws = frappe.get_doc("Workspace", "Home")
	ws.public = 1
	ws.is_hidden = 0
	ws.content = _home_content()
	ws.set("shortcuts", [])
	for i, s in enumerate(SHORTCUTS, start=1):
		ws.append("shortcuts", {**s, "idx": i})
	# a content custom_block resolves by matching custom_block_name against the
	# child row's label, so label MUST equal the block name.
	ws.set("custom_blocks", [{"custom_block_name": CARD, "label": CARD},
	                         {"custom_block_name": CALENDAR, "label": CALENDAR},
	                         {"custom_block_name": DASHBOARD, "label": DASHBOARD}])
	ws.flags.ignore_permissions = True
	ws.save()
	# role-gate the team dashboard block so only HR/admin get it delivered on Home
	blk = frappe.get_doc("Custom HTML Block", DASHBOARD)
	blk.set("roles", [{"role": "HR Manager"}, {"role": "System Manager"}])
	blk.flags.ignore_permissions = True
	blk.save()


def _setup_dashboard():
	# HR/admin-only "Attendance Dashboard" workspace (worked hours, late/early, per day)
	content = [
		{"id": "dash_hdr", "type": "header",
		 "data": {"text": '<span class="h4"><b>Team Attendance</b></span>', "col": 12}},
		{"id": "dash_blk", "type": "custom_block", "data": {"custom_block_name": DASHBOARD, "col": 12}},
	]
	if frappe.db.exists("Workspace", DASHBOARD):
		frappe.delete_doc("Workspace", DASHBOARD, force=1, ignore_permissions=True)
	ws = frappe.get_doc({
		"doctype": "Workspace", "name": DASHBOARD, "title": DASHBOARD, "label": DASHBOARD,
		"public": 1, "is_standard": 0, "is_hidden": 0, "icon": "users", "sequence_id": 0.2,
		"content": json.dumps(content),
		"custom_blocks": [{"custom_block_name": DASHBOARD, "label": DASHBOARD}],
		"roles": [{"role": "HR Manager"}],   # only HR Manager + Workspace Manager (admin) see it
	})
	ws.flags.ignore_permissions = True
	ws.insert()
	frappe.db.commit()


def _apply_visibility():
	# same trimmed sidebar for every role (is_hidden hides for all, incl. admin)
	for w in frappe.get_all("Workspace", fields=["name", "public"]):
		if not w.public or w.name == DASHBOARD:
			continue
		frappe.db.set_value("Workspace", w.name, "is_hidden",
		                    0 if w.name in VISIBLE else 1, update_modified=False)
	# drop per-workspace role restrictions EXCEPT the HR-only dashboard's
	frappe.db.delete("Has Role", {"parenttype": "Workspace", "parent": ["!=", DASHBOARD]})
	frappe.db.commit()


def _remove_my_attendance():
	if frappe.db.exists("Workspace", "My Attendance"):
		frappe.delete_doc("Workspace", "My Attendance", force=1, ignore_permissions=True)
		frappe.db.commit()


def _lock_readonly_doctypes():
	"""Employee role = read-only on check-ins & attendance (created by the check-in
	flow, not by hand). Removing write/create/delete makes the form open read-only
	for employees; HR/admin keep full access. Stored as Custom DocPerm (persists)."""
	from frappe.permissions import update_permission_property
	for dt in ("Employee Checkin", "Attendance"):
		for ptype in ("write", "create", "delete", "amend"):
			try:
				update_permission_property(dt, "Employee", 0, ptype, 0, validate=False)
			except Exception:
				pass
	frappe.db.commit()


def _setup_regularization_perms():
	"""HR's warning note on a Regularization sits at permlevel 1: HR/admin write it,
	the employee can only read it (Frappe silently drops writes to a permlevel the
	user lacks)."""
	from frappe.permissions import add_permission, update_permission_property
	dt = "Attendance Request"
	for role in ("HR Manager", "HR User", "System Manager"):
		try:
			add_permission(dt, role, 1)
			update_permission_property(dt, role, 1, "read", 1, validate=False)
			update_permission_property(dt, role, 1, "write", 1, validate=False)
		except Exception:
			pass
	try:
		add_permission(dt, "Employee", 1)
		update_permission_property(dt, "Employee", 1, "read", 1, validate=False)
		update_permission_property(dt, "Employee", 1, "write", 0, validate=False)
	except Exception:
		pass
	frappe.db.commit()


def setup_desk():
	"""Idempotent; wired to after_install and after_migrate so a migrate that
	re-syncs the standard Home from ERPNext source can't undo our layout."""
	# don't export the standard Home back to ERPNext's source during our save
	orig_dev = frappe.conf.get("developer_mode")
	frappe.conf.developer_mode = 0
	try:
		_setup_home()
		_setup_dashboard()
		_apply_visibility()
		_remove_my_attendance()
		_lock_readonly_doctypes()
		_setup_regularization_perms()
	finally:
		frappe.conf.developer_mode = orig_dev
	frappe.db.commit()
