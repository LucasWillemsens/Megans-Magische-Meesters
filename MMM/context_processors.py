"""Request context shared by every Jinja2 render: what the request's
authenticated account is allowed to see in the band-site navigation."""

from . import account_access


def band_navigation(request):
    return {
        "isAdminAccount": account_access.is_admin_account(getattr(request, "user", None)),
    }
