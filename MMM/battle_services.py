import json
import random
from urllib.parse import unquote

from .card_tokens import play_card_token_index
from .models import (
    BattleHistory,
    BattleParticipant,
    CardState,
    Deck,
    Game,
    GameCard,
)

DECK_BLOCK_SIZE = 32
HAND_FAN_SIZE = 9


def reset_games():
    games_removed = Game.objects.count()
    Game.objects.all().delete()
    BattleHistory.objects.all().delete()
    BattleParticipant.objects.all().delete()
    GameCard.objects.all().delete()
    CardState.objects.all().delete()
    Deck.objects.all().delete()
    return games_removed


def ensure_game_initialized(game):
    for participant in game.history.participants.all():
        participant.startWithDeckInRandomOrder(initializeStartingCard=True)
    if game.roundNumber < 1:
        game.roundNumber = 1
        game.save(update_fields=["roundNumber"])


def game_outcome(game, force_end=False):
    participants = list(game.history.participants.all())
    if not participants:
        return False, False, None

    active_participants = [p for p in participants if not p.defeated and not p.fled]
    if len(active_participants) == 1:
        others = [other for other in participants if other.fled]
        return True, len(others) < len(participants) - 1, active_participants
    elif len(active_participants) > 1:
        return force_end, True, active_participants
    else:
        return True, True, None


def parse_play_cookie_payload(cookie_value):
    decoded_value = unquote(cookie_value or "")
    if decoded_value.startswith("{"):
        try:
            payload = json.loads(decoded_value)
        except json.JSONDecodeError:
            payload = {}
        return {
            "laneValue": int(payload.get("laneValue", 0)),
            "sourceLane": int(payload["sourceLane"]) if payload.get("sourceLane") is not None else None,
            "sourceOrdinal": int(payload["sourceOrdinal"]) if payload.get("sourceOrdinal") is not None else None,
            "flipFaceUp": bool(payload.get("flipFaceUp", False)),
        }

    flip_face_up = decoded_value.endswith("f")
    lane_value = decoded_value[:-1] if flip_face_up else decoded_value
    return {
        "laneValue": int(lane_value or 0),
        "sourceLane": None,
        "sourceOrdinal": None,
        "flipFaceUp": flip_face_up,
    }


def cookie_staged_plays(cookies, game):
    """Resolve staged play cookies by presentation token into game card payloads."""
    token_index = play_card_token_index(game.id)
    staged_plays = {}
    for cookie_name, cookie_value in cookies.items():
        if cookie_name not in token_index:
            continue
        card_id, _participant_id = token_index[cookie_name]
        staged_plays[str(card_id)] = parse_play_cookie_payload(cookie_value)
    return staged_plays


def consume_staged_plays(game, staged_plays, participant):
    for card_key, payload in staged_plays.items():
        try:
            card_id = int(card_key)
        except (TypeError, ValueError):
            continue
        if not GameCard.objects.filter(pk=card_id, game_id=game.id, user_id=participant.id).exists():
            continue
        participant.playCard(
            card_id,
            int(payload["laneValue"]),
            payload["flipFaceUp"],
            sourceLane=payload["sourceLane"],
            sourceOrdinal=payload["sourceOrdinal"],
        )


def perform_board_action(game, participant, action_name, staged_plays):
    """Consume the staged plays, then execute one supported board action."""
    error_message = ""
    action_plays = []
    timeline_steps = []
    try:
        consume_staged_plays(game, staged_plays, participant)
        if action_name == "draw":
            action_plays, timeline_steps, error_message = resolve_draw(participant)
        elif action_name == "end_turn":
            participant.resetTurn()
        elif action_name == "play":
            pass
        else:
            error_message = "Unknown action."
    except Exception as action_error:
        error_message = str(action_error)
    return action_plays, timeline_steps, error_message


