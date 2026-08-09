"""
Management command to add or refresh all 52 cards from a standard playing-card
deck in Lucas' collection.  These cards use the CSS-playing-card renderer.

Usage:
    python manage.py add_deck_cards
"""

from django.core.management.base import BaseCommand
from MMM.models import Player, Card, CardOwnerHistory


RANK_NAMES = [
    "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Jack", "Queen", "King", "Ace",
]

# Suit names indexed by cardType:
#   0=Intelligence(Clubs), 1=Speed(Spades), 2=Viciousness(Diamonds), 3=Resolve(Hearts)
SUIT_NAMES = ["Clubs", "Spades", "Diamonds", "Hearts"]
STATIC_ART_SOURCE = "static"


class Command(BaseCommand):
    help = "Add or refresh all 52 standard playing cards in Lucas' collection"

    def handle(self, *args, **options):
        # 1. Get or create Lucas
        lucas, created = Player.objects.get_or_create(name="Lucas")
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created player '{lucas.name}'"))
        else:
            self.stdout.write(f"Found player '{lucas.name}' (id={lucas.id})")

        # 2. Create owner-history record for Lucas
        owner_history, hist_created = CardOwnerHistory.objects.get_or_create(
            cardOwner=lucas,
            defaults={"cardOwner": lucas},
        )
        if hist_created:
            owner_history.save()
            self.stdout.write(self.style.SUCCESS("Created CardOwnerHistory for Lucas"))
        else:
            self.stdout.write("CardOwnerHistory already exists for Lucas")

        # 3. Create or refresh 52 cards (13 ranks × 4 suits).  Matching cards
        # are updated so this command also migrates cards created by the old
        # version, which stored an empty artSource.
        created_count = 0
        updated_count = 0

        for suit_idx in range(4):          # Clubs, Spades, Diamonds, Hearts
            for rank_idx in range(13):     # Two through Ace
                title = f"{RANK_NAMES[rank_idx]} of {SUIT_NAMES[suit_idx]}"
                existing_cards = Card.objects.filter(
                    ownerHistory=owner_history,
                    title=title,
                )
                if existing_cards.exists():
                    changed = existing_cards.update(
                        artSource=STATIC_ART_SOURCE,
                        cardType=suit_idx,
                    )
                    updated_count += changed
                    self.stdout.write(f"  Updated: {title}")
                    continue

                card = Card.objects.create(
                    title=title,
                    artSource=STATIC_ART_SOURCE,
                    cardType=suit_idx,
                )
                card.ownerHistory.add(owner_history)
                created_count += 1
                self.stdout.write(f"  Created: {title}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created {created_count} new card(s), updated {updated_count}."
        ))
