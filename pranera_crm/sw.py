"""Serve the PWA service worker from inside the wizard's own URL scope.

A service worker can only control the path it is served from (or a sub-path)
unless the response carries ``Service-Worker-Allowed``. The built worker lives
under ``/assets/pranera_crm/frontend/``, which cannot control ``/deal_wizard/``.
Rather than requiring an nginx rule, we serve the very same file at
``/deal_wizard/sw.js`` (default scope ``/deal_wizard/``) and still send the
header, so it works on a bare ``bench serve`` and in production alike.
"""

import mimetypes
import os
import re

import frappe
from werkzeug.wrappers import Response

from frappe.website.page_renderers.base_renderer import BaseRenderer

SCOPE = "/deal_wizard/"
URL_PREFIX = "deal_wizard/"

# Only files emitted by vite-plugin-pwa/workbox, never an arbitrary path.
ALLOWED_FILE = re.compile(r"^(sw\.js|workbox-[A-Za-z0-9_-]+\.js)(\.map)?$")


class ServiceWorkerRenderer(BaseRenderer):
	def __init__(self, path=None, http_status_code=None):
		super().__init__(path=path, http_status_code=http_status_code)
		self.file_path = None

		if self.path.startswith(URL_PREFIX):
			filename = self.path[len(URL_PREFIX) :]
			if ALLOWED_FILE.match(filename):
				candidate = frappe.get_app_path("pranera_crm", "public", "frontend", filename)
				if os.path.isfile(candidate):
					self.file_path = candidate

	def can_render(self):
		return bool(self.file_path)

	def render(self):
		with open(self.file_path, "rb") as f:
			data = f.read()

		is_map = self.file_path.endswith(".map")
		response = Response(data)
		response.mimetype = (
			"application/json" if is_map else (mimetypes.guess_type(self.file_path)[0] or "text/javascript")
		)
		response.headers["Service-Worker-Allowed"] = SCOPE
		# the browser must always revalidate the worker script to pick up updates
		response.headers["Cache-Control"] = "no-cache, must-revalidate"
		return response