def resolve_draw(participant):
    next_deck_card = participant.getNextDeckCard()
    source_lane = next_deck_card.state.lane if next_deck_card else None
    source_ordinal = next_deck_card.state.laneOrdinal if next_deck_card else None
    drawn_card = participant.drawCard()
    action_plays = []
    timeline_steps = []
    if drawn_card is None:
        return action_plays, timeline_steps, f"No cards left in {participant}'s deck."

    action_plays.append({
        "cardId": str(drawn_card.id),
        "participantId": participant.id,
        "laneValue": 0,
        "sourceLane": source_lane,
        "sourceOrdinal": source_ordinal,
        "flipFaceUp": False,
    })
    if participant.getNextDeckCard() is None:
        timeline_steps = []
        run_specials(participant, timeline_steps)
        from MMM.special_timeline import build_shuffle_step
        timeline_steps.extend(build_shuffle_step(participant))
        participant.shuffleBoard()
        participant.resetTurn()
    return action_plays, timeline_steps, ""


def run_specials(participant, timeline=None):
    int_count, spd_count, vis_count, res_count, tactics, power, influence = participant.getStats()
    response = ""
    game = participant.getGame()
    if int_count >= spd_count and int_count >= vis_count and int_count >= res_count:
        run_int_special(participant, int_count, timeline)
        if game_outcome(game)[0]:
            return

    int_count, spd_count, vis_count, res_count, tactics, power, influence = participant.getStats()

    if spd_count >= int_count and spd_count >= vis_count and spd_count >= res_count:
        response = run_spd_special(participant, spd_count, power, timeline=timeline)
        if game_outcome(game)[0]:
            return

    if response == "" and vis_count >= int_count and vis_count >= spd_count and vis_count >= res_count:
        response = run_vis_special(participant, vis_count, timeline=timeline)
        if game_outcome(game)[0]:
            return

    if response == "" and res_count >= int_count and res_count >= spd_count and res_count >= vis_count:
        run_res_special(participant, res_count, timeline)


def run_int_special(participant, count, timeline=None):
    from MMM.special_timeline import build_int_timeline
    print(f"{participant.player.name} enacts master plan (max {count} cards)")
    hand_cards = list(GameCard.objects.filter(game_id=participant.getGame().id, user_id=participant.id, state__lane=0))
    random.shuffle(hand_cards)
    chosen = hand_cards[:min(count, len(hand_cards))]
    chosen_ids = [card.id for card in chosen]
    for card in chosen:
        participant.playCard(card.id, flipFaceUp=True, specialClause=True)
    if timeline is not None:
        build_int_timeline(participant, count, timeline, card_ids=chosen_ids)


def run_spd_special(participant, speed, power, opponent_id=None, timeline=None):
    from MMM.special_timeline import build_spd_timeline
    opponent = participant.getGame().history.participants.exclude(id=participant.id).filter(defeated=False, fled=False).first()
    if opponent_id is not None:
        opponent = participant.getGame().history.participants.get(id=opponent_id)
    if opponent is None:
        return ""
    opponent_int, opponent_spd, opponent_vis, opponent_res, opponent_tactics, opponent_power, opponent_influence = opponent.getStats()

    if opponent_power < power:
        print(f"{participant.player.name} rushes down {opponent.player.name}")
        if timeline is not None:
            build_spd_timeline(participant, speed, power, opponent, timeline)
        else:
            run_specials(opponent)
        run_specials(opponent, timeline)
    else:
        if opponent_spd < speed:
            print(f"{participant.player.name} flees from {opponent.player.name} and steals a card")
            participant.flee()
            if timeline is not None:
                build_spd_timeline(participant, speed, power, opponent, timeline)
            return f"{participant.id} fled from {opponent.id}"
        else:
            print(f"{participant.player.name} fails to flee from {opponent.player.name}")
            if timeline is not None:
                build_spd_timeline(participant, speed, power, opponent, timeline)
    return ""


