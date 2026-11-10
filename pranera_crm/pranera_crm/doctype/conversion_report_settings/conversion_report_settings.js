// Conversion Report Settings: who gets the CRM conversion report PDF on WhatsApp, and when.
// Preview PDF and Send Now ask for the period first (pranera_crm/conversion_report.py).

frappe.ui.form.on("Conversion Report Settings", {
	setup(frm) {
		frm.set_query("template", () => ({
			filters: { header_type: "DOCUMENT", status: "APPROVED" },
		}));
	},

	refresh(frm) {
		frm.add_custom_button(__("Preview PDF"), () =>
			ask_period(frm, __("Preview PDF"), (args) => {
				const query = new URLSearchParams(args).toString();
				window.open(
					`/api/method/pranera_crm.conversion_report.preview?${query}`,
					"_blank"
				);
			})
		);
		frm.add_custom_button(__("Send Now"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save your changes before sending."));
				return;
			}
			ask_period(frm, __("Send Now"), (args) =>
				frappe.call({
					method: "pranera_crm.conversion_report.send_now",
					args,
					freeze: true,
					freeze_message: __("Making the PDF and sending it on WhatsApp…"),
					callback: ({ message }) => {
						show_results(message);
						frm.reload_doc();
					},
				})
			);
		}).addClass("btn-primary");
	},
});

async function ask_period(frm, title, action) {
	const presets = (await frappe.xcall("pranera_crm.conversion_report.presets")) || [];
	const options = [...presets, { value: "custom", label: __("Custom dates") }];
	const dialog = new frappe.ui.Dialog({
		title,
		fields: [
			{
				fieldname: "preset",
				label: __("Period"),
				fieldtype: "Select",
				options: options.map((o) => ({ value: o.value, label: o.label })),
				default: "last_week",
				reqd: 1,
			},
			{
				fieldname: "from_date",
				label: __("From"),
				fieldtype: "Date",
				depends_on: "eval:doc.preset=='custom'",
				mandatory_depends_on: "eval:doc.preset=='custom'",
			},
			{
				fieldname: "to_date",
				label: __("To"),
				fieldtype: "Date",
				depends_on: "eval:doc.preset=='custom'",
				mandatory_depends_on: "eval:doc.preset=='custom'",
			},
		],
		primary_action_label: title,
		primary_action(values) {
			dialog.hide();
			const args = { preset: values.preset };
			if (values.preset === "custom") {
				args.from_date = values.from_date;
				args.to_date = values.to_date;
			}
			action(args);
		},
	});
	dialog.show();
}

function show_results(message) {
	if (!message) return;
	const rows = (message.results || [])
		.map(
			(r) => `<tr><td>${frappe.utils.escape_html(r.name || "")}</td>
				<td>${frappe.utils.escape_html(r.number || "")}</td>
				<td><span class="indicator-pill ${
					r.status === "Sent" ? "green" : r.status === "Failed" ? "red" : "orange"
				}">${frappe.utils.escape_html(r.status)}</span></td>
				<td class="text-muted small">${frappe.utils.escape_html(r.error || "")}</td></tr>`
		)
		.join("");
	frappe.msgprint({
		title: __("Conversion report for {0}", [message.period]),
		message: `<table class="table table-bordered"><thead><tr><th>${__(
			"Recipient"
		)}</th><th>${__("Number")}</th><th>${__(
			"Status"
		)}</th><th></th></tr></thead><tbody>${rows}</tbody></table>`,
		wide: true,
	});
}
