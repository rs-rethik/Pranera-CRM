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
	{
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"FCRM Settings-enable_convert_to_deal_wizard",
					# Pranera's own fields, made on the client site first; the Deal Dashboard reads them.
					# No module on purpose: uninstalling this app must not drop their data.
					"CRM Products-custom_uom",
					"CRM Products-custom_item_code",
					"CRM Organization-custom_customer",
					"CRM Organization-custom_sales_person",
					"CRM Deal-custom_customer",
					"CRM Deal-custom_sales_person",
					"Sales Order-custom_crm_deal",
				],
			]
		],
	},
	{"dt": "Report", "filters": [["name", "=", "Deals by Status"]]},
]

standard_queries = {"CRM Lost Reason": "pranera_crm.lost_reasons.search"}

doc_events = {
	"CRM Lead": {
		"validate": "pranera_crm.lost_reasons.validate",
		# a lead's contact joins the organization / customer its Organization names (lead_contact.py)
		"after_insert": "pranera_crm.lead_contact.on_lead_change",
		"on_update": "pranera_crm.lead_contact.on_lead_change",
	},
	"CRM Deal": {
		"validate": "pranera_crm.lost_reasons.validate",
		# cached Deal Dashboards go stale with any deal change (one cache write, after commit)
		"on_update": "pranera_crm.deal_dashboard.api.bump_cache_version",
		"on_trash": "pranera_crm.deal_dashboard.api.bump_cache_version",
	},
	"CRM Organization": {"on_update": "pranera_crm.deal_dashboard.api.bump_cache_version"},
	"Customer": {"on_update": "pranera_crm.deal_dashboard.api.bump_cache_version"},
	"Sales Order": {
		"on_submit": "pranera_crm.deal_dashboard.api.bump_cache_version",
		"on_cancel": "pranera_crm.deal_dashboard.api.bump_cache_version",
		"on_update_after_submit": "pranera_crm.deal_dashboard.api.bump_cache_version",
	},
	# a user's Sales Person comes from Sales Person -> Employee -> User
	"Sales Person": {"on_update": "pranera_crm.deal_dashboard.scope.clear_cache"},
	"Employee": {"on_update": "pranera_crm.deal_dashboard.scope.clear_cache"},
}

scheduler_events = {
	"cron": {
		"0 10 * * *": ["pranera_crm.owner_follow_up.run"],
		# the conversion report PDF on WhatsApp, when Conversion Report Settings says it is due
		"*/15 * * * *": ["pranera_crm.conversion_report.run_scheduled"],
	}
}

before_migrate = "pranera_crm.setup.before_migrate"
after_install = "pranera_crm.setup.after_install"
after_migrate = "pranera_crm.setup.after_migrate"
