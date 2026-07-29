"""
Timeline data structures and builder functions for special draw sequences.
The server records what happens during special execution as a flat, ordered
list of steps, which the client plays sequentially.
"""

from MMM.models import GameCard

# Step kind constants
SPECIAL_TRIGGER = "special-trigger"
CARD_EFFECT = "card-effect"
PARTICIPANT_EFFECT = "participant-effect"
SHUFFLE_BACK = "shuffle-back"


def build_trigger_step(participant, banner, lane, order=0):
    """Build a special-trigger step: banner + lane highlight, no card movement."""
    return {
        "order": order,
        "kind": SPECIAL_TRIGGER,
        "banner": banner,
        "participantId": participant.id,
        "lane": lane,
        "affectedCards": [],
        "defeatedParticipantId": None,
        "fledParticipantId": None,
    }


def build_card_effect_step(participant, affected_cards, order=0):
    """Build a card-effect step: cards fly, flip, or gain trust glow."""
    return {
        "order": order,
        "kind": CARD_EFFECT,
        "banner": "",
        "participantId": participant.id,
        "lane": max((c["destinationLane"] for c in affected_cards), default=None),
        "affectedCards": affected_cards,
        "defeatedParticipantId": None,
        "fledParticipantId": None,
    }


def build_participant_effect_step(participant, banner, defeated_id=None, fled_id=None, order=0):
    """Build a participant-effect step: defeat or flee."""
    return {
        "order": order,
        "kind": PARTICIPANT_EFFECT,
        "banner": banner,
        "participantId": participant.id,
        "lane": None,
        "affectedCards": [],
        "defeatedParticipantId": defeated_id,
        "fledParticipantId": fled_id,
    }


def build_shuffle_step(participant, order=0):
    """Build a shuffle-back step listing all untrusted face-up board cards + hand cards."""
    game = participant.getGame()
    board_cards = GameCard.objects.filter(
        game_id=game.id,
        user_id=participant.id,
        state__trusted=False,
        state__inDeck=False,
        state__faceDown=False,
    )
    hand_cards = GameCard.objects.filter(
        game_id=game.id,
        user_id=participant.id,
        state__lane=0,
    )
    affected = []
    for card in board_cards:
        affected.append({
            "cardId": card.id,
            "sourceLane": card.state.lane,
            "sourceOrdinal": card.state.laneOrdinal,
            "destinationLane": -1,  # -1 means deck
            "destinationOrdinal": 0,
            "flipFaceUp": False,
            "trust": False,
        })
    for card in hand_cards:
        affected.append({
            "cardId": card.id,
            "sourceLane": card.state.lane,
            "sourceOrdinal": card.state.laneOrdinal,
            "destinationLane": -1,
            "destinationOrdinal": 0,
            "flipFaceUp": False,
            "trust": False,
        })
    return [{
        "order": order,
        "kind": SHUFFLE_BACK,
        "banner": "",
        "participantId": participant.id,
        "lane": None,
        "affectedCards": affected,
        "defeatedParticipantId": None,
        "fledParticipantId": None,
    }]


def build_int_timeline(participant, count, timeline):
    """Append intSpecial steps to the timeline."""
    hand_cards = list(GameCard.objects.filter(
        game_id=participant.getGame().id,
        user_id=participant.id,
        state__lane=0,
    ))
    import random
    random.shuffle(hand_cards)
    chosen = hand_cards[:min(count, len(hand_cards))]

    # Trigger step
    banner = f"{participant.player.name} enacts master plan (max {count} cards)"
    timeline.append(build_trigger_step(participant, banner, lane=1))

    # Card-effect step: all chosen cards fly hand -> lane
    if chosen:
        affected = []
        for card in chosen:
            # After playCard, the card will be at some lane.
            # We record its destination based on the specialClause play.
            # But actually, intSpecial calls playCard with random lane.
            # We only know the lane after execution. Since the function
            # executes the plays, we build the step from the card state after.
            affected.append({
                "cardId": card.id,
                "sourceLane": card.state.lane,        # 0 (hand) before playCard
                "sourceOrdinal": card.state.laneOrdinal,
                "destinationLane": card.state.lane,    # will be set after playCard
                "destinationOrdinal": card.state.laneOrdinal,
                "flipFaceUp": True,
                "trust": False,
            })
        timeline.append(build_card_effect_step(participant, affected))