def run_vis_special(participant, viciousness, opponent_id=None, timeline=None):
    from MMM.special_timeline import build_vis_timeline
    opponent = participant.getGame().history.participants.exclude(id=participant.id).filter(defeated=False, fled=False).first()
    if opponent_id is not None:
        opponent = participant.getGame().history.participants.get(id=opponent_id)
    if opponent is None:
        return ""
    opponent_int, opponent_spd, opponent_vis, opponent_res, opponent_tactics, opponent_power, opponent_influence = opponent.getStats()

    new_trusted_res_card = None
    new_trusted_res_cards = get_trustable_cards(participant, [4])
    if len(new_trusted_res_cards) > 0:
        new_trusted_res_card = new_trusted_res_cards[0]
    outcome = None
    if new_trusted_res_card is None:
        response = f"{participant.player.name} drains the last of their resolve and is defeated"
        outcome = "drain"
        print(response)
        participant.defeated = True
        participant.save()
    elif opponent_res < viciousness:
        response = f"{participant.player.name} attacks and defeats {opponent.player.name} ({viciousness} > {opponent_res})"
        outcome = "win"
        print(response)
        opponent.defeated = True
        opponent.save()
    else:
        response = f"{participant.player.name} attacks {opponent.player.name} unsuccesfully ({viciousness} <= {opponent_res})"
        outcome = "fail"
        print(response)
        response = ""
    if new_trusted_res_card is not None:
        new_trusted_res_card.state.trust()
        new_trusted_res_card.state.save()
    if timeline is not None:
        build_vis_timeline(participant, viciousness, opponent, timeline, outcome, new_trusted_res_card)
    return response


def run_res_special(participant, count, timeline=None):
    from MMM.special_timeline import build_res_timeline
    print(f"{participant.player.name} holds and trusts up to {count} cards")
    new_cards = get_trustable_cards(participant)
    chosen_ids = []
    if new_cards:
        random.shuffle(new_cards)
        chosen = new_cards[:min(count, len(new_cards))]
        chosen_ids = [card.id for card in chosen]
        for new_card in chosen:
            new_card.state.trust()
            new_card.state.save()
    if timeline is not None:
        build_res_timeline(participant, count, timeline, card_ids=chosen_ids)


def get_trustable_cards(participant, lane_numbers=(1, 2, 3, 4)):
    trustable_cards = []
    for lane_number in lane_numbers:
        lane_cards = GameCard.objects.filter(game_id=participant.getGame().id, user_id=participant.id, state__lane=lane_number, state__trusted=False, state__faceDown=False).order_by("state__laneOrdinal")
        trustable_cards += lane_cards
    return trustable_cards


def run_bot_turn(game, human_player_id):
    bot_participants = game.history.participants.exclude(player_id=human_player_id).filter(computerControlled=True)
    bot_actions = []
    bot_timelines = []
    for bot_participant in bot_participants:
        hand_card = (
            GameCard.objects.filter(game_id=game.id, user_id=bot_participant.id, state__lane=0)
            .select_related("card")
            .first()
        )
        if hand_card is None:
            next_deck_card = bot_participant.getNextDeckCard()
            if bot_participant.drawCard() is not None:
                if bot_participant.getNextDeckCard() is None:
                    timeline = []
                    run_specials(bot_participant, timeline)
                    from MMM.special_timeline import build_shuffle_step
                    timeline.extend(build_shuffle_step(bot_participant))
                    bot_participant.shuffleBoard()
                    if timeline:
                        bot_timelines.extend(timeline)
                else:
                    bot_actions.append(
                        {
                            "participantId": bot_participant.id,
                            "playerId": bot_participant.player_id,
                            "cardId": next_deck_card.id,
                            "laneValue": 0,
                            "sourceLane": next_deck_card.state.lane,
                            "sourceOrdinal": next_deck_card.state.laneOrdinal,
                            "flipFaceUp": False,
                        }
                    )
            hand_card = (
                GameCard.objects.filter(game_id=game.id, user_id=bot_participant.id, state__lane=0)
                .select_related("card")
                .first()
            )
        if hand_card is not None:
            source_lane = hand_card.state.lane
            source_ordinal = hand_card.state.laneOrdinal
            played_card = bot_participant.playCard(hand_card.id, flipFaceUp=True)
            bot_actions.append(
                {
                    "participantId": bot_participant.id,
                    "playerId": bot_participant.player_id,
                    "cardId": played_card.id,
                    "laneValue": played_card.state.lane,
                    "sourceLane": source_lane,
                    "sourceOrdinal": source_ordinal,
                    "flipFaceUp": not played_card.state.faceDown,
                }
            )
        bot_participant.resetTurn()
    return bot_actions, bot_timelines


def _ordered_lane_cards(cards):
    return sorted(cards, key=lambda card: (card.state.laneOrdinal, card.id))


def _deck_stack_key(card):
    return card.state.lane, -card.id


