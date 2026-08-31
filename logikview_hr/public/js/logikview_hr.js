// Hide the floating "+ New" workspace-page button for everyone except the
// Administrator account - it lets anyone create a new sidebar page, which
// isn't something employees or HR should be doing. It's part of the
// workspace chrome (workspace.js's .workspace-footer), not tied to any one
// doctype, so it re-renders on every workspace switch - a MutationObserver
// keeps it hidden through that instead of a one-shot check on page load.
(function () {
	if (frappe.session.user === "Administrator") return;

	function hide_new_workspace_btn() {
		document.querySelectorAll(".btn-new-workspace").forEach(function (el) {
			el.style.display = "none";
		});
	}

	hide_new_workspace_btn();
	new MutationObserver(hide_new_workspace_btn).observe(document.body, {
		childList: true,
		subtree: true,
	});
})();

// The "My Documents" shortcut is accurate for an employee, who only ever sees
// their own files, but misleading for HR, whose row-level access covers the
// whole company. One shared workspace shortcut cannot carry two labels, so the
// text is swapped in the DOM for HR only. Purely cosmetic - it is the same
// shortcut to the same list, and the underlying permissions are unchanged.
(function () {
	if (!frappe.user || !frappe.user.has_role) return;
	if (!(frappe.user.has_role("HR Manager") || frappe.user.has_role("HR User"))) return;

	var FROM = "My Documents";
	var TO = "Employee Documents";

	function relabel() {
		document
			.querySelectorAll('[data-widget-name="' + FROM + '"] .widget-title')
			.forEach(function (el) {
				// only touch the text node, so the icon markup beside it survives
				el.childNodes.forEach(function (n) {
					if (n.nodeType === 3 && n.nodeValue.trim() === FROM) {
						n.nodeValue = n.nodeValue.replace(FROM, TO);
					}
				});
				if (el.textContent.trim() === FROM) el.textContent = TO;
			});
	}

	relabel();
	// shortcuts re-render on every workspace switch
	new MutationObserver(relabel).observe(document.body, {
		childList: true,
		subtree: true,
	});
})();
