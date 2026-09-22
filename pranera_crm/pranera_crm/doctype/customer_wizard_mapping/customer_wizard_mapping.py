# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

# target_fieldname values that don't need to exist as a plain field on target_doctype
# because the resolver special-cases them (see pranera_crm/customer_wizard.py).
SPECIAL_TARGETS = {("Customer", "sales_team")}


class CustomerWizardMapping(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from pranera_crm.pranera_crm.doctype.customer_wizard_mapping_option.customer_wizard_mapping_option import (
			CustomerWizardMappingOption,
		)

		depends_on_option: DF.Data | None
		depends_on_operator: DF.Literal["Is", "Is not"]
		depends_on_question: DF.Link | None
		enabled: DF.Check
		fallback_value: DF.Data | None
		is_mandatory: DF.Check
		label: DF.Data
		options: DF.Table[CustomerWizardMappingOption]
		override_roles: DF.SmallText | None
		question_key: DF.Data
		question_type: DF.Literal["Fixed", "Dynamic"]
		scope: DF.Literal["Organization", "Contact"]
		sequence: DF.Int
		source_doctype: DF.Link | None
		source_filters: DF.Code | None
		source_label_field: DF.Data | None
		target_doctype: DF.Literal["Customer", "Address", "Contact"]
		target_fieldname: DF.Data
	# end: auto-generated types

	def validate(self):
		self.validate_target_field()
		self.validate_options()
		self.validate_dynamic_source()
		self.validate_branching()
		self.validate_override_roles()

	def validate_target_field(self):
		if (self.target_doctype, self.target_fieldname) in SPECIAL_TARGETS:
			return
		field = frappe.get_meta(self.target_doctype).get_field(self.target_fieldname)
		if not field:
			frappe.throw(
				_("{0} has no field {1}").format(self.target_doctype, frappe.bold(self.target_fieldname)),
				title=_("Unknown Target Field"),
			)
		if field.fieldtype in ("Table", "Table MultiSelect"):
			frappe.throw(
				_("{0}.{1} is a table field and can't be set directly; only \"sales_team\" on Customer is supported.").format(
					self.target_doctype, self.target_fieldname
				)
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

	def validate_dynamic_source(self):
		if self.question_type != "Dynamic":
			self.source_doctype = None
			self.source_filters = None
			return
		if not self.source_doctype:
			frappe.throw(_("Source Doctype is required for a Dynamic question."))
		if not frappe.get_meta(self.source_doctype).get_field(self.source_label_field or "name") and (
			self.source_label_field or "name"
		) != "name":
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
			frappe.throw(_("Match must be \"Is\" or \"Is not\"."))

		parent = frappe.get_cached_doc("Customer Wizard Mapping", self.depends_on_question)
		if parent.scope != self.scope:
			frappe.throw(
				_("{0} applies to {1}, but this question applies to {2}. A question can only depend on one in the same step.").format(
					frappe.bold(self.depends_on_question), parent.scope, self.scope
				)
			)

		# guard against a dependency cycle
		seen = {self.name}
		node = parent
		while node.depends_on_question:
			if node.depends_on_question in seen:
				frappe.throw(_("Circular dependency in \"Only After Question\"."))
			seen.add(node.name)
			node = frappe.get_cached_doc("Customer Wizard Mapping", node.depends_on_question)

	def validate_override_roles(self):
		roles = [r.strip() for r in (self.override_roles or "").splitlines() if r.strip()]
		unknown = [r for r in roles if not frappe.db.exists("Role", r)]
		if unknown:
			frappe.throw(_("Unknown role(s): {0}").format(", ".join(unknown)))
		self.override_roles = "\n".join(roles)

	def get_override_roles(self) -> list[str]:
		return [r for r in (self.override_roles or "").splitlines() if r]
