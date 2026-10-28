from pranera_crm import lost_reasons


def execute():
	"""Lead reasons on leads, deal reasons on deals: tag the agreed lost reasons, adding the missing."""
	lost_reasons.seed()
