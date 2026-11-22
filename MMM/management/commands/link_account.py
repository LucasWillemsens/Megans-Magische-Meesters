"""Management command that links an authenticated account to an existing
MMM player, for the controlled one-time linking of accounts to players.

Usage:
    python3 manage.py link_account <account-email> <player-name>

The account must have signed in at least once (Google sign-in creates it),
and the player must already exist: neither is ever created by this command,
and neither side of the one-to-one link can be taken twice.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from MMM.models import Player


class Command(BaseCommand):
    help = "Link the account that signed in with <account-email> to the existing player <player-name>"

    def add_arguments(self, parser):
        parser.add_argument("email", help="email address of the signed-in account")
        parser.add_argument("player", help="name of the existing player to link it to")

    def handle(self, *args, **options):
        email = options["email"].strip()
        player_name = options["player"].strip()

        users = list(get_user_model().objects.filter(email__iexact=email))
        if not users:
            raise CommandError(
                f"no account with email {email} exists; sign in once with it before linking"
            )
        if len(users) > 1:
            raise CommandError(
                f"multiple accounts share the email {email}; refusing to pick one"
            )
        user = users[0]

        players = list(Player.objects.filter(name__iexact=player_name))
        if not players:
            raise CommandError(
                f"no player named {player_name} exists; this command never creates players"
            )
        if len(players) > 1:
            player_names = ", ".join(player.name for player in players)
            raise CommandError(
                f"multiple players match the name {player_name} ({player_names}); "
                "pass the exact name"
            )
        player = players[0]

        if player.account_id == user.id:
            self.stdout.write(self.style.SUCCESS(
                f"player {player.name} is already linked to {email}"
            ))
            return
        if player.account_id is not None:
            raise CommandError(
                f"player {player.name} is already linked to {player.account.email}"
            )
        other_player = Player.objects.filter(account=user).first()
        if other_player is not None:
            raise CommandError(
                f"{email} is already linked to player {other_player.name}"
            )

        player.account = user
        player.save(update_fields=["account"])
        self.stdout.write(self.style.SUCCESS(
            f"linked player {player.name} to the account {email}"
        ))
