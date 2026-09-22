app_name = "pranera_crm"
app_title = "Pranera CRM"
app_publisher = "Aerele Technologies"
app_description = "A step-by-step deal conversion wizard for Frappe CRM"
app_email = "rethik@aerele.in"
app_license = "mit"

# Apps
# ------------------

required_apps = ["crm", "erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "pranera_crm",
# 		"logo": "/assets/pranera_crm/logo.png",
# 		"title": "Pranera CRM",
# 		"route": "/pranera_crm",
# 		"has_permission": "pranera_crm.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/pranera_crm/css/pranera_crm.css"
# app_include_js = "/assets/pranera_crm/js/pranera_crm.js"

# include js, css files in header of web template
# web_include_css = "/assets/pranera_crm/css/pranera_crm.css"
# web_include_js = "/assets/pranera_crm/js/pranera_crm.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "pranera_crm/public/scss/website"

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
# app_include_icons = "pranera_crm/public/icons.svg"

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
# 	"methods": "pranera_crm.utils.jinja_methods",
# 	"filters": "pranera_crm.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "pranera_crm.install.before_install"
# after_install = "pranera_crm.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "pranera_crm.uninstall.before_uninstall"
# after_uninstall = "pranera_crm.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "pranera_crm.utils.before_app_install"
# after_app_install = "pranera_crm.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "pranera_crm.utils.before_app_uninstall"
# after_app_uninstall = "pranera_crm.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "pranera_crm.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["pranera_crm.search.awesomebar_results"]

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
# 		"pranera_crm.tasks.all"
# 	],
# 	"daily": [
# 		"pranera_crm.tasks.daily"
# 	],
# 	"hourly": [
# 		"pranera_crm.tasks.hourly"
# 	],
# 	"weekly": [
# 		"pranera_crm.tasks.weekly"
# 	],
# 	"monthly": [
# 		"pranera_crm.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "pranera_crm.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "pranera_crm.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "pranera_crm.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["pranera_crm.utils.before_request"]
# after_request = ["pranera_crm.utils.after_request"]

# Job Events
# ----------
# before_job = ["pranera_crm.utils.before_job"]
# after_job = ["pranera_crm.utils.after_job"]

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
# 	"pranera_crm.auth.validate"
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



# Deal wizard
# -----------

# The more specific sw.js rule wins over the catch-all (werkzeug prefers static
# parts), so the service worker is not swallowed by the SPA page.
website_route_rules = [
	{"from_route": "/deal_wizard/sw.js", "to_route": "deal_wizard_sw"},
	{"from_route": "/deal_wizard/<path:app_path>", "to_route": "deal_wizard"},
]

# Serves /deal_wizard/sw.js with `Service-Worker-Allowed: /deal_wizard/`
page_renderer = ["pranera_crm.sw.ServiceWorkerRenderer"]

# Adds a "Convert (Wizard)" action to the CRM Lead page
fixtures = [
	{"dt": "CRM Form Script", "filters": [["name", "=", "Pranera Convert Wizard"]]},
	# "Enable Convert to Deal Wizard" switch on CRM Settings
	{"dt": "Custom Field", "filters": [["name", "=", "FCRM Settings-enable_convert_to_deal_wizard"]]},
	# Starting set of question -> answer -> value mappings for the ERPNext Customer
	# step; edit, disable or add to these freely in Customer Wizard Mapping.
	{"dt": "Customer Wizard Mapping"},
]

# Store the switch's default (enabled) once; never overwrites a saved value
after_install = "pranera_crm.setup.after_install"
after_migrate = "pranera_crm.setup.after_migrate"