def _next_deck_card_from_cards(deck_cards):
    return min(deck_cards, key=lambda card: (-card.state.lane, card.id), default=None)


def _deck_presentation(deck_cards, next_deck_card=None):
    ordered_deck_cards = sorted(deck_cards, key=_deck_stack_key)
    active_card_count = (
        ((len(ordered_deck_cards) - 1) % DECK_BLOCK_SIZE) + 1
        if ordered_deck_cards
        else 0
    )
    active_stack = ordered_deck_cards[-active_card_count:] if active_card_count else []
    inert_block_count = (
        len(ordered_deck_cards) - active_card_count
    ) // DECK_BLOCK_SIZE

    deck_card_ids = {card.id for card in ordered_deck_cards}
    if next_deck_card is None or next_deck_card.id not in deck_card_ids:
        next_deck_card = _next_deck_card_from_cards(ordered_deck_cards)
    if next_deck_card is not None:
        active_card_ids = {card.id for card in active_stack}
        if next_deck_card.id not in active_card_ids:
            active_stack = active_stack[1:] + [next_deck_card]
        elif active_stack[-1].id != next_deck_card.id:
            active_stack = [
                card for card in active_stack if card.id != next_deck_card.id
            ] + [next_deck_card]

    deck_indicators = [
        {"cardCount": DECK_BLOCK_SIZE} for _ in range(inert_block_count)
    ]
    return active_stack, deck_indicators


def chunk_hand_cards(hand_cards):
    ordered_cards = list(hand_cards)
    return [
        ordered_cards[index:index + HAND_FAN_SIZE]
        for index in range(0, len(ordered_cards), HAND_FAN_SIZE)
    ] or [[]]


def context_board(game_cards, participant_id):
    user_cards = [gameCard for gameCard in game_cards if gameCard.user_id == participant_id]
    hand_cards = [gameCard for gameCard in user_cards if gameCard.state.lane == 0]
    intelligence_cards = [gameCard for gameCard in user_cards if gameCard.state.lane == 1]
    speed_cards = [gameCard for gameCard in user_cards if gameCard.state.lane == 2]
    visciousness_cards = [gameCard for gameCard in user_cards if gameCard.state.lane == 3]
    resolve_cards = [gameCard for gameCard in user_cards if gameCard.state.lane == 4]
    deck_cards = [gameCard for gameCard in user_cards if gameCard.state.inDeck == True]
    participant = BattleParticipant.objects.filter(pk=participant_id).first()
    next_deck_card = participant.getNextDeckCard() if participant is not None else None
    deck_stack, deck_indicators = _deck_presentation(deck_cards, next_deck_card)

    board = {
        "handCards": hand_cards,
        "handFans": chunk_hand_cards(hand_cards),
        "handCount": len(hand_cards),
        "laneRows": [{"name": "Intelligence", "value": len([revealedCard for revealedCard in intelligence_cards if not revealedCard.state.faceDown]), "cards": _ordered_lane_cards([card for card in intelligence_cards if card.state.trusted == False]), "trustedCards": _ordered_lane_cards([card for card in intelligence_cards if card.state.trusted == True])},
        {"name": "Speed", "value": len([revealedCard for revealedCard in speed_cards if not revealedCard.state.faceDown]), "cards": _ordered_lane_cards([card for card in speed_cards if card.state.trusted == False]), "trustedCards": _ordered_lane_cards([card for card in speed_cards if card.state.trusted == True])},
        {"name": "Visciousness", "value": len([revealedCard for revealedCard in visciousness_cards if not revealedCard.state.faceDown]), "cards": _ordered_lane_cards([card for card in visciousness_cards if card.state.trusted == False]), "trustedCards": _ordered_lane_cards([card for card in visciousness_cards if card.state.trusted == True])},
        {"name": "Resolve", "value": len([revealedCard for revealedCard in resolve_cards if not revealedCard.state.faceDown]), "cards": _ordered_lane_cards([card for card in resolve_cards if card.state.trusted == False]), "trustedCards": _ordered_lane_cards([card for card in resolve_cards if card.state.trusted == True])}],
        "deckCount": len(deck_cards),
        "deckStack": deck_stack,
        "deckIndicators": deck_indicators,
    }
    return board
