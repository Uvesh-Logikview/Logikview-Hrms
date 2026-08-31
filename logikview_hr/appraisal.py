"""Work-anniversary appraisal cycle.

Flow: 7 days before an employee's work anniversary an appraisal is auto-created
and the employee + HR are notified. The employee fills the self-assessment, it
routes to the reporting officer (team lead / manager) for the RO ratings, then
to the director(s):
  * Director Two's team  -> Director Two reviews, done.
  * Director One's team   -> Director One reviews, then Director Two (final), done.
Directors only add a feedback comment (no scoring).

Reminders (in-app bell + email, see logikview_hr.notify):
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
    """Return (first_director, needs_second, second_director).

    Every appraisal is now seen by BOTH directors, whichever team the employee
    sits in - it used to be two-step only for Director One's team and a single
    signature for Director Two's, which meant half the company was reviewed by
    one director and half by two. The director in the employee's own reporting
    line reviews first, so the person closest to the work comments before it is
    closed out by the other.
    """
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

    # only one director configured - nothing to hand over to
    if not d_one or not d_two or d_one == d_two:
        return (d_one or d_two), 0, None

    if root == d_two:                       # their own director reviews first
        return d_two, 1, d_one
    return d_one, 1, d_two


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
    """In-app + email (see logikview_hr.notify)."""
    from logikview_hr.notify import notify
    notify(users, subject, message, "Logikview Appraisal", appraisal_name, dedup_key)


# ---------------------------------------------------------------- routing
@frappe.whitelist()
def resolve_defaults(employee):
    """Everything that depends on who the employee is: which form they get and
    who reviews it. Shared by the scheduler and by a hand-created appraisal, so
    a manual one routes exactly like an auto-generated one."""
    s = _settings()
    d_one, d_two = s.director_one, s.director_two
    emp = frappe.db.get_value("Employee", employee,
                              ["department", "reports_to", "employee_name"], as_dict=True)
    if not emp:
        return {}

    assessment_type = "General" if emp.department in _general_departments(s) else "Technical"
    first_director, needs_second, second_director = _top_director(employee, d_one, d_two)

    # keep-in-loop (CC) director: notified but not a reviewer (e.g. Pranjal for the
    # Frappe team, which reports up to Sumeet). Skip if he's already in the chain.
    loop_depts = {d.strip() for d in (s.loop_departments or "").splitlines() if d.strip()}
    cc_director = s.loop_director if (emp.department in loop_depts and s.loop_director) else None
    if cc_director in (first_director, second_director):
        cc_director = None

    return {
        "assessment_type": assessment_type,
        "reporting_officer": emp.reports_to,
        "first_director": first_director,
        "needs_second_director": needs_second,
        "second_director": second_director,
        "cc_director": cc_director,
        "ratings": _rating_rows(assessment_type),
    }


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

    d = resolve_defaults(employee)
    cc_director = d.get("cc_director")

    doc = frappe.get_doc({
        "doctype": "Logikview Appraisal",
        "employee": employee,
        "anniversary_date": anniversary_date,
        "years_completed": years,
        "workflow_state": "Pending Self-Assessment",
        **d,
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
    if cc_director:
        _notify([_user_of(cc_director)], f"In the loop: appraisal started for {emp.employee_name}",
                f"You're being kept in the loop for {emp.employee_name}'s appraisal ({doc.name}). "
                f"No action needed from you — you'll be notified as it progresses.", doc.name, "created-cc")
    return doc.name


def on_appraisal_update(doc, method=None):
    """On every stage change tell whoever has to act next, and keep the
    in-the-loop (CC) director informed."""
    before = doc.get_doc_before_save()
    if not before or before.workflow_state == doc.workflow_state:
        return

    # the person whose turn it is now (this is what was missing: a director was
    # only nudged by the Monday reminder, never when it actually reached them)
    actor_field = STATE_ACTOR.get(doc.workflow_state)
    actor_user = _user_of(doc.get(actor_field)) if actor_field else None
    if actor_user:
        what = {
            "Pending Self-Assessment": "Please complete your self-assessment.",
            "Pending Manager Review": "Please fill in the RO ratings and your feedback.",
            "Pending Director Review": "Please review and add your feedback.",
            "Pending Final Director": "Please add your closing feedback to finish this appraisal.",
        }.get(doc.workflow_state, "Please review.")
        _notify([actor_user], f"Appraisal awaiting you — {doc.employee_name}",
                f"The appraisal {doc.name} for <b>{doc.employee_name}</b> is now at "
                f"'{doc.workflow_state}'. {what}",
                doc.name, f"actor-{doc.workflow_state}")

    if doc.workflow_state == "Completed":
        _notify([_user_of(doc.employee), _user_of(doc.reporting_officer)],
                f"Appraisal completed — {doc.employee_name}",
                f"The appraisal {doc.name} for {doc.employee_name} is complete. "
                f"The manager and director feedback is on the record.",
                doc.name, "completed")

    cc_user = _user_of(doc.get("cc_director"))
    if cc_user:
        _notify([cc_user], f"Appraisal update: {doc.employee_name} — {doc.workflow_state}",
                f"The appraisal {doc.name} for {doc.employee_name} moved to '{doc.workflow_state}'.",
                doc.name, f"cc-{doc.workflow_state}")


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
                                     "first_director", "second_director", "cc_director",
                                     "workflow_state", "anniversary_date"]):
        actor_field = STATE_ACTOR.get(ap.workflow_state)
        actor_emp = ap.get(actor_field) if actor_field else None
        actor_user = _user_of(actor_emp)

        overdue = ap.anniversary_date and getdate(add_months(ap.anniversary_date, overdue_months)) <= getdate(today())

        if overdue:
            # daily, to everyone involved
            recipients = [_user_of(ap.employee), _user_of(ap.reporting_officer),
                          _user_of(ap.first_director), _user_of(ap.second_director),
                          _user_of(ap.cc_director)] + hr
            subj = f"OVERDUE appraisal: {ap.employee_name} ({ap.workflow_state})"
            msg = (f"The appraisal {ap.name} for {ap.employee_name} has been pending for over "
                   f"{overdue_months} months (stage: {ap.workflow_state}). Please act on it today.")
            _notify(recipients, subj, msg, ap.name, f"overdue-{day}")
        elif is_monday and actor_user:
            subj = f"Reminder: appraisal awaiting you — {ap.employee_name}"
            msg = (f"The appraisal {ap.name} for {ap.employee_name} is at '{ap.workflow_state}' "
                   f"and awaiting your action. Please complete it.")
            _notify([actor_user], subj, msg, ap.name, f"monday-{day}")
