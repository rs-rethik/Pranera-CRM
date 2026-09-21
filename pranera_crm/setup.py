from pranera_crm.settings import ensure_default


def after_install():
	ensure_default()


def after_migrate():
	ensure_default()
