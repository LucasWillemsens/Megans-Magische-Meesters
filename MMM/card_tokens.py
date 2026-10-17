import hashlib

from .models import GameCard

CARD_TOKEN_SALT = "MMM board card presentation token"
CARD_TOKEN_KEY_PREFIX = "c"


def card_token(game_id, card_db_id):
    digest = hashlib.blake2b(
        f"{CARD_TOKEN_SALT}:{game_id}:{card_db_id}".encode("utf-8"),
        digest_size=8,
    ).hexdigest()
    return f"{CARD_TOKEN_KEY_PREFIX}{digest}"


def play_card_token_index(game_id):
    """Map every presentation token of the game to (card id, owner participant id)."""
    game_cards = GameCard.objects.filter(game_id=game_id).values_list("id", "user_id")
    return {
        card_token(game_id, card_id): (card_id, participant_id)
        for card_id, participant_id in game_cards
    }


def timeline_card_tokens(timeline_steps, game_id):
    """Rewrite played card references of timeline steps into presentation tokens."""
    client_steps = []
    for step in timeline_steps:
        affected_cards = [
            {**card_effect, "cardId": card_token(game_id, card_effect["cardId"])}
            for card_effect in step.get("affectedCards", [])
        ]
        client_steps.append({**step, "affectedCards": affected_cards})
    return client_steps
