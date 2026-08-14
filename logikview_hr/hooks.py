app_name = "logikview_hr"
app_title = "Logikview HR"
app_publisher = "Logikview Analytics"
app_description = "Online GPS check-in for Logikview Analytics HR"
app_email = "admin@logikview.local"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "logikview_hr",
# 		"logo": "/assets/logikview_hr/logo.png",
# 		"title": "Logikview HR",
# 		"route": "/logikview_hr",
# 		"has_permission": "logikview_hr.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/logikview_hr/css/logikview_hr.css"
# app_include_js = "/assets/logikview_hr/js/logikview_hr.js"

# include js, css files in header of web template
# web_include_css = "/assets/logikview_hr/css/logikview_hr.css"
# web_include_js = "/assets/logikview_hr/js/logikview_hr.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "logikview_hr/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "logikview_hr/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "logikview_hr.utils.jinja_methods",
# 	"filters": "logikview_hr.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "logikview_hr.install.before_install"
# after_install = "logikview_hr.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "logikview_hr.uninstall.before_uninstall"
# after_uninstall = "logikview_hr.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "logikview_hr.utils.before_app_install"
# after_app_install = "logikview_hr.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "logikview_hr.utils.before_app_uninstall"
# after_app_uninstall = "logikview_hr.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "logikview_hr.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"logikview_hr.tasks.all"
# 	],
# 	"daily": [
# 		"logikview_hr.tasks.daily"
# 	],
# 	"hourly": [
# 		"logikview_hr.tasks.hourly"
# 	],
# 	"weekly": [
# 		"logikview_hr.tasks.weekly"
# 	],
# 	"monthly": [
# 		"logikview_hr.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "logikview_hr.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "logikview_hr.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "logikview_hr.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["logikview_hr.utils.before_request"]
# after_request = ["logikview_hr.utils.after_request"]

# Job Events
# ----------
# before_job = ["logikview_hr.utils.before_job"]
# after_job = ["logikview_hr.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"logikview_hr.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []



# Fixtures
# --------
# Version-controlled config that reproduces the whole GPS check-in feature on any
# site via `bench install-app logikview_hr`. Custom HTML Block must import before
# the "My Attendance" workspace that references it.
fixtures = [
	{"dt": "Server Script", "filters": [["name", "in", ["Checkin Toggle", "Today Working Hours"]]]},
	{"dt": "Custom HTML Block", "filters": [["name", "in", ["Checkin button functionality", "Attendance Calendar", "Attendance Dashboard"]]]},
	{"dt": "Custom Field", "filters": [["name", "in", [
		"Employee Checkin-custom_location_accuracy",
		"Employee Checkin-custom_auto_checkout",
		"Attendance Request-custom_late_category",
		"Attendance Request-custom_late_by_minutes",
		"Attendance Request-custom_hr_warning",
	]]]},
	# Regularization (Feature 2): "Late Arrival" reason option, the rename to
	# "Regularization", and the late-category colour indicator on the list view.
	{"dt": "Property Setter", "filters": [["name", "in", [
		"Attendance Request-reason-options",
		"Employee-gender-link_filters",
		"Employee-salutation-link_filters",
		"Attendance Request-custom_late_category-in_standard_filter",
		"Attendance Request-custom_late_category-in_list_view",
		"Attendance Request-custom_late_by_minutes-in_list_view",
		"Attendance Request-custom_late_by_minutes-label",
		"Attendance Request-to_date-in_list_view",
		"Employee Checkin-device_id-in_list_view",
		"Employee Checkin-device_id-label",
		"Employee Checkin-device_id-in_standard_filter",
		"Employee Checkin-custom_auto_checkout-in_list_view",
		"Employee Checkin-custom_auto_checkout-in_standard_filter",
	]]]},
	{"dt": "Translation", "filters": [["source_text", "=", "Attendance Request"]]},
	{"dt": "Client Script", "filters": [["name", "in", [
		"Regularization Late Colours",
		"Logikview Appraisal Field Locks",
		"Fun Friday Like Button",
		"Fun Friday List Colours",
		"Employee Approver Pickers",
		"Employee Checkin Location",
	]]]},
	# Fun Friday idea board (seed ideas ship with the app; everyone can see/add)
	{"dt": "Fun Friday Idea"},
	{"dt": "Logikview Checkin Settings"},
	# Appraisal cycle (Feature 3): workflow + its states/actions + the director
	# routing config (single). The DocTypes themselves ship as app module JSON.
	{"dt": "Workflow", "filters": [["name", "=", "Logikview Appraisal Workflow"]]},
	{"dt": "Workflow State", "filters": [["name", "in", [
		"Pending Self-Assessment", "Pending Manager Review",
		"Pending Director Review", "Pending Final Director", "Completed",
	]]]},
	{"dt": "Workflow Action Master", "filters": [["name", "in", [
		"Submit Self-Assessment", "Submit Manager Review", "Forward to Final Director",
		"Complete Appraisal", "HR: Skip to Manager", "HR: Skip to Director",
		"HR: Skip to Final Director", "HR: Complete",
	]]]},
	{"dt": "Logikview Appraisal Settings"},
]

# Desk setup: build the Home dashboard (check-in card + Employee Details shortcuts)
# and trim the sidebar to HR, on install and after every migrate.
after_install = "logikview_hr.workspace_setup.setup_desk"
after_migrate = "logikview_hr.workspace_setup.setup_desk"

# Row-level visibility: employees see only their own records (+ direct reports for
# managers); HR Manager / HR User / System Manager see all.
permission_query_conditions = {
	"Employee": "logikview_hr.permissions.employee_query",
	"Attendance": "logikview_hr.permissions.attendance_query",
	"Leave Application": "logikview_hr.permissions.leave_application_query",
	"Employee Checkin": "logikview_hr.permissions.employee_checkin_query",
	"Expense Claim": "logikview_hr.permissions.expense_claim_query",
	"Attendance Request": "logikview_hr.permissions.attendance_request_query",
	"Leave Allocation": "logikview_hr.permissions.leave_allocation_query",
	"Logikview Appraisal": "logikview_hr.permissions.appraisal_query",
}

has_permission = {
	"Employee": "logikview_hr.permissions.employee_has_permission",
	"Attendance": "logikview_hr.permissions.employee_linked_has_permission",
	"Leave Application": "logikview_hr.permissions.employee_linked_has_permission",
	"Employee Checkin": "logikview_hr.permissions.employee_linked_has_permission",
	"Expense Claim": "logikview_hr.permissions.employee_linked_has_permission",
	"Attendance Request": "logikview_hr.permissions.employee_linked_has_permission",
	"Leave Allocation": "logikview_hr.permissions.employee_linked_has_permission",
	"Logikview Appraisal": "logikview_hr.permissions.appraisal_has_permission",
}

scheduler_events = {
	"daily": [
		"logikview_hr.appraisal.create_due_appraisals",
		"logikview_hr.appraisal.send_appraisal_reminders",
	],
	# auto check-out: every 15 min in the evening (function gates to >= 19:15)
	"cron": {
		"*/15 19-23 * * *": [
			"logikview_hr.checkin.auto_checkout",
		],
	},
}

doc_events = {
	"Logikview Appraisal": {
		# notify the in-the-loop (CC) director whenever the appraisal advances a stage
		"on_update": "logikview_hr.appraisal.on_appraisal_update",
	},
	"Attendance Request": {
		# tell the employee when HR leaves a warning/note on their regularization
		"on_update": "logikview_hr.regularization.notify_warning",
		"on_submit": "logikview_hr.regularization.notify_warning",
	},
}
