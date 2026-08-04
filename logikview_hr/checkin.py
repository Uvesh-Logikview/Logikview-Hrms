"""Auto check-out for employees who forget to check out.

Rule (per Logikview): people may check out themselves any time. If they're still
checked in and have completed the full day (>= REQUIRED_HOURS of worked time), the
system checks them out automatically — but never before 19:15, so anyone who
extends past the 19:00 shift end still gets credited up to when they hit their
hours. A late-night safety sweep closes any session left open, capping the counted
time at REQUIRED_HOURS so a forgotten check-out can't run up the clock overnight.
"""

import frappe
from frappe.utils import today, now_datetime, get_datetime, add_to_date

REQUIRED_HOURS = 9
REQUIRED_SECONDS = REQUIRED_HOURS * 3600
AUTO_AFTER = (19, 15)      # don't auto-checkout before 19:15
FINAL_SWEEP = (23, 30)     # after this, close anything still open (capped)
DEVICE_TAG = "Auto Checkout"


def _worked(employee, day, upto):
    """Return (completed_seconds, last_in_time, first_in_time) for the day.
    completed_seconds counts only closed IN->OUT pairs (open segment excluded)."""
    logs = frappe.get_all("Employee Checkin",
                          filters={"employee": employee, "time": [">=", day]},
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


def auto_checkout():
    now = now_datetime()
    if (now.hour, now.minute) < AUTO_AFTER:
        return
    day = today()
    final_sweep = (now.hour, now.minute) >= FINAL_SWEEP

    employees = frappe.get_all("Employee Checkin", filters={"time": [">=", day]},
                               pluck="employee", group_by="employee")
    for emp in employees:
        completed, last_in, first_in = _worked(emp, day, now)
        if not last_in:
            continue  # already checked out
        open_secs = (now - last_in).total_seconds()
        total_now = completed + open_secs

        if total_now >= REQUIRED_SECONDS:
            out_time = now                                   # full credit for extenders
        elif final_sweep:
            # forgot to check out and under the day's hours: cap total at REQUIRED
            cap = max(0, REQUIRED_SECONDS - completed)
            out_time = add_to_date(last_in, seconds=cap)
            if get_datetime(out_time) > now:
                out_time = now
        else:
            continue  # still under hours, before the final sweep -> let them check out

        try:
            _checkout(emp, day, get_datetime(out_time), first_in)
        except Exception:
            frappe.log_error(f"auto_checkout failed for {emp}", "Logikview Auto Checkout")


def _checkout(employee, day, out_time, first_in):
    settings = frappe.get_cached_doc("Logikview Checkin Settings")
    lat = settings.latitude
    lon = settings.longitude
    geojson = ('{"type": "FeatureCollection", "features": [{"type": "Feature", '
               '"properties": {}, "geometry": {"type": "Point", "coordinates": ['
               + str(lon) + ', ' + str(lat) + ']}}]}')

    shift = frappe.db.get_value("Shift Assignment",
                                {"employee": employee, "status": "Active",
                                 "start_date": ["<=", day], "end_date": [">=", day]}, "shift_type")
    if not shift:
        shift = frappe.db.get_value("Shift Assignment",
                                    {"employee": employee, "status": "Active",
                                     "start_date": ["<=", day], "end_date": ["in", ["", None]]}, "shift_type")

    checkin = frappe.get_doc({
        "doctype": "Employee Checkin", "employee": employee, "log_type": "OUT",
        "time": out_time, "device_id": DEVICE_TAG,
        "latitude": lat, "longitude": lon, "geolocation": geojson, "shift": shift,
    })
    checkin.flags.ignore_permissions = True
    checkin.insert(ignore_permissions=True)

    # ---- finalize attendance (same rules as the manual check-out) ----
    logs = frappe.get_all("Employee Checkin", filters={"employee": employee, "time": [">=", day]},
                          fields=["log_type", "time"], order_by="time asc")
    total_seconds, last_in = 0, None
    for l in logs:
        t = get_datetime(l.time)
        if l.log_type == "IN":
            last_in = t
        elif l.log_type == "OUT" and last_in:
            total_seconds += (t - last_in).total_seconds()
            last_in = None
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
        if shift_doc.end_time:
            shift_end = get_datetime(day + " " + str(shift_doc.end_time))
            grace = shift_doc.early_exit_grace_period or 0
            if out_time < add_to_date(shift_end, minutes=-grace):
                early_exit = 1

    status = "Half Day" if (half_day_threshold and working_hours < half_day_threshold) else "Present"
    existing = frappe.db.get_value("Attendance",
                                   {"employee": employee, "attendance_date": day, "docstatus": ["!=", 2]}, "name")
    if existing:
        frappe.db.set_value("Attendance", existing,
                            {"working_hours": working_hours, "status": status,
                             "late_entry": late_entry, "early_exit": early_exit})
    else:
        att = frappe.get_doc({
            "doctype": "Attendance", "employee": employee, "attendance_date": day,
            "status": status, "working_hours": working_hours, "shift": shift,
            "company": frappe.db.get_value("Employee", employee, "company"),
            "late_entry": late_entry, "early_exit": early_exit,
        })
        att.flags.ignore_permissions = True
        att.flags.ignore_validate = True
        att.insert(ignore_permissions=True)
        frappe.db.set_value("Attendance", att.name, "docstatus", 1)
    frappe.db.commit()
