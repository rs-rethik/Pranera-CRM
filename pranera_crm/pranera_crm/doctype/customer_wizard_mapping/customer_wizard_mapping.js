const TARGET_DOCTYPES = ["Customer", "Address", "Contact", "CRM Lead"];
const FIELD_PICKERS = {
	target_doctype: "target_fieldname",
	secondary_target_doctype: "secondary_target_fieldname",
};

frappe.ui.form.on("Customer Wizard Mapping", {
	setup(frm) {
		for (const doctype_field of Object.keys(FIELD_PICKERS)) {
			frm.set_query(doctype_field, () => ({ filters: { name: ["in", TARGET_DOCTYPES] } }));
		}
	},

	refresh(frm) {
		for (const [doctype_field, fieldname_field] of Object.entries(FIELD_PICKERS)) {
			load_field_options(frm, doctype_field, fieldname_field);
		}
	},

	target_doctype(frm) {
		frm.set_value("target_fieldname", "");
		load_field_options(frm, "target_doctype", "target_fieldname");
		if (frm.is_new() && frm.doc.target_doctype) {
			frm.set_value(
				"requires_erpnext_bridge",
				frm.doc.target_doctype === "CRM Lead" ? 0 : 1
			);
		}
	},

	secondary_target_doctype(frm) {
		frm.set_value("secondary_target_fieldname", "");
		load_field_options(frm, "secondary_target_doctype", "secondary_target_fieldname");
	},
});

function load_field_options(frm, doctype_field, fieldname_field) {
	const doctype = frm.doc[doctype_field];
	if (!doctype) {
		set_field_options(frm, fieldname_field, []);
		return;
	}
	frappe.call({
		method: "pranera_crm.pranera_crm.doctype.customer_wizard_mapping.customer_wizard_mapping.get_target_fields",
		args: { doctype },
		callback: (r) => set_field_options(frm, fieldname_field, r.message || []),
	});
}

// An Autocomplete control reads its options once when it is built, so a later
// set_df_property alone is not enough: hand the list to the live control too.
function set_field_options(frm, fieldname, options) {
	frm.set_df_property(fieldname, "options", options);
	const control = frm.fields_dict[fieldname];
	if (control && control.set_data) {
		control.set_data(options);
		frm.refresh_field(fieldname);
	}
}
