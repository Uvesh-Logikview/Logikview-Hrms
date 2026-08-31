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
// text is swapped in the DOM for HR only. Purely cosmetic - same shortcut, same
// list, permissions unchanged.
//
// The role test lives INSIDE relabel(): this file is loaded via app_include_js,
// which runs before frappe.boot has populated the user's roles, so checking up
// front returned false and the whole thing silently never ran.
(function () {
	var FROM = "My Documents";
	var TO = "Employee Documents";

	function isHR() {
		try {
			return frappe.user.has_role("HR Manager") || frappe.user.has_role("HR User");
		} catch (e) {
			return false;   // roles not loaded yet - a later mutation will retry
		}
	}

	function relabel() {
		if (!isHR()) return;
		document
			.querySelectorAll('[data-widget-name="' + FROM + '"] .widget-title')
			.forEach(function (el) {
				// set_title() wraps the label in <span class="ellipsis">, so the
				// text is not a direct child of .widget-title
				var target = el.querySelector("span") || el;
				if (target.textContent.trim() === FROM) {
					target.textContent = TO;
					target.setAttribute("title", TO);
				}
			});
	}

	relabel();
	// shortcuts re-render on every workspace switch
	new MutationObserver(relabel).observe(document.body, {
		childList: true,
		subtree: true,
	});
})();
