"""Work-anniversary appraisal cycle.

Flow: 7 days before an employee's work anniversary an appraisal is auto-created
and the employee + HR are notified. The employee fills the self-assessment, it
routes to the reporting officer (team lead / manager) for the RO ratings, then
to the director(s):
  * Director Two's team  -> Director Two reviews, done.
  * Director One's team   -> Director One reviews, then Director Two (final), done.
Directors only add a feedback comment (no scoring).

Reminders (in-app, no SMTP on this bench):
  * whoever's turn it is and hasn't acted -> every Monday
  * appraisal pending > `overdue_months` -> daily, to employee + RO + directors + HR
"""

import frappe
from frappe.utils import getdate, today, add_days, add_months, nowdate

CAT_INDIVIDUAL = "Individual"
CAT_DOMAIN = "In your domain"
CAT_TEAM = "As a team member / leader"

INDIVIDUAL = ["Sincerity", "Readiness to take work", "Adherence to timelines",
              "Punctuality", "Initiative", "Reliability"]
TECH_DOMAIN = ["Software Development skills", "Problem solving skills", "Domain knowledge",
               "Best practices coding", "Documentation", "Learning new tech skills"]
GENERAL_DOMAIN = ["Quality of work", "Job knowledge", "Productivity & efficiency",
                  "Accuracy & attention to detail", "Process adherence", "Learning & development"]
TEAM = ["Communication", "Helping others achieve their goals", "Coordination with others",
        "Communication skills", "Client interaction", "Interpersonal skills"]

STATE_ACTOR = {
    "Pending Self-Assessment": "employee",
    "Pending Manager Review": "reporting_officer",
    "Pending Director Review": "first_director",
    "Pending Final Director": "second_director",
}


# ---------------------------------------------------------------- helpers
def _settings():
    return frappe.get_cached_doc("Logikview Appraisal Settings")


def _general_departments(s):
    return {d.strip() for d in (s.general_departments or "").splitlines() if d.strip()}


def _top_director(emp, d_one, d_two):
    """Walk reports_to to the root; return (first_director, needs_second, second_director)."""
    seen = set()
    cur = emp
    root = None
    while cur and cur not in seen:
        seen.add(cur)
        parent = frappe.db.get_value("Employee", cur, "reports_to")
        if not parent:
            root = cur
            break
        cur = parent
    if root == d_one:                       # Director One's team -> two-step
        return d_one, 1, d_two
    if root == d_two:                       # Director Two's team -> single
        return d_two, 0, None
    return d_two, 0, None                   # fallback: route to Director Two


def _rating_rows(assessment_type):
    domain = GENERAL_DOMAIN if assessment_type == "General" else TECH_DOMAIN
    rows = []
    for p in INDIVIDUAL:
        rows.append({"category": CAT_INDIVIDUAL, "parameter": p})
    for p in domain:
        rows.append({"category": CAT_DOMAIN, "parameter": p})
    for p in TEAM:
        rows.append({"category": CAT_TEAM, "parameter": p})
    return rows


def _user_of(emp):
    return frappe.db.get_value("Employee", emp, "user_id") if emp else None


def _hr_users():
    users = frappe.get_all("Has Role", filters={"role": ["in", ["HR Manager", "HR User"]],
                                                 "parenttype": "User"}, pluck="parent")
    return [u for u in set(users) if u and u not in ("Administrator",)
            and frappe.db.get_value("User", u, "enabled")]


def _notify(users, subject, message, appraisal_name, dedup_key):
    """In-app bell notification, de-duplicated per (user, appraisal, dedup_key)."""
    for user in {u for u in users if u}:
        marker = f"{appraisal_name}|{dedup_key}"
        if frappe.db.exists("Notification Log",
                            {"for_user": user, "document_name": appraisal_name,
                             "subject": ["like", f"%{marker}%"]}):
            continue
        frappe.get_doc({
            "doctype": "Notification Log", "for_user": user, "type": "Alert",
            "document_type": "Logikview Appraisal", "document_name": appraisal_name,
            "subject": subject + f"<!--{marker}-->",
            "email_content": message,
        }).insert(ignore_permissions=True)


