"""The Deal Dashboard shown inside CRM (crm_sidebar_ext.js opens /deal_wizard/dashboard).

Deals are read with frappe.get_list, so CRM's own permission rule decides which deals
count. Customers and Sales Orders are limited to the user's Sales Person and the ones
below it in the Sales Person tree (scope.py). Nothing here skips permissions.
"""
