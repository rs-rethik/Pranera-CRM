"""Serve the PWA service worker from inside the wizard's own URL scope.

A service worker can only control the path it is served from (or a sub-path)
unless the response carries ``Service-Worker-Allowed``. The built worker lives
under ``/assets/pranera_crm/frontend/``, which cannot control ``/deal_wizard/``.
Rather than requiring an nginx rule, we serve the very same file at
``/deal_wizard/sw.js`` (default scope ``/deal_wizard/``) and also send the
header, so it works on a bare ``bench serve`` and in production alike.

hooks.py maps ``/deal_wizard/sw.js`` to the ``deal_wizard_sw`` endpoint;
Frappe hands page renderers that *resolved* endpoint, not the raw URL.
"""

import os

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

ENDPOINT = "deal_wizard_sw"
SCOPE = "/deal_wizard/"


class ServiceWorkerRenderer(BaseRenderer):
	def __init__(self, path=None, http_status_code=None):
		super().__init__(path=path, http_status_code=http_status_code)
		self.file_path = frappe.get_app_path("pranera_crm", "public", "frontend", "sw.js")

	def can_render(self):
		return self.path == ENDPOINT and os.path.isfile(self.file_path)

	def render(self):
		with open(self.file_path, "rb") as f:
			response = Response(f.read())

		response.mimetype = "text/javascript"
		response.headers["Service-Worker-Allowed"] = SCOPE
		response.headers["Cache-Control"] = "no-cache, must-revalidate"
		return response