# ---------------------------------------------------------------- creation
def create_appraisal(employee, anniversary_date, years):
    s = _settings()
    d_one, d_two = s.director_one, s.director_two
    emp = frappe.db.get_value("Employee", employee,
                              ["department", "reports_to", "employee_name"], as_dict=True)
    if not emp:
        return None
    # directors themselves are not appraised through this cycle
    if employee in (d_one, d_two) or not emp.reports_to:
        return None

    assessment_type = "General" if emp.department in _general_departments(s) else "Technical"
    first_director, needs_second, second_director = _top_director(employee, d_one, d_two)

    doc = frappe.get_doc({
        "doctype": "Logikview Appraisal",
        "employee": employee,
        "anniversary_date": anniversary_date,
        "years_completed": years,
        "assessment_type": assessment_type,
        "reporting_officer": emp.reports_to,
        "first_director": first_director,
        "needs_second_director": needs_second,
        "second_director": second_director,
        "workflow_state": "Pending Self-Assessment",
        "ratings": _rating_rows(assessment_type),
    })
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    subject = f"Appraisal due: please complete your self-assessment ({years}-yr work anniversary)"
    msg = (f"Your {years}-year work anniversary is on {getdate(anniversary_date).strftime('%d %b %Y')}. "
           f"Please open your appraisal ({doc.name}) and complete the self-assessment. "
           f"It then goes to your reporting officer and the director(s) for review.")
    hr = _hr_users()
    _notify([_user_of(employee)], subject, msg, doc.name, "created-emp")
    _notify(hr, f"Appraisal started for {emp.employee_name} ({years} yrs)",
            f"An appraisal ({doc.name}) was auto-created for {emp.employee_name}.", doc.name, "created-hr")
    return doc.name


def _is_anniversary(doj, target):
    doj, target = getdate(doj), getdate(target)
    if (doj.month, doj.day) == (target.month, target.day):
        return True
    # Feb-29 hires: mark the anniversary on Feb-28 in non-leap years
    if doj.month == 2 and doj.day == 29 and target.month == 2 and target.day == 28:
        import calendar
        return not calendar.isleap(target.year)
    return False


def create_due_appraisals():
    """Daily: 7 days before each active employee's work anniversary."""
    s = _settings()
    days = int(s.notify_days_before or 7)
    target = getdate(add_days(today(), days))
    for emp in frappe.get_all("Employee", filters={"status": "Active"},
                              fields=["name", "date_of_joining"]):
        if not emp.date_of_joining or not _is_anniversary(emp.date_of_joining, target):
            continue
        years = target.year - getdate(emp.date_of_joining).year
        if years <= 0:
            continue
        if frappe.db.exists("Logikview Appraisal",
                            {"employee": emp.name, "anniversary_date": target}):
            continue
        try:
            create_appraisal(emp.name, target, years)
        except Exception:
            frappe.log_error(f"create_appraisal failed for {emp.name}", "Logikview Appraisal")


# ---------------------------------------------------------------- reminders
def send_appraisal_reminders():
    """Daily: Monday nudge to the current actor + daily nudge for >N-month overdue."""
    s = _settings()
    overdue_months = int(s.overdue_months or 4)
    is_monday = getdate(today()).weekday() == 0
    hr = _hr_users()
    day = nowdate()

    for ap in frappe.get_all("Logikview Appraisal",
                             filters={"workflow_state": ["!=", "Completed"]},
                             fields=["name", "employee", "employee_name", "reporting_officer",
                                     "first_director", "second_director", "workflow_state",
                                     "anniversary_date"]):
        actor_field = STATE_ACTOR.get(ap.workflow_state)
        actor_emp = ap.get(actor_field) if actor_field else None
        actor_user = _user_of(actor_emp)

        overdue = ap.anniversary_date and getdate(add_months(ap.anniversary_date, overdue_months)) <= getdate(today())

        if overdue:
            # daily, to everyone involved
            recipients = [_user_of(ap.employee), _user_of(ap.reporting_officer),
                          _user_of(ap.first_director), _user_of(ap.second_director)] + hr
            subj = f"OVERDUE appraisal: {ap.employee_name} ({ap.workflow_state})"
            msg = (f"The appraisal {ap.name} for {ap.employee_name} has been pending for over "
                   f"{overdue_months} months (stage: {ap.workflow_state}). Please act on it today.")
            _notify(recipients, subj, msg, ap.name, f"overdue-{day}")
        elif is_monday and actor_user:
            subj = f"Reminder: appraisal awaiting you — {ap.employee_name}"
            msg = (f"The appraisal {ap.name} for {ap.employee_name} is at '{ap.workflow_state}' "
                   f"and awaiting your action. Please complete it.")
            _notify([actor_user], subj, msg, ap.name, f"monday-{day}")
