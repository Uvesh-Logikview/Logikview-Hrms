import frappe

# Keep only HR/Payroll workspaces (and our own); hide the rest of the ERPNext desk.
KEEP_MODULES = {"HR", "Payroll", "Logikview HR"}
KEEP_NAMES = {"My Attendance"}


def hide_non_hr_workspaces():
	"""Hide every public workspace that isn't HR/Payroll or ours.

	Idempotent. Wired to after_install and after_migrate so that a migrate
	re-syncing a standard workspace can't un-hide it. Uses db.set_value so it
	never exports workspace changes back to app source (even in developer_mode).
	"""
	for w in frappe.get_all("Workspace", fields=["name", "module"]):
		keep = (w.name in KEEP_NAMES) or (w.module in KEEP_MODULES)
		frappe.db.set_value("Workspace", w.name, "is_hidden", 0 if keep else 1, update_modified=False)
	frappe.db.commit()
