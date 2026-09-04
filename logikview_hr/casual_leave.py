"""Casual Leave balance: accrual, the advance/loan cap, and the one place that
computes the figure shown on the employee dashboard, in HR's team view, and
in the exportable report - so the three can never disagree.

Casual Leave already accrues 1 day/month via HRMS's own earned-leave
scheduler (Leave Type.is_earned_leave, capped at 12/year) - that machinery is
untouched, and get_casual_leave_balance reads its result rather than
recomputing accrual by hand. What stock HRMS doesn't have is a cap on how far
into unearned leave someone can dip: "Allow Negative Balance" on the Leave
Type is all-or-nothing - unlimited negative, just a warning - or fully
blocked. enforce_advance_limit adds the middle ground: up to 2 days may be
taken before they're earned, no more.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

LEAVE_TYPE = "Casual Leave"
ADVANCE_LIMIT = 2  # the "loan" - days that may be taken before they're accrued


def _as_admin(fn, *args, **kwargs):
	"""get_leave_balance_on gates on the caller being the employee, their leave
	approver, or someone with Employee read - appropriate for a document the
	caller is directly acting on, wrong for internal aggregation (HR's team
	view, the report, the enforcement hook here) where the whitelisted
	function one level up has already done its own authorization. Runs the
	read-only balance lookup as Administrator rather than re-deriving
	get_leave_balance_on's ledger/carry-forward/expiry logic by hand."""
	current_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		return fn(*args, **kwargs)
	finally:
		frappe.set_user(current_user)


def get_casual_leave_balance(employee, as_of=None):
	"""Accrued / taken / balance / advance-in-use for one employee, as of a
	date (defaults to today). Built on HRMS's own get_leave_balance_on - the
	same ledger-backed function that drives the standard Leave Application
	balance check - rather than re-deriving accrued-minus-taken from Leave
	Allocation and Leave Application directly, so this never disagrees with
	what HRMS itself considers the balance."""
	from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

	as_of = getdate(as_of or today())

	allocation = frappe.db.get_value(
		"Leave Allocation",
		{"employee": employee, "leave_type": LEAVE_TYPE, "docstatus": 1,
		 "from_date": ["<=", as_of], "to_date": [">=", as_of]},
		["total_leaves_allocated"], as_dict=True,
	)
	accrued = flt(allocation.total_leaves_allocated) if allocation else 0.0

	# consider_all_leaves_in_the_allocation_period=True: count every submitted
	# leave in the allocation period, not just ones whose dates have already
	# passed. Without it, an approved leave dated next month doesn't reduce
	# the balance until that date arrives - which would let the advance cap
	# be bypassed by stacking several future-dated approvals that each look
	# individually within the 2-day limit "as of today".
	result = _as_admin(
		get_leave_balance_on, employee, LEAVE_TYPE, as_of,
		consider_all_leaves_in_the_allocation_period=True, for_consumption=True,
	)
	balance = flt(result.get("leave_balance_for_consumption"))

	advance_used = max(0.0, -balance)
	taken = accrued - balance

	return {
		"accrued": accrued,
		"taken": taken,
		"balance": balance,
		"advance_used": advance_used,
		"advance_limit": ADVANCE_LIMIT,
		"advance_remaining": max(0.0, ADVANCE_LIMIT - advance_used),
	}


def enforce_advance_limit(doc, method=None):
	"""Block a Casual Leave application that would push the balance past the
	advance cap. Runs after HRMS's own validate() (doc_events hooks always
	fire after the doctype's own controller - see Document.hook's compose()),
	which - with Allow Negative Balance on - only warns, never blocks; this is
	the actual enforcement, and total_leave_days is already computed by the
	time this runs."""
	if doc.leave_type != LEAVE_TYPE or doc.docstatus == 2:
		return

	current = get_casual_leave_balance(doc.employee)["balance"]
	requested = flt(doc.total_leave_days)
	projected = current - requested

	if projected < -ADVANCE_LIMIT:
		can_still_borrow = max(0.0, ADVANCE_LIMIT - max(0.0, -current))
		frappe.throw(
			_(
				"This request needs {0} Casual Leave day(s), but only {1} can still be taken "
				"in advance of what's accrued (current balance {2}). Approving it would leave "
				"the balance at {3}, past the {4}-day advance limit."
			).format(requested, can_still_borrow, current, projected, ADVANCE_LIMIT),
			title=_("Advance Leave Limit Exceeded"),
		)


@frappe.whitelist()
def get_my_casual_leave_balance():
	"""Employee dashboard tile. Casual Leave only - Comp Off and any other
	leave type are shown separately (see get_other_leave_balances), never
	blended into this figure."""
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee:
		return {"casual_leave": None, "other": []}
	return {
		"casual_leave": get_casual_leave_balance(employee),
		"other": get_other_leave_balances(employee),
	}


def get_other_leave_balances(employee):
	"""Everything except Casual Leave and Paid Leave (Paid Leave has been
	excluded from this widget from the start - see the original My Leave
	Balance script). Comp Off is the main one in practice; kept as simple
	accrued-minus-taken since the advance/loan concept in this spec is
	Casual-Leave-specific."""
	today_ = today()
	EXCLUDED = (LEAVE_TYPE, "Paid Leave")
	allocs = frappe.get_all(
		"Leave Allocation",
		filters={"employee": employee, "docstatus": 1, "leave_type": ["not in", EXCLUDED],
		         "from_date": ["<=", today_], "to_date": [">=", today_]},
		fields=["leave_type", "total_leaves_allocated", "from_date", "to_date"],
	)
	rows = []
	for a in allocs:
		taken = flt(frappe.db.get_value(
			"Leave Application",
			{"employee": employee, "leave_type": a.leave_type, "docstatus": 1,
			 "from_date": [">=", a.from_date], "to_date": ["<=", a.to_date]},
			"sum(total_leave_days)",
		))
		allocated = flt(a.total_leaves_allocated)
		rows.append({"leave_type": a.leave_type, "allocated": allocated, "taken": taken,
		             "balance": allocated - taken})
	return rows


@frappe.whitelist()
def get_team_casual_leave_balance():
	"""HR's team view (Leave Management dashboard block). Same authorization
	as the existing Team Leave Balance script it replaces: HR Manager, HR
	User, System Manager or Administrator."""
	me = frappe.session.user
	allowed = me == "Administrator" or any(
		frappe.db.exists("Has Role", {"parent": me, "parenttype": "User", "role": r})
		for r in ("HR Manager", "HR User", "System Manager")
	)
	if not allowed:
		return {"error": "not permitted"}

	out = []
	for e in frappe.get_all("Employee", filters={"status": "Active"},
	                        fields=["name", "employee_name", "department"],
	                        order_by="employee_name"):
		dept = (e.department or "")
		if dept.endswith(" - LA"):
			dept = dept[:-5]
		cl = get_casual_leave_balance(e.name)
		# same {leave_type, allocated, taken, balance} row shape the existing
		# Leave Management table already renders, so this drops in without a
		# JS rewrite - "allocated" here means accrued-to-date, same as every
		# other row, never the full annual entitlement
		cl_row = {"leave_type": LEAVE_TYPE, "allocated": cl["accrued"], "taken": cl["taken"],
		          "balance": cl["balance"], "advance_used": cl["advance_used"]}
		out.append({
			"employee": e.name, "employee_name": e.employee_name, "department": dept,
			"rows": [cl_row] + get_other_leave_balances(e.name),
		})
	return out
