"""Server-side account authorization: which authenticated account is the
designated admin, and which player an authenticated account plays as.

Only an account whose email address was verified by the sign-in provider is
eligible; accounts without a verified address matching the configured admin
email are denied, so a merely asserted or changed user email never opens the
admin pages.
"""

from django.conf import settings

from allauth.account.models import EmailAddress

from .models import Player


def linked_player(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return Player.objects.filter(account=user).first()


def is_admin_account(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return (
        EmailAddress.objects
        .filter(user=user, verified=True, email__iexact=settings.ADMIN_EMAIL)
        .exists()
    )
