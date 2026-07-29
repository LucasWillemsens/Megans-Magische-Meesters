"""
Management command to add all 52 cards from a standard playing-card deck
to Lucas' collection, without art — exercising the CSS-playing-card fallback.

Usage:
    python manage.py add_deck_cards
"""

from django.core.management.base import BaseCommand
from MMM.models import Player, Card, CardOwnerHistory


# Rank names in order: id%13=0 → "Two", id%13=1 → "Three", ... id%13=12 → "Ace"
RANK_NAMES = [
    "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Jack", "Queen", "King", "Ace",
]

# Suit names indexed by cardType:
#   0=Intelligence(Clubs), 1=Speed(Spades), 2=Viciousness(Diamonds), 3=Resolve(Hearts)
SUIT_NAMES = ["Clubs", "Spades", "Diamonds", "Hearts"]


class Command(BaseCommand):
    help = "Add all 52 standard playing cards to Lucas' collection (no art)"

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

        # 3. Create 52 cards (13 ranks × 4 suits)
        existing_titles = set(
            Card.objects.filter(ownerHistory=owner_history).values_list("title", flat=True)
        )
        created_count = 0
        skipped_count = 0

        for suit_idx in range(4):          # Clubs, Spades, Diamonds, Hearts
            for rank_idx in range(13):     # Two through Ace
                title = f"{RANK_NAMES[rank_idx]} of {SUIT_NAMES[suit_idx]}"
                if title in existing_titles:
                    self.stdout.write(f"  Skipping (exists): {title}")
                    skipped_count += 1
                    continue

                card = Card.objects.create(
                    title=title,
                    artSource="",           # No art → triggers CSS playing card display
                    cardType=suit_idx,
                )
                card.ownerHistory.add(owner_history)
                created_count += 1
                self.stdout.write(f"  Created: {title}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created {created_count} new card(s), skipped {skipped_count} existing."
        ))
