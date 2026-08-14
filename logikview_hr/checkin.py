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


def classify_location(latitude, longitude):
	"""Office vs Work From Home, using the same radius rule as a manual check-in."""
	s = frappe.get_cached_doc("Logikview Checkin Settings")
	distance_km = (((float(latitude) - float(s.latitude)) ** 2
	                + (float(longitude) - float(s.longitude)) ** 2) ** 0.5) * 111
	return "Office" if distance_km <= float(s.radius_km) else "Work From Home"


@frappe.whitelist()
def ping_location(latitude, longitude, accuracy=None):
	"""Called periodically by the check-in card while the person is checked in, so
	an auto check-out can be tagged with where they actually were - the job runs
	on the server hours later, when there is no browser left to ask for GPS."""
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee or not latitude or not longitude:
		return {}

	location = classify_location(latitude, longitude)
	frappe.db.set_value("Employee", employee, {
		"custom_last_seen_location": location,
		"custom_last_seen_latitude": float(latitude),
		"custom_last_seen_longitude": float(longitude),
		"custom_last_seen_at": now_datetime(),
	}, update_modified=False)
	frappe.db.commit()
	return {"location": location}


def _last_known_location(employee, day):
	"""Where the person was most recently seen today (GPS ping), else where they
	checked in from. Returns (location, lat, lon, geojson) or None."""
	emp = frappe.db.get_value("Employee", employee,
	                          ["custom_last_seen_location", "custom_last_seen_latitude",
	                           "custom_last_seen_longitude", "custom_last_seen_at"], as_dict=True)
	if emp and emp.custom_last_seen_at and emp.custom_last_seen_location:
		if str(emp.custom_last_seen_at)[:10] == day:      # only trust today's ping
			lat, lon = emp.custom_last_seen_latitude, emp.custom_last_seen_longitude
			geojson = ('{"type": "FeatureCollection", "features": [{"type": "Feature", '
			           '"properties": {}, "geometry": {"type": "Point", "coordinates": ['
			           + str(lon) + ', ' + str(lat) + ']}}]}')
			return emp.custom_last_seen_location, lat, lon, geojson

	last_in = frappe.db.sql("""
		select device_id, latitude, longitude, geolocation
		from `tabEmployee Checkin`
		where employee = %s and log_type = 'IN' and time between %s and %s
		order by time desc limit 1""",
		(employee, day + " 00:00:00", day + " 23:59:59"), as_dict=True)
	if last_in:
		return (last_in[0].device_id or "Office", last_in[0].latitude,
		        last_in[0].longitude, last_in[0].geolocation)
	return None


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


def close_stale_sessions(days_back=30):
    """Close sessions left open on PAST days (the daily sweep only handles today,
    so a day the job didn't run would otherwise stay open forever). Counted time
    is capped at REQUIRED_HOURS."""
    day = today()
    rows = frappe.db.sql("""
        select employee, date(time) d
        from `tabEmployee Checkin`
        where time >= date_sub(%s, interval %s day) and date(time) < %s
        group by employee, date(time)""", (day, days_back, day), as_dict=True)
    for r in rows:
        past_day = str(r.d)
        completed, last_in, first_in = _worked(r.employee, past_day, None)
        if not last_in:
            continue
        cap = max(0, REQUIRED_SECONDS - completed)
        out_time = get_datetime(add_to_date(last_in, seconds=cap))
        # never let the auto check-out cross midnight into the next day
        end_of_day = get_datetime(past_day + " 23:59:00")
        if out_time > end_of_day:
            out_time = end_of_day
        try:
            _checkout(r.employee, past_day, out_time, first_in)
        except Exception:
            frappe.log_error(f"close_stale_sessions failed for {r.employee} {past_day}",
                             "Logikview Auto Checkout")


def backfill_attendance(days_back=30):
    """Create/refresh Attendance for past days that have check-ins but no
    Attendance record (e.g. a day closed by an out-of-band OUT), so worked hours
    are never left missing or at 0."""
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
            continue  # still open (the sweep handles it) or nothing worked
        try:
            _write_attendance(r.employee, past_day, completed, first_in,
                              get_datetime(past_day + " 00:00:00"))
            made += 1
        except Exception:
            frappe.log_error(f"backfill_attendance failed for {r.employee} {past_day}",
                             "Logikview Auto Checkout")
    return made


def auto_checkout():
    now = now_datetime()
    if (now.hour, now.minute) < AUTO_AFTER:
        return
    day = today()
    final_sweep = (now.hour, now.minute) >= FINAL_SWEEP
    if final_sweep:
        close_stale_sessions()
        backfill_attendance()

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
    # Tag the auto check-out with where the person actually was: the most recent
    # GPS ping sent by their check-in card today, falling back to where they
    # checked in from. custom_auto_checkout is what marks it system-generated.
    settings = frappe.get_cached_doc("Logikview Checkin Settings")
    known = _last_known_location(employee, day)
    if known:
        location, lat, lon, geojson = known
        lat = lat or settings.latitude
        lon = lon or settings.longitude
    else:
        location, lat, lon, geojson = "Office", settings.latitude, settings.longitude, None
    if not geojson:
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
        "time": out_time, "device_id": location,
        "custom_auto_checkout": 1,
        "latitude": lat, "longitude": lon, "geolocation": geojson, "shift": shift,
    })
    checkin.flags.ignore_permissions = True
    checkin.insert(ignore_permissions=True)

    # ---- finalize attendance (same rules as the manual check-out) ----
    total_seconds, _open, _first = _worked(employee, day, None)
    _write_attendance(employee, day, total_seconds, first_in, out_time, shift)


def _write_attendance(employee, day, total_seconds, first_in, out_time, shift=None):
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
