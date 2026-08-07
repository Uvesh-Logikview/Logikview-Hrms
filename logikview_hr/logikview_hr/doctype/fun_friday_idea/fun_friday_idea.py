# Copyright (c) 2026, Logikview Analytics and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FunFridayIdea(Document):
	def before_insert(self):
		if not self.suggested_by:
			self.suggested_by = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")

	def validate(self):
		self.vote_count = len(self.votes or [])


@frappe.whitelist()
def toggle_like(idea: str):
	"""Like / unlike an idea. One vote per user."""
	doc = frappe.get_doc("Fun Friday Idea", idea)
	user = frappe.session.user
	# a User link normalises to lowercase, while session.user keeps the original
	# case - compare case-insensitively or the same person can vote twice
	existing = [v for v in doc.votes if (v.user or "").lower() == user.lower()]
	if existing:
		for v in existing:
			doc.remove(v)
		liked = False
	else:
		doc.append("votes", {"user": user})
		liked = True
	doc.vote_count = len(doc.votes)
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"liked": liked, "vote_count": doc.vote_count}
