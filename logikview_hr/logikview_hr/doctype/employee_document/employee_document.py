# Copyright (c) 2026, Logikview Analytics and contributors
# For license information, please see license.txt

from urllib.parse import unquote, urlparse

import frappe
from frappe.model.document import Document

# Where a link points, spelled the way people say it. Anything not listed
# falls back to the bare host, which is still more use than the raw URL.
KNOWN_HOSTS = {
	"drive.google.com": "Google Drive",
	"docs.google.com": "Google Docs",
	"onedrive.live.com": "OneDrive",
	"1drv.ms": "OneDrive",
	"sharepoint.com": "SharePoint",
	"dropbox.com": "Dropbox",
}


class EmployeeDocument(Document):
	def validate(self):
		self.set_document_name()

	def set_document_name(self):
		"""Give every row a name a human can scan in the list.

		HR reads this list to check who has handed in what, so the useful
		column is the document's own name - the raw attachment URL is not
		readable, and the document type alone does not tell two marksheets
		apart. Whatever the employee typed always wins; this only fills the
		blank."""
		if (self.document_name or "").strip():
			return
		self.document_name = self.derive_document_name()

	def derive_document_name(self):
		url = (self.attachment or "").strip()
		if not url:
			return None

		# Our own uploads: the last path segment IS the filename.
		if url.startswith(("/files/", "/private/files/")):
			return unquote(url.rsplit("/", 1)[-1])

		# An external link. The tail of the URL is not a filename - a Drive
		# share URL ends in "view?usp=sharing" - so name it by where it lives
		# and let the document type carry the meaning.
		host = (urlparse(url).netloc or "").lower()
		if host.startswith("www."):
			host = host[4:]
		if not host:
			return unquote(url.rsplit("/", 1)[-1]) or None
		label = next(
			(
				pretty
				for domain, pretty in KNOWN_HOSTS.items()
				if host == domain or host.endswith("." + domain)
			),
			host,
		)
		return f"{self.document_type} ({label} link)" if self.document_type else f"{label} link"


def backfill_document_names():
	"""Name the rows that pre-date the document_name field - without this the
	list view shows a bare EMPDOC-xxxxx id for them, since document_name is
	the title field."""
	rows = frappe.get_all("Employee Document", filters={"document_name": ["in", ["", None]]}, pluck="name")
	for name in rows:
		doc = frappe.get_doc("Employee Document", name)
		derived = doc.derive_document_name()
		if derived:
			frappe.db.set_value("Employee Document", name, "document_name", derived, update_modified=False)
