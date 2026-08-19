"""One place for HR notifications: the in-app bell **and** an email.

Every HR flow (leave, WFH, comp-off, regularization, appraisal) used to only
insert a Notification Log, which meant people had to be logged in to notice.
Now that an outgoing account is configured, the same message is also emailed.

Email failures are swallowed on purpose: a mail server hiccup must never roll
back an approval or block a workflow transition.
"""

import frappe

BRAND = "Logikview HR"


def _has_outgoing():
	return bool(frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1}))


def _form_url(doctype, docname):
	try:
		return frappe.utils.get_url_to_form(doctype, docname)
	except Exception:
		return frappe.utils.get_url("/app")


def _email_body(message, doctype, docname):
	body = f"<div style='font-size:14px;line-height:1.6;color:#1f272e;'>{message}</div>"
	if doctype and docname:
		url = _form_url(doctype, docname)
		body += (
			f"<p style='margin-top:18px;'>"
			f"<a href='{url}' style='background:#1F4E78;color:#fff;text-decoration:none;"
			f"padding:9px 16px;border-radius:6px;font-size:13px;font-weight:600;'>Open in {BRAND}</a>"
			f"</p><p style='font-size:11.5px;color:#8a94a0;margin-top:14px;'>{url}</p>"
		)
	return body


def notify(users, subject, message, doctype=None, docname=None, dedup_key=None, email=True):
	"""Bell + email. `dedup_key` stops the same nudge repeating for a document."""
	recipients = {u for u in (users or []) if u and u != "Administrator"}
	if not recipients:
		return

	sent_to = []
	for user in recipients:
		if dedup_key and docname:
			marker = f"{docname}|{dedup_key}"
			if frappe.db.exists("Notification Log",
			                    {"for_user": user, "document_name": docname,
			                     "subject": ["like", f"%{marker}%"]}):
				continue
			log_subject = f"{subject}<!--{marker}-->"
		else:
			log_subject = subject

		try:
			frappe.get_doc({
				"doctype": "Notification Log", "for_user": user, "type": "Alert",
				"document_type": doctype, "document_name": docname,
				"subject": log_subject, "email_content": message,
			}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(f"notification log failed for {user}", "Logikview Notify")
		sent_to.append(user)

	if not (email and sent_to and _has_outgoing()):
		return
	try:
		frappe.sendmail(
			recipients=sent_to,
			subject=f"[{BRAND}] {subject}",
			message=_email_body(message, doctype, docname),
			reference_doctype=doctype,
			reference_name=docname,
			now=False,                     # queued, so a slow SMTP never blocks a save
		)
	except Exception:
		frappe.log_error(f"notification email failed: {subject}", "Logikview Notify")
