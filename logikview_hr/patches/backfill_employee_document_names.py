# Copyright (c) 2026, Logikview Analytics and contributors
# For license information, please see license.txt

from logikview_hr.logikview_hr.doctype.employee_document.employee_document import (
	backfill_document_names,
)


def execute():
	"""document_name is now the title field for Employee Document. Rows created
	before it existed have it empty, which would show as a bare EMPDOC-xxxxx id
	in the list - name them from their attachment."""
	backfill_document_names()
