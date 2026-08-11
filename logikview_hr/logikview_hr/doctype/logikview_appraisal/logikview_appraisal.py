# Copyright (c) 2026, Logikview Analytics and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today


class LogikviewAppraisal(Document):
	def validate(self):
		self.apply_defaults()

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
