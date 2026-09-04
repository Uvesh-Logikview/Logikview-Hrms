// Copyright (c) 2026, Logikview Analytics and contributors
// For license information, please see license.txt

frappe.query_reports["Casual Leave Balance"] = {
	filters: [
		{
			fieldname: "as_of_date",
			label: __("As of Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			description: __("Accrual and usage are counted up to this date - matches the employee dashboard when left as today."),
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
	],
};
