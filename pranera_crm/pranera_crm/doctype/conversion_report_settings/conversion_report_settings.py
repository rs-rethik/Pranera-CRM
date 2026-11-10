import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class ConversionReportSettings(Document):
	def validate(self):
		self.month_day = min(max(cint(self.month_day) or 1, 1), 28)
		if (
			self.template
			and frappe.db.get_value("WhatsApp Templates", self.template, "header_type") != "DOCUMENT"
		):
			frappe.throw(_("Choose a WhatsApp template with a Document header: the PDF is sent in it."))
		if self.enabled and not (self.template and any(r.enabled for r in self.recipients)):
			frappe.throw(_("Choose a template and add a recipient before turning on Send Automatically."))
