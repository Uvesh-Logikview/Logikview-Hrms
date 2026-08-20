"""Check-in / check-out reminders and the end-of-day late report.

Both were deferred while the site had no outgoing mail account; now that email
works they run on the scheduler.

  * morning  - nudge anyone who hasn't checked in by the late boundary
  * evening  - nudge anyone still checked in, so the day isn't left open
  * end of day - summary to HR: how many were late, who, and by how much

Nobody is chased on a weekend, a holiday, or a day they are on approved leave.
"""

import frappe
from frappe.utils import getdate, now_datetime, today

LATE_AFTER_MIN = 10 * 60 + 45          # 10:45, matches the shift grace period


def _is_working_day(day=None):
	day = getdate(day or today())
	if day.weekday() >= 5:                                    # Sat / Sun
		return False
	hl = frappe.db.get_value("Company", {}, "default_holiday_list")
	if hl and frappe.db.exists("Holiday", {"parent": hl, "holiday_date": day}):
		return False
	return True


def _on_leave(employee, day):
	return bool(frappe.db.exists("Leave Application", {
		"employee": employee, "docstatus": 1, "status": "Approved",
		"from_date": ["<=", day], "to_date": [">=", day],
	}))


def _active_employees():
	return frappe.get_all("Employee", filters={"status": "Active"},
	                      fields=["name", "employee_name", "user_id", "department"],
	                      limit_page_length=0)


def _first_in(employee, day):
	rows = frappe.get_all("Employee Checkin",
	                      filters={"employee": employee, "log_type": "IN",
	                               "time": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]},
	                      fields=["time"], order_by="time asc", limit=1)
	return rows[0].time if rows else None


def _still_checked_in(employee, day):
	rows = frappe.get_all("Employee Checkin",
	                      filters={"employee": employee,
	                               "time": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]},
	                      fields=["log_type"], order_by="time desc", limit=1)
	return bool(rows) and rows[0].log_type == "IN"


def morning_checkin_reminder():
	"""Anyone with no check-in once the late boundary has passed."""
	day = today()
	if not _is_working_day(day):
		return 0
	from logikview_hr.notify import notify

	sent = 0
	for e in _active_employees():
		if not e.user_id or _on_leave(e.name, day) or _first_in(e.name, day):
			continue
		notify([e.user_id], "Reminder: you haven't checked in today",
		       "You have not checked in yet today. Please open Logikview HR and check in, "
		       "or raise a regularization if you are working from elsewhere.",
		       "Employee", e.name, dedup_key=f"checkin-{day}")
		sent += 1
	return sent


def evening_checkout_reminder():
	"""Anyone still checked in at the end of the day."""
	day = today()
	if not _is_working_day(day):
		return 0
	from logikview_hr.notify import notify

	sent = 0
	for e in _active_employees():
		if not e.user_id or not _still_checked_in(e.name, day):
			continue
		notify([e.user_id], "Reminder: please check out",
		       "You are still checked in. Please check out so today's working hours are "
		       "recorded correctly. If you forget, the system fills in your hours but the "
		       "session stays open.",
		       "Employee", e.name, dedup_key=f"checkout-{day}")
		sent += 1
	return sent


def _hr_users():
	users = frappe.get_all("Has Role", filters={"role": ["in", ["HR Manager", "HR User"]],
	                                            "parenttype": "User"}, pluck="parent")
	return [u for u in set(users) if u and u != "Administrator"
	        and frappe.db.get_value("User", u, "enabled")]


def late_attendance_report():
	"""End-of-day summary to HR: how many were late, who, and who never came in."""
	day = today()
	if not _is_working_day(day):
		return
	hr = _hr_users()
	if not hr:
		return
	from logikview_hr.notify import notify

	late, absent, present = [], [], 0
	for e in _active_employees():
		if _on_leave(e.name, day):
			continue
		first = _first_in(e.name, day)
		if not first:
			absent.append(e)
			continue
		present += 1
		t = str(first)
		mins = int(t[11:13]) * 60 + int(t[14:16])
		if mins > LATE_AFTER_MIN:
			by = mins - LATE_AFTER_MIN
			late.append((e, t[11:16], f"{by // 60} hr {by % 60} min" if by >= 60 else f"{by} min"))

	rows = "".join(
		f"<tr><td style='padding:5px 10px;border-bottom:1px solid #eee;'>{frappe.utils.escape_html(e.employee_name)}</td>"
		f"<td style='padding:5px 10px;border-bottom:1px solid #eee;'>{(e.department or '').replace(' - LA','')}</td>"
		f"<td style='padding:5px 10px;border-bottom:1px solid #eee;'>{at}</td>"
		f"<td style='padding:5px 10px;border-bottom:1px solid #eee;color:#c0392b;'>{by}</td></tr>"
		for e, at, by in late)
	table = (
		"<table style='border-collapse:collapse;font-size:13px;margin-top:10px;'>"
		"<tr><th style='text-align:left;padding:5px 10px;border-bottom:2px solid #ddd;'>Employee</th>"
		"<th style='text-align:left;padding:5px 10px;border-bottom:2px solid #ddd;'>Department</th>"
		"<th style='text-align:left;padding:5px 10px;border-bottom:2px solid #ddd;'>Checked in</th>"
		"<th style='text-align:left;padding:5px 10px;border-bottom:2px solid #ddd;'>Late by</th></tr>"
		f"{rows}</table>" if late else "<p>Nobody was late today.</p>")

	message = (
		f"<p><b>{len(late)}</b> employee(s) were late on "
		f"{getdate(day).strftime('%d %b %Y')} (after 10:45).</p>"
		f"<p style='color:#6b7885;font-size:12.5px;'>Checked in: {present} &nbsp;·&nbsp; "
		f"Late: {len(late)} &nbsp;·&nbsp; No check-in: {len(absent)}</p>"
		f"{table}"
		+ (f"<p style='margin-top:12px;'><b>No check-in today:</b> "
		   f"{', '.join(frappe.utils.escape_html(e.employee_name) for e in absent)}</p>" if absent else "")
	)
	notify(hr, f"Late attendance report - {getdate(day).strftime('%d %b %Y')} ({len(late)} late)",
	       message, None, None, dedup_key=None)
	return len(late)
