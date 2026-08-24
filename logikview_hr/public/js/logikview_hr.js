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