def build_spd_timeline(participant, speed, power, opponent, timeline):
    """Append spdSpecial steps to the timeline. Returns response string."""
    if opponent is None:
        return ""
    opponentInt, opponentSpd, opponentVis, opponentRes, opponentTactics, opponentPower, opponentInfluence = opponent.getStats()

    if opponentPower < power:
        # Rush down
        banner = f"{participant.player.name} rushes down {opponent.player.name}"
        timeline.append(build_trigger_step(participant, banner, lane=2))
        # Opponent's special steps are appended to the SAME timeline (flattening)
        # by calling the opponent's special functions with the same timeline
        from MMM.views import specialActions
        specialActions(opponent, timeline)
        return ""
    else:
        if opponentSpd < speed:
            # Flee
            banner = f"{participant.player.name} flees from {opponent.player.name} and steals a card"
            timeline.append(build_trigger_step(participant, banner, lane=2))
            timeline.append(build_participant_effect_step(
                participant, banner, fled_id=participant.id))
            return f"{participant.id} fled from {opponent.id}"
        else:
            # Fail flee
            banner = f"{participant.player.name} fails to flee from {opponent.player.name}"
            timeline.append(build_trigger_step(participant, banner, lane=2))
            return ""


def build_vis_timeline(participant, viciousness, opponent, timeline):
    """Append visSpecial steps to the timeline. Returns response string."""
    if opponent is None:
        return ""
    opponentInt, opponentSpd, opponentVis, opponentRes, opponentTactics, opponentPower, opponentInfluence = opponent.getStats()

    from MMM.views import getTrustableCards
    newTrustedResCards = getTrustableCards(participant, [4])
    newTrustedResCard = newTrustedResCards[0] if newTrustedResCards else None

    if newTrustedResCard is None:
        # Drain - self defeat
        banner = f"{participant.player.name} drains the last of their resolve and is defeated"
        timeline.append(build_trigger_step(participant, banner, lane=3))
        timeline.append(build_participant_effect_step(
            participant, banner, defeated_id=participant.id))
        return banner
    elif opponentRes < viciousness:
        # Win - defeat opponent
        banner = f"{participant.player.name} attacks and defeats {opponent.player.name} ({viciousness} > {opponentRes})"
        timeline.append(build_trigger_step(participant, banner, lane=3))
        # Card-effect for the trusted resolve card glowing
        affected = [{
            "cardId": newTrustedResCard.id,
            "sourceLane": newTrustedResCard.state.lane,
            "sourceOrdinal": newTrustedResCard.state.laneOrdinal,
            "destinationLane": newTrustedResCard.state.lane,
            "destinationOrdinal": newTrustedResCard.state.laneOrdinal,
            "flipFaceUp": False,
            "trust": True,
        }]
        timeline.append(build_card_effect_step(participant, affected))
        timeline.append(build_participant_effect_step(
            participant, banner, defeated_id=opponent.id))
        return banner
    else:
        # Fail - no defeat
        banner = f"{participant.player.name} attacks {opponent.player.name} unsuccesfully ({viciousness} <= {opponentRes})"
        timeline.append(build_trigger_step(participant, banner, lane=3))
        # Still trust the resolve card
        affected = [{
            "cardId": newTrustedResCard.id,
            "sourceLane": newTrustedResCard.state.lane,
            "sourceOrdinal": newTrustedResCard.state.laneOrdinal,
            "destinationLane": newTrustedResCard.state.lane,
            "destinationOrdinal": newTrustedResCard.state.laneOrdinal,
            "flipFaceUp": False,
            "trust": True,
        }]
        timeline.append(build_card_effect_step(participant, affected))
        return ""


def build_res_timeline(participant, count, timeline):
    """Append resSpecial steps to the timeline."""
    from MMM.views import getTrustableCards
    newCards = getTrustableCards(participant)
    if not newCards:
        return
    import random
    random.shuffle(newCards)
    chosen = newCards[:min(count, len(newCards))]

    banner = f"{participant.player.name} holds and trusts up to {count} cards"
    timeline.append(build_trigger_step(participant, banner, lane=4))

    if chosen:
        affected = []
        for card in chosen:
            affected.append({
                "cardId": card.id,
                "sourceLane": card.state.lane,
                "sourceOrdinal": card.state.laneOrdinal,
                "destinationLane": card.state.lane,
                "destinationOrdinal": card.state.laneOrdinal,
                "flipFaceUp": False,
                "trust": True,
            })
        timeline.append(build_card_effect_step(participant, affected))
