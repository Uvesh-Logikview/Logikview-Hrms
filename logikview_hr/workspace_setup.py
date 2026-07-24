import frappe

# Keep these workspaces visible to everyone (employees included).
KEEP_MODULES = {"HR", "Payroll", "Logikview HR"}
KEEP_NAMES = {"My Attendance"}

# Non-HR workspaces stay visible in the desk but only for this role, so
# admins keep a full dashboard while regular employees see HR only.
ADMIN_ROLE = "System Manager"


def hide_non_hr_workspaces():
	"""Restrict non-HR/Payroll workspaces to System Manager (role-based), not is_hidden.

	is_hidden removes a workspace from the sidebar for EVERYONE (even admins), so we
	instead unhide the non-HR workspaces and gate them behind the System Manager role.
	Admins keep the whole ERPNext desk; employees see only HR/Payroll + ours.

	Idempotent; wired to after_install and after_migrate. Only touches public
	workspaces and only saves when something actually changes.
	"""
	for w in frappe.get_all("Workspace", fields=["name", "module", "public", "is_hidden"]):
		if not w.public:
			continue
		keep = (w.name in KEEP_NAMES) or (w.module in KEEP_MODULES)
		ws = frappe.get_doc("Workspace", w.name)
		changed = False

		# never rely on is_hidden for this cleanup
		if ws.is_hidden:
			ws.is_hidden = 0
			changed = True

		if keep:
			# leave HR workspaces exactly as the apps shipped them (visible to all)
			pass
		else:
			current = sorted(d.role for d in ws.get("roles", []))
			if current != [ADMIN_ROLE]:
				ws.set("roles", [{"role": ADMIN_ROLE}])
				changed = True

		if changed:
			ws.flags.ignore_permissions = True
			ws.save()

	frappe.db.commit()
