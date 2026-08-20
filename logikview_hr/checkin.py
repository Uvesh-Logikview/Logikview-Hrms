"""Attendance hours for days the employee did not close themselves.

Checking out is manual - the system never creates a check-out record. If someone
has not checked out by the evening, we only write the day's worked hours to
Attendance (counted to the 19:15 cut-off and capped at a full day) so the day is
never left at 0, and the session stays open. When they do check out, the check-in
script recomputes the real hours and clears the auto-filled flag.
"""

import frappe
from frappe.utils import today, now_datetime, get_datetime, add_to_date

REQUIRED_HOURS = 9                 # cap when filling in a forgotten check-out
REQUIRED_SECONDS = REQUIRED_HOURS * 3600
FULL_DAY_HOURS = 8                 # per HR policy: 8 working hours a day
AUTO_AFTER = (19, 15)      # don't fill hours before this (people extend past 19:00)
FINAL_SWEEP = (23, 30)     # last run of the night
CUTOFF_TIME = "19:15:00"   # hours for a day with no check-out are counted to here


def _worked(employee, day, upto):
    """Return (completed_seconds, last_in_time, first_in_time) for the day.
    completed_seconds counts only closed IN->OUT pairs (open segment excluded)."""
    # bound to THIS day only - an open-ended ">= day" pulls in later days' logs,
    # which mixes sessions together (wrong hours, and last_in ends up None so the
    # open session is never closed)
    logs = frappe.get_all("Employee Checkin",
                          filters={"employee": employee,
                                   "time": ["between", [day + " 00:00:00", day + " 23:59:59"]]},
                          fields=["log_type", "time"], order_by="time asc")
    total, last_in, first_in = 0, None, None
    for l in logs:
        t = get_datetime(l.time)
        if l.log_type == "IN":
            if first_in is None:
                first_in = t
            last_in = t
        elif l.log_type == "OUT" and last_in:
            total += (t - last_in).total_seconds()
            last_in = None
    return total, last_in, first_in


def fill_open_day_hours(days_back=30):
    """Days where the person never checked out: record the hours so attendance is
    not left at 0, but leave the session OPEN and create no check-out record - only
    the employee closes their own day. If they do check out later, the check-in
    script recomputes the real hours and clears the auto-filled flag."""
    day = today()
    rows = frappe.db.sql("""
        select employee, date(time) d
        from `tabEmployee Checkin`
        where time >= date_sub(%s, interval %s day) and date(time) <= %s
        group by employee, date(time)""", (day, days_back, day), as_dict=True)
    filled = 0
    for r in rows:
        past_day = str(r.d)
        completed, last_in, first_in = _worked(r.employee, past_day, None)
        if not last_in:
            continue                       # properly checked out - nothing to do
        if past_day == day and (now_datetime().hour, now_datetime().minute) < AUTO_AFTER:
            continue                       # today, too early - let them check out
        # same figure the auto check-out used to produce: worked time up to the
        # cut-off, capped at a full day so a forgotten check-out can't inflate it
        cutoff = min(get_datetime(past_day + " " + CUTOFF_TIME), now_datetime()) \
            if past_day == day else get_datetime(past_day + " " + CUTOFF_TIME)
        open_secs = max(0, (cutoff - last_in).total_seconds())
        total = min(completed + open_secs, REQUIRED_SECONDS)
        if total <= 0:
            continue
        try:
            _write_attendance(r.employee, past_day, total, first_in,
                              get_datetime(past_day + " " + CUTOFF_TIME), auto_filled=1)
            filled += 1
        except Exception:
            frappe.log_error(f"fill_open_day_hours failed for {r.employee} {past_day}",
                             "Logikview Attendance Fill")
    return filled


def backfill_attendance(days_back=30):
    """Create/refresh Attendance for past days that have check-ins, are already
    closed, but have no Attendance record - so worked hours are never missing."""
    day = today()
    rows = frappe.db.sql("""
        select employee, date(time) d
        from `tabEmployee Checkin`
        where time >= date_sub(%s, interval %s day) and date(time) < %s
        group by employee, date(time)""", (day, days_back, day), as_dict=True)
    made = 0
    for r in rows:
        past_day = str(r.d)
        if frappe.db.exists("Attendance", {"employee": r.employee, "attendance_date": past_day,
                                           "docstatus": ["!=", 2]}):
            continue
        completed, last_in, first_in = _worked(r.employee, past_day, None)
        if last_in or not completed:
            continue  # still open (fill_open_day_hours handles it) or nothing worked
        try:
            _write_attendance(r.employee, past_day, completed, first_in,
                              get_datetime(past_day + " 00:00:00"))
            made += 1
        except Exception:
            frappe.log_error(f"backfill_attendance failed for {r.employee} {past_day}",
                             "Logikview Attendance Fill")
    return made


def auto_checkout():
    """Evening job. Despite the name it no longer checks anybody out - it only
    fills in the hours for people who haven't checked out yet."""
    now = now_datetime()
    if (now.hour, now.minute) < AUTO_AFTER:
        return
    fill_open_day_hours()
    if (now.hour, now.minute) >= FINAL_SWEEP:
        backfill_attendance()


def _write_attendance(employee, day, total_seconds, first_in, out_time, shift=None,
                      auto_filled=0):
    """Create or refresh the day's Attendance from the worked seconds."""
    if shift is None:
        shift = frappe.db.get_value("Shift Assignment",
                                    {"employee": employee, "status": "Active",
                                     "start_date": ["<=", day], "end_date": [">=", day]}, "shift_type")
        if not shift:
            shift = frappe.db.get_value("Shift Assignment",
                                        {"employee": employee, "status": "Active",
                                         "start_date": ["<=", day], "end_date": ["in", ["", None]]}, "shift_type")
    working_hours = round(total_seconds / 3600, 4)

    late_entry, early_exit, half_day_threshold = 0, 0, 0
    if shift:
        shift_doc = frappe.get_doc("Shift Type", shift)
        half_day_threshold = shift_doc.working_hours_threshold_for_half_day or 0
        if shift_doc.start_time and first_in:
            shift_start = get_datetime(day + " " + str(shift_doc.start_time))
            grace = shift_doc.late_entry_grace_period or 0
            if first_in > add_to_date(shift_start, minutes=grace):
                late_entry = 1
        # NB: early exit is judged on hours actually worked, not on the clock -
        # leaving at 18:00 after a full day is not an early exit, while leaving at
        # 19:10 having arrived at 15:00 is.
        pass

    status = "Half Day" if (half_day_threshold and working_hours < half_day_threshold) else "Present"
    if status == "Present" and working_hours < FULL_DAY_HOURS:
        early_exit = 1
    existing = frappe.db.get_value("Attendance",
                                   {"employee": employee, "attendance_date": day, "docstatus": ["!=", 2]}, "name")
    if existing:
        frappe.db.set_value("Attendance", existing,
                            {"working_hours": working_hours, "status": status,
                             "late_entry": late_entry, "early_exit": early_exit,
                             "custom_hours_auto_filled": auto_filled})
    else:
        att = frappe.get_doc({
            "doctype": "Attendance", "employee": employee, "attendance_date": day,
            "status": status, "working_hours": working_hours, "shift": shift,
            "company": frappe.db.get_value("Employee", employee, "company"),
            "late_entry": late_entry, "early_exit": early_exit,
            "custom_hours_auto_filled": auto_filled,
        })
        att.flags.ignore_permissions = True
        att.flags.ignore_validate = True
        att.insert(ignore_permissions=True)
        frappe.db.set_value("Attendance", att.name, "docstatus", 1)
    frappe.db.commit()
