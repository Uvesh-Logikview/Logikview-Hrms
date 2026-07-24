import json

import frappe

# Replicates the hrsystem/snaphire desk: the check-in card + Employee Details
# shortcuts on the standard Home workspace, and the same trimmed sidebar
# (is_hidden on non-HR workspaces) shown to every role.

CARD = "Checkin button functionality"

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
	ws.set("custom_blocks", [{"custom_block_name": CARD, "label": CARD}])
	ws.flags.ignore_permissions = True
	ws.save()


def _apply_visibility():
	# same trimmed sidebar for every role (is_hidden hides for all, incl. admin)
	for w in frappe.get_all("Workspace", fields=["name", "public"]):
		if not w.public:
			continue
		frappe.db.set_value("Workspace", w.name, "is_hidden",
		                    0 if w.name in VISIBLE else 1, update_modified=False)
	# drop any per-workspace role restriction (we don't gate by role — hrsystem doesn't)
	frappe.db.delete("Has Role", {"parenttype": "Workspace"})
	frappe.db.commit()


def _remove_my_attendance():
	if frappe.db.exists("Workspace", "My Attendance"):
		frappe.delete_doc("Workspace", "My Attendance", force=1, ignore_permissions=True)
		frappe.db.commit()


def setup_desk():
	"""Idempotent; wired to after_install and after_migrate so a migrate that
	re-syncs the standard Home from ERPNext source can't undo our layout."""
	# don't export the standard Home back to ERPNext's source during our save
	orig_dev = frappe.conf.get("developer_mode")
	frappe.conf.developer_mode = 0
	try:
		_setup_home()
		_apply_visibility()
		_remove_my_attendance()
	finally:
		frappe.conf.developer_mode = orig_dev
	frappe.db.commit()
