# Copyright (c) 2026, Logikview Analytics and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today


class LogikviewAppraisal(Document):
	def validate(self):
		self.apply_defaults()
		self._validate_mandatory_on_transition()

	def _validate_mandatory_on_transition(self):
		"""Block moving past a stage unless that stage's owner actually filled
		everything in - a stage transition means the workflow_state changed
		from what it was before this save."""
		before = self.get_doc_before_save()
		if not before or before.workflow_state == self.workflow_state:
			return
		leaving_state = before.workflow_state

		if leaving_state == "Pending Self-Assessment":
			missing = [r.parameter for r in self.ratings if not r.employee_rating]
			if missing:
				frappe.throw(frappe._("Please rate every parameter before submitting your "
				                      "self-assessment. Missing: {0}").format(", ".join(missing)))
			questions = {
				"q_accomplishments": frappe._("What were your most significant work-related accomplishments?"),
				"q_not_accomplished": frappe._("What did you NOT accomplish that you had planned? Why?"),
				"q_goals": frappe._("Goals for the coming year"),
			}
			for fieldname, label in questions.items():
				if not (self.get(fieldname) or "").strip():
					frappe.throw(frappe._("Please answer: {0}").format(label))

		elif leaving_state == "Pending Manager Review":
			missing = [r.parameter for r in self.ratings if not r.ro_rating]
			if missing:
				frappe.throw(frappe._("Please rate every parameter before submitting your "
				                      "review. Missing: {0}").format(", ".join(missing)))

	def apply_defaults(self):
		"""A hand-created appraisal must end up identical to a scheduler-created one:
		the right form (Technical/General), the full set of rating rows, and the
		reviewer chain - otherwise the workflow has nobody to route to and rows can
		be missed."""
		if not self.employee:
			return

		from logikview_hr.appraisal import resolve_defaults

		d = resolve_defaults(self.employee)
		if not d:
			return

		# routing: only fill what the user hasn't set
		for field in ("reporting_officer", "first_director", "second_director", "cc_director"):
			if not self.get(field):
				self.set(field, d.get(field))
		if self.needs_second_director is None:
			self.needs_second_director = d.get("needs_second_director")

		# a Select pre-fills with its first option ("Technical"), so "if not set"
		# would never correct it - decide it from the department on a new doc
		if self.is_new():
			self.assessment_type = d.get("assessment_type")

		self._sync_rating_rows()
		self._collect_seniors()

	def _collect_seniors(self):
		"""Everyone senior to this employee: the whole reporting line above them
		(both managers at each level), the directors, and HR. Any of them may write
		the feedback - it should not be locked to one person at one exact stage."""
		seniors, seen, queue = set(), set(), [self.employee]
		while queue:
			emp = queue.pop()
			if not emp or emp in seen:
				continue
			seen.add(emp)
			row = frappe.db.get_value("Employee", emp,
			                          ["reports_to", "custom_reporting_manager_2"], as_dict=True) or {}
			for mgr in (row.get("reports_to"), row.get("custom_reporting_manager_2")):
				if mgr and mgr not in seen:
					queue.append(mgr)
					user = frappe.db.get_value("Employee", mgr, "user_id")
					if user:
						seniors.add(user)

		for field in ("first_director", "second_director", "cc_director"):
			user = frappe.db.get_value("Employee", self.get(field), "user_id") if self.get(field) else None
			if user:
				seniors.add(user)

		seniors.update(frappe.get_all("Has Role",
		                              filters={"role": ["in", ["HR Manager", "HR User"]],
		                                       "parenttype": "User"}, pluck="parent"))
		seniors.discard(frappe.db.get_value("Employee", self.employee, "user_id"))
		self.senior_users = ",".join(sorted(u for u in seniors if u))

	def _sync_rating_rows(self):
		"""The parameter list is fixed by assessment type. Rebuild it to exactly that
		set - re-adding rows that were never added or were deleted, dropping rows
		that no longer apply (e.g. after switching Technical <-> General) - while
		keeping every rating already entered."""
		from logikview_hr.appraisal import _rating_rows

		expected = _rating_rows(self.assessment_type or "Technical")
		current = {(r.category, r.parameter): r for r in self.ratings}
		if [(r.category, r.parameter) for r in self.ratings] == \
		   [(e["category"], e["parameter"]) for e in expected]:
			return

		rows = []
		for i, e in enumerate(expected, start=1):
			existing = current.get((e["category"], e["parameter"]))
			row = {"category": e["category"], "parameter": e["parameter"], "idx": i}
			if existing:
				row["employee_rating"] = existing.employee_rating
				row["ro_rating"] = existing.ro_rating
			rows.append(row)
		self.set("ratings", [])
		for row in rows:
			self.append("ratings", row)

		if not self.anniversary_date:
			doj = frappe.db.get_value("Employee", self.employee, "date_of_joining")
			if doj:
				doj = getdate(doj)
				t = getdate(today())
				year = t.year if (doj.month, doj.day) >= (t.month, t.day) else t.year + 1
				try:
					self.anniversary_date = doj.replace(year=year)
				except ValueError:                      # 29 Feb in a non-leap year
					self.anniversary_date = doj.replace(year=year, day=28)
				self.years_completed = year - doj.year

		if not self.workflow_state:
			self.workflow_state = "Pending Self-Assessment"
