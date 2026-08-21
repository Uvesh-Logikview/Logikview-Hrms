"""Attendance nudges, absence marking and celebration notices.

Schedule (working days only - never on a weekend, company holiday, or a day the
person is on approved leave):

  10:45  "Your Shift has Started."   -> anyone not checked in
  15:00  mark Absent                 -> still no check-in
  19:15  "Your Shift has Ended."     -> anyone still checked in

  daily  birthday / work anniversary notice, sent the day before.
"""

import frappe
from frappe.utils import add_days, getdate, today


def _is_working_day(day=None):
	day = getdate(day or today())
	if day.weekday() >= 5:
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
	                      fields=["name", "employee_name", "user_id", "department",
	                              "date_of_birth", "date_of_joining",
	                              "custom_exempt_from_attendance"],
	                      limit_page_length=0)


def _has_checked_in(employee, day):
	return bool(frappe.db.exists("Employee Checkin", {
		"employee": employee, "log_type": "IN",
		"time": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]}))


def _still_checked_in(employee, day):
	rows = frappe.get_all("Employee Checkin",
	                      filters={"employee": employee,
	                               "time": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]},
	                      fields=["log_type"], order_by="time desc", limit=1)
	return bool(rows) and rows[0].log_type == "IN"


def _nudge(subject, message, want, key):
	"""Send to everyone matching `want(employee, day)`; once per person per day."""
	day = today()
	if not _is_working_day(day):
		return 0
	from logikview_hr.notify import notify

	sent = 0
	for e in _active_employees():
		if e.get("custom_exempt_from_attendance"):
			continue            # directors etc. don't follow shift timings
		if not e.user_id or _on_leave(e.name, day) or not want(e.name, day):
			continue
		notify([e.user_id], subject, message, "Employee", e.name, dedup_key=f"{key}-{day}")
		sent += 1
	return sent


# ---------------------------------------------------------------- morning
def _not_in(emp, day):
	return not _has_checked_in(emp, day)


def checkin_shift_started():                # 10:45
	return _nudge("Your Shift has Started",
	              "Your Shift has Started. Please check in on Logikview HR.",
	              _not_in, "in-1045")


# ---------------------------------------------------------------- evening
def _still_in(emp, day):
	return _still_checked_in(emp, day)


def checkout_shift_end():                   # 19:15
	return _nudge("Your Shift has Ended",
	              "Your Shift has Ended. Please check out on Logikview HR.",
	              _still_in, "out-1915")


# ---------------------------------------------------------------- absence
def mark_absent_no_checkin():
	"""15:00 - nobody has checked in by mid-afternoon, so mark the day Absent.
	A later check-out recomputes the day and puts it back to Present."""
	day = today()
	if not _is_working_day(day):
		return 0
	from logikview_hr.notify import notify

	marked = 0
	for e in _active_employees():
		if _on_leave(e.name, day) or _has_checked_in(e.name, day):
			continue
		if frappe.db.exists("Attendance", {"employee": e.name, "attendance_date": day,
		                                   "docstatus": ["!=", 2]}):
			continue
		exempt = bool(e.get("custom_exempt_from_attendance"))
		try:
			att = frappe.get_doc({
				"doctype": "Attendance", "employee": e.name, "attendance_date": day,
				"status": "Present" if exempt else "Absent", "working_hours": 0,
				"company": frappe.db.get_value("Employee", e.name, "company"),
			})
			att.flags.ignore_permissions = True
			att.flags.ignore_validate = True
			att.insert(ignore_permissions=True)
			frappe.db.set_value("Attendance", att.name, "docstatus", 1)
			marked += 1
			if exempt:
				continue        # recorded Present, nothing to tell them
			if e.user_id:
				notify([e.user_id], "You have been marked absent today",
				       "No check-in was recorded by 3:00 PM, so today has been marked "
				       "<b>Absent</b>. If this is wrong, please check in or raise a "
				       "regularization for HR to approve.",
				       "Employee", e.name, dedup_key=f"absent-{day}")
		except Exception:
			frappe.log_error(f"absent marking failed for {e.name} {day}", "Logikview Attendance")
	frappe.db.commit()
	return marked


# ---------------------------------------------------------------- celebrations
def celebration_reminders():
	"""Tell everyone the day before a birthday or work anniversary."""
	target = getdate(add_days(today(), 1))
	from logikview_hr.notify import notify

	people = _active_employees()
	recipients = [e.user_id for e in people if e.user_id]
	sent = 0
	for e in people:
		for kind, d in (("birthday", e.date_of_birth), ("anniversary", e.date_of_joining)):
			if not d:
				continue
			d = getdate(d)
			if (d.month, d.day) != (target.month, target.day):
				continue
			years = target.year - d.year
			if kind == "anniversary" and years <= 0:
				continue
			if kind == "birthday":
				subject = f"Tomorrow is {e.employee_name}'s birthday"
				msg = (f"<b>{e.employee_name}</b>"
				       + (f" ({e.department.replace(' - LA', '')})" if e.department else "")
				       + " celebrates their birthday tomorrow. Do wish them!")
			else:
				subject = f"{e.employee_name} completes {years} year(s) tomorrow"
				msg = (f"<b>{e.employee_name}</b> completes <b>{years} year(s)</b> at Logikview "
				       f"tomorrow. Do congratulate them!")
			notify([u for u in recipients if u != e.user_id], subject, msg,
			       "Employee", e.name, dedup_key=f"{kind}-{target}")
			sent += 1
	return sent


# ---------------------------------------------------------------- HR report
def _hr_users():
	users = frappe.get_all("Has Role", filters={"role": ["in", ["HR Manager", "HR User"]],
	                                            "parenttype": "User"}, pluck="parent")
	return [u for u in set(users) if u and u != "Administrator"
	        and frappe.db.get_value("User", u, "enabled")]


LATE_AFTER_MIN = 10 * 60 + 45


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
		if _on_leave(e.name, day) or e.get("custom_exempt_from_attendance"):
			continue
		rows = frappe.get_all("Employee Checkin",
		                      filters={"employee": e.name, "log_type": "IN",
		                               "time": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]},
		                      fields=["time"], order_by="time asc", limit=1)
		if not rows:
			absent.append(e)
			continue
		present += 1
		t = str(rows[0].time)
		mins = int(t[11:13]) * 60 + int(t[14:16])
		if mins > LATE_AFTER_MIN:
			by = mins - LATE_AFTER_MIN
			late.append((e, t[11:16], f"{by // 60} hr {by % 60} min" if by >= 60 else f"{by} min"))

	rows_html = "".join(
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
		f"{rows_html}</table>" if late else "<p>Nobody was late today.</p>")

	message = (
		f"<p><b>{len(late)}</b> employee(s) were late on "
		f"{getdate(day).strftime('%d %b %Y')} (after 10:45).</p>"
		f"<p style='color:#6b7885;font-size:12.5px;'>Checked in: {present} &nbsp;·&nbsp; "
		f"Late: {len(late)} &nbsp;·&nbsp; No check-in: {len(absent)}</p>{table}"
		+ (f"<p style='margin-top:12px;'><b>No check-in today:</b> "
		   f"{', '.join(frappe.utils.escape_html(e.employee_name) for e in absent)}</p>" if absent else ""))
	notify(hr, f"Late attendance report - {getdate(day).strftime('%d %b %Y')} ({len(late)} late)",
	       message, None, None)
	return len(late)
