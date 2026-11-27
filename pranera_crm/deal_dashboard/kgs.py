import frappe
from frappe.utils import flt

KG_UOMS = {"kg", "kgs", "kilogram", "kilograms"}


def is_kg(uom: str | None) -> bool:
	return (uom or "").strip().lower() in KG_UOMS


class KgsConverter:
	"""Quantity lines in kilograms, from their UOM or their item's stock UOM.

	A line in Pcs or another unit becomes kilograms only through the item's UOM
	Conversion Detail to Kg; without one it stays out (convert() returns None).
	"""

	def __init__(self, items: set[str]):
		items = {item for item in items if item}
		self.stock_uom = (
			dict(
				frappe.get_all(
					"Item", filters={"name": ["in", list(items)]}, fields=["name", "stock_uom"], as_list=True
				)
			)
			if items
			else {}
		)
		self.kg_factor = self._kg_factors(items)

	def convert(self, qty: float, uom: str | None, item: str | None) -> float | None:
		uom = uom or self.stock_uom.get(item)
		if is_kg(uom):
			return flt(qty)
		factor = self.kg_factor.get(item)
		if factor and uom == self.stock_uom.get(item):
			# one Kg is `factor` stock units
			return flt(qty) / factor
		return None

	def _kg_factors(self, items: set[str]) -> dict[str, float]:
		if not items:
			return {}
		rows = frappe.get_all(
			"UOM Conversion Detail",
			filters={"parenttype": "Item", "parent": ["in", list(items)], "conversion_factor": [">", 0]},
			fields=["parent", "uom", "conversion_factor"],
		)
		return {row.parent: flt(row.conversion_factor) for row in rows if is_kg(row.uom)}


# the product line fields on CRM Deal; the item and UOM ones are Pranera's custom fields
LINE_FIELDS = {
	"uom": "custom_uom",
	"item": "custom_item_code",
	"product": "product_code",
}


def line_fields() -> list[str]:
	"""get_list fields for a deal's product lines, grouped with sum(qty) as qty."""
	meta = frappe.get_meta("CRM Products")
	fields = [
		f"`tabCRM Products`.`{field}` as {alias}"
		for alias, field in LINE_FIELDS.items()
		if alias == "product" or meta.has_field(field)
	]
	return [*fields, "sum(`tabCRM Products`.qty) as qty", "count(`tabCRM Products`.name) as line_count"]


def line_group_by() -> str:
	meta = frappe.get_meta("CRM Products")
	return ", ".join(
		f"`tabCRM Products`.`{field}`"
		for alias, field in LINE_FIELDS.items()
		if alias == "product" or meta.has_field(field)
	)


class DealLineKgs:
	"""Kilograms of grouped deal product lines (rows with uom, item, product, qty)."""

	def __init__(self, rows: list[dict]):
		products = {row.get("product") for row in rows if row.get("product") and not row.get("item")}
		self.product_item = _product_items(products)
		self.converter = KgsConverter({self.item(row) for row in rows})

	def item(self, row: dict) -> str | None:
		return row.get("item") or self.product_item.get(row.get("product"))

	def kgs(self, row: dict) -> float | None:
		"""None for a line that is not in kilograms, 0 for a deal without lines."""
		if row.get("qty") is None:
			return 0.0
		return self.converter.convert(row["qty"], row.get("uom"), self.item(row))


def _product_items(products: set[str]) -> dict[str, str]:
	if not products:
		return {}
	meta = frappe.get_meta("CRM Product")
	fields = ["name", "erpnext_item_code"]
	if meta.has_field("custom_item_code"):
		fields.append("custom_item_code")
	rows = frappe.get_all("CRM Product", filters={"name": ["in", list(products)]}, fields=fields)
	return {
		row.name: row.get("custom_item_code") or row.erpnext_item_code
		for row in rows
		if row.get("custom_item_code") or row.erpnext_item_code
	}
