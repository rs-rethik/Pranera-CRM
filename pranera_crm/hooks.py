app_name = "pranera_crm"
app_title = "Pranera CRM"
app_publisher = "Aerele Technologies"
app_description = "A step-by-step deal conversion wizard for Frappe CRM"
app_email = "rethik@aerele.in"
app_license = "mit"

required_apps = ["crm", "erpnext"]

website_route_rules = [
	{"from_route": "/deal_wizard/sw.js", "to_route": "deal_wizard_sw"},
	{"from_route": "/deal_wizard/<path:app_path>", "to_route": "deal_wizard"},
	{"from_route": "/crm-open/<name>", "to_route": "crm_open"},
]

page_renderer = ["pranera_crm.sw.ServiceWorkerRenderer"]

fixtures = [
	{"dt": "CRM Form Script", "filters": [["name", "=", "Pranera Convert Wizard"]]},
	{"dt": "Custom Field", "filters": [["name", "=", "FCRM Settings-enable_convert_to_deal_wizard"]]},
	{"dt": "Report", "filters": [["name", "=", "Deals by Status"]]},
]

standard_queries = {"CRM Lost Reason": "pranera_crm.lost_reasons.search"}

doc_events = {
	"CRM Lead": {"validate": "pranera_crm.lost_reasons.validate"},
	"CRM Deal": {"validate": "pranera_crm.lost_reasons.validate"},
}

scheduler_events = {"cron": {"0 10 * * *": ["pranera_crm.owner_follow_up.run"]}}

before_migrate = "pranera_crm.setup.before_migrate"
after_install = "pranera_crm.setup.after_install"
after_migrate = "pranera_crm.setup.after_migrate"
