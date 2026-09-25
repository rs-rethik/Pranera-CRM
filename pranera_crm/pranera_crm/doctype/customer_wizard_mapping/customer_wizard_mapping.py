# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

SPECIAL_TARGETS = {("Customer", "sales_team")}
TARGET_DOCTYPES = ("Customer", "Address", "Contact", "CRM Lead")
NON_TARGET_FIELDTYPES = (
	"Section Break",
	"Column Break",
	"Tab Break",
	"Table",
	"Table MultiSelect",
	"HTML",
	"Button",
	"Image",
	"Heading",
	"Fold",
)


class CustomerWizardMapping(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from pranera_crm.pranera_crm.doctype.customer_wizard_mapping_option.customer_wizard_mapping_option import (
			CustomerWizardMappingOption,
		)
		from pranera_crm.pranera_crm.doctype.customer_wizard_mapping_role.customer_wizard_mapping_role import (
			CustomerWizardMappingRole,
		)

		depends_on_option: DF.Data | None
		depends_on_operator: DF.Literal["Is", "Is not"]
		depends_on_question: DF.Link | None
		enabled: DF.Check
		fallback_value: DF.Data | None
		is_mandatory: DF.Check
		label: DF.Data
		options: DF.Table[CustomerWizardMappingOption]
		override_roles: DF.TableMultiSelect[CustomerWizardMappingRole]
		question_key: DF.Data
		question_type: DF.Literal["Fixed", "Dynamic"]
		requires_erpnext_bridge: DF.Check
		scope: DF.Literal["Organization", "Contact"]
		secondary_target_doctype: DF.Link | None
		secondary_target_fieldname: DF.Autocomplete | None
		sequence: DF.Int
		source_doctype: DF.Link | None
		source_filters: DF.Code | None
		source_label_field: DF.Data | None
		target_doctype: DF.Link
		target_fieldname: DF.Autocomplete
	# end: auto-generated types

	def validate(self):
		self.validate_target_field()
		self.validate_secondary_target()
		self.validate_options()
		self.validate_mapped_master_values()
		self.validate_dynamic_source()
		self.validate_branching()
		self.validate_override_roles()

	def validate_target_field(self):
		self._validate_field_target(self.target_doctype, self.target_fieldname)

	def validate_secondary_target(self):
		if not self.secondary_target_doctype and not self.secondary_target_fieldname:
			return
		if not self.secondary_target_doctype or not self.secondary_target_fieldname:
			frappe.throw(_("Set both Secondary Target Doctype and Secondary Target Fieldname, or neither."))
		self._validate_field_target(self.secondary_target_doctype, self.secondary_target_fieldname)

	def _validate_field_target(self, doctype, fieldname):
		if doctype not in TARGET_DOCTYPES:
			frappe.throw(
				_("Target Doctype must be one of: {0}").format(", ".join(TARGET_DOCTYPES)),
				title=_("Unsupported Doctype"),
			)
		if (doctype, fieldname) in SPECIAL_TARGETS:
			return
		field = frappe.get_meta(doctype).get_field(fieldname)
		if not field:
			frappe.throw(
				_("{0} has no field {1}").format(doctype, frappe.bold(fieldname)),
				title=_("Unknown Target Field"),
			)
		if field.fieldtype in ("Table", "Table MultiSelect"):
			frappe.throw(
				_(
					'{0}.{1} is a table field and can\'t be set directly; only "sales_team" on Customer is supported.'
				).format(doctype, fieldname)
			)

	def validate_options(self):
		if self.question_type != "Fixed":
			self.options = []
			return
		if not self.options:
			frappe.throw(_("Add at least one answer, or switch Question Type to Dynamic."))

		seen = set()
		defaults = 0
		for row in self.options:
			if row.option_value in seen:
				frappe.throw(
					_("Duplicate answer key {0} in row {1}").format(frappe.bold(row.option_value), row.idx)
				)
			seen.add(row.option_value)
			defaults += cint(row.is_default)
		if defaults > 1:
			frappe.throw(_("Only one answer can be the default."))

	def validate_mapped_master_values(self):
		"""A Fixed question's mapped_value/fallback_value are static config — a Link
		pointed at a since-deleted record, or a Select value that isn't one of the
		field's configured options, should never make it into a saved row. Caught
		here instead of at submit time, where a Customer target only surfaces as an
		unfixable customer_error and a CRM Lead target aborts the whole convert
		before the Deal even exists."""
		if self.question_type != "Fixed":
			return
		self._validate_mapped_values(
			self.target_doctype, self.target_fieldname, "mapped_value", check_fallback=True
		)
		if self.secondary_target_doctype:
			self._validate_mapped_values(
				self.secondary_target_doctype, self.secondary_target_fieldname, "secondary_mapped_value"
			)

	def _validate_mapped_values(self, doctype, fieldname, option_fieldname, *, check_fallback=False):
		if (doctype, fieldname) in SPECIAL_TARGETS:
			return
		field = frappe.get_meta(doctype).get_field(fieldname)
		if not field or field.fieldtype not in ("Link", "Select"):
			return

		values = {row.get(option_fieldname) for row in self.options if row.get(option_fieldname)}
		if check_fallback and self.fallback_value:
			values.add(self.fallback_value)

		if field.fieldtype == "Link":
			for value in values:
				if not frappe.db.exists(field.options, value):
					frappe.throw(
						_("{0}.{1}: {2} is not a valid {3}").format(
							doctype, fieldname, frappe.bold(value), field.options
						),
						title=_("Unknown Master Record"),
					)
		else:  # Select
			allowed = set((field.options or "").splitlines())
			for value in values:
				if value not in allowed:
					frappe.throw(
						_("{0}.{1}: {2} is not one of its allowed values").format(
							doctype, fieldname, frappe.bold(value)
						),
						title=_("Invalid Select Value"),
					)

	def validate_dynamic_source(self):
		if self.question_type != "Dynamic":
			self.source_doctype = None
			self.source_filters = None
			return
		if not self.source_doctype:
			frappe.throw(_("Source Doctype is required for a Dynamic question."))
		if (
			not frappe.get_meta(self.source_doctype).get_field(self.source_label_field or "name")
			and (self.source_label_field or "name") != "name"
		):
			frappe.throw(
				_("{0} has no field {1}").format(self.source_doctype, frappe.bold(self.source_label_field))
			)
		if self.source_filters:
			try:
				json.loads(self.source_filters)
			except ValueError:
				frappe.throw(_("Filters (JSON) is not valid JSON."))

	def validate_branching(self):
		if not self.depends_on_question:
			self.depends_on_option = None
			self.depends_on_operator = None
			return
		if self.depends_on_question == self.name:
			frappe.throw(_("A question can't depend on itself."))
		if not self.depends_on_option:
			frappe.throw(_("Only When Answer Is is required when Only After Question is set."))
		if self.depends_on_operator not in (None, "Is", "Is not"):
			frappe.throw(_('Match must be "Is" or "Is not".'))

		parent = frappe.get_cached_doc("Customer Wizard Mapping", self.depends_on_question)
		if parent.scope != self.scope:
			frappe.throw(
				_(
					"{0} applies to {1}, but this question applies to {2}. A question can only depend on one in the same step."
				).format(frappe.bold(self.depends_on_question), parent.scope, self.scope)
			)

		seen = {self.name}
		node = parent
		while node.depends_on_question:
			if node.depends_on_question in seen:
				frappe.throw(_('Circular dependency in "Only After Question".'))
			seen.add(node.name)
			node = frappe.get_cached_doc("Customer Wizard Mapping", node.depends_on_question)

	def validate_override_roles(self):
		seen = set()
		self.override_roles = [r for r in self.override_roles if not (r.role in seen or seen.add(r.role))]

	def get_override_roles(self) -> list[str]:
		return [r.role for r in self.override_roles if r.role]


@frappe.whitelist()
def get_target_fields(doctype: str) -> list[dict]:
	"""Fields of ``doctype`` an answer can be saved on, for the form's field picker."""
	if not frappe.has_permission("Customer Wizard Mapping", "read"):
		frappe.throw(_("Not allowed"), frappe.PermissionError)
	if doctype not in TARGET_DOCTYPES:
		frappe.throw(_("Target Doctype must be one of: {0}").format(", ".join(TARGET_DOCTYPES)))

	fields = [
		{"value": df.fieldname, "label": f"{_(df.label or df.fieldname)} ({df.fieldname})"}
		for df in frappe.get_meta(doctype).fields
		if df.fieldtype not in NON_TARGET_FIELDTYPES and not df.hidden
	]
	if doctype == "Customer":
		fields.append({"value": "sales_team", "label": _("Sales Team - for a Sales Person question")})
	return fields
