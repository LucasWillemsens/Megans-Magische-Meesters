import json

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.template import loader
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import api_docs
from .battle_services import (
    context_board,
    ensure_game_initialized,
    game_outcome,
    perform_board_action,
    reset_games,
    run_bot_turn,
)
from .models import BattleParticipant, Game, GameCard

BOARD_PHASES = ("", "player", "playerMoves", "enemy")

NATURAL_LANE_VALUES = (1, 2, 3, 4)

PLAY_RECORD_FIELDS = {"cardId", "laneValue", "flipFaceUp", "sourceLane", "sourceOrdinal"}


class BoardActionRefused(Exception):
    pass


def _error_response(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _board_participants(request, game_id, player_id):
    try:
        game = Game.objects.get(pk=game_id)
    except Game.DoesNotExist:
        return None, None, _error_response("no such game or participant", status=404)
    try:
        participant = (
            BattleParticipant.objects
            .select_related("player")
            .get(player_id=player_id, battles=game.history)
        )
    except BattleParticipant.DoesNotExist:
        return None, None, _error_response("no such game or participant", status=404)
    return game, participant, None


def _request_payload_plays(request, plays_required):
    raw_body = request.body or b""
    if not raw_body.strip():
        return []
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as decode_error:
        raise BoardActionRefused(f"request body is not valid JSON: {decode_error}")
    if not isinstance(body, dict):
        raise BoardActionRefused("request body must be a JSON object")
    staged_plays = body.get("plays", [])
    if staged_plays is None:
        staged_plays = []
    if not isinstance(staged_plays, list):
        raise BoardActionRefused("plays must be an array of play records")
    if plays_required and not staged_plays:
        raise BoardActionRefused("plays must contain at least one play record")
    return staged_plays


def _validate_play_record(play, record_position):
    if not isinstance(play, dict):
        raise BoardActionRefused(f"play #{record_position} must be a JSON object")
    unsupported_fields = sorted(set(play) - PLAY_RECORD_FIELDS)
    if unsupported_fields:
        raise BoardActionRefused(
            f"play #{record_position} carries unsupported fields: {', '.join(unsupported_fields)}"
        )
    card_id = play.get("cardId")
    if isinstance(card_id, bool) or not isinstance(card_id, int):
        raise BoardActionRefused(f"play #{record_position} needs an integer cardId")
    lane_value = play.get("laneValue")
    if isinstance(lane_value, bool) or lane_value not in NATURAL_LANE_VALUES:
        raise BoardActionRefused(f"play #{record_position} needs a laneValue between 1 and 4")
    flip_face_up = play.get("flipFaceUp", False)
    if not isinstance(flip_face_up, bool):
        raise BoardActionRefused(f"play #{record_position} flipFaceUp must be a boolean")
    payload = {"cardId": card_id, "laneValue": lane_value, "flipFaceUp": flip_face_up}
    for field in ("sourceLane", "sourceOrdinal"):
        value = play.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise BoardActionRefused(f"play #{record_position} {field} must be an integer or null")
        payload[field] = value
    return payload


def _validated_staged_plays(request, game, participant, plays_required):
    record_list = _request_payload_plays(request, plays_required)
    seen_card_ids = set()
    payloads = []
    for record_position, record in enumerate(record_list):
        payload = _validate_play_record(record, record_position)
        if payload["cardId"] in seen_card_ids:
            raise BoardActionRefused(f"card {payload['cardId']} is staged more than once in plays")
        seen_card_ids.add(payload["cardId"])
        payloads.append(payload)
    owned_card_ids = set(
        GameCard.objects.filter(
            pk__in=seen_card_ids, game_id=game.id, user_id=participant.id
        ).values_list("id", flat=True)
    )
    for payload in payloads:
        if payload["cardId"] not in owned_card_ids:
            raise BoardActionRefused(
                f"card {payload['cardId']} is not a game card of participant {participant.id} in game {game.id}"
            )
    return {str(payload.pop("cardId")): payload for payload in payloads}


def _execute_board_action(request, game, participant, action_name):
    try:
        staged_payloads = _validated_staged_plays(
            request, game, participant, action_name == "play"
        )
        with transaction.atomic():
            ensure_game_initialized(game)
            executed_plays, timeline_steps, failure_message = perform_board_action(
                game, participant, action_name, staged_payloads
            )
            if failure_message:
                raise BoardActionRefused(failure_message)
    except BoardActionRefused as refusal:
        return None, _error_response(str(refusal))
    consumed_plays = [
        {
            "cardId": int(card_id),
            "participantId": participant.id,
            "laneValue": int(payload["laneValue"]),
            "sourceLane": payload["sourceLane"],
            "sourceOrdinal": payload["sourceOrdinal"],
            "flipFaceUp": payload["flipFaceUp"],
        }
        for card_id, payload in staged_payloads.items()
    ]
    return (consumed_plays, executed_plays, timeline_steps), None


def _normalized_play(play):
    return {**play, "cardId": int(play["cardId"])}


def _lane_card_payload(game_card):
    return {
        "gameCardId": game_card.id,
        "title": game_card.card.title,
        "cardType": game_card.card.cardType,
        "lane": game_card.state.lane,
        "laneOrdinal": game_card.state.laneOrdinal,
        "faceDown": game_card.state.faceDown,
        "trusted": game_card.state.trusted,
    }


def _hand_card_payload(game_card):
    return {
        "gameCardId": game_card.id,
        "title": game_card.card.title,
        "cardType": game_card.card.cardType,
        "laneOrdinal": game_card.state.laneOrdinal,
        "defaultLaneValue": game_card.card.cardType + 1,
    }


def _participant_state(game_cards, participant):
    own_board = context_board(game_cards, participant.id)
    return {
        "participantId": participant.id,
        "playerId": participant.player_id,
        "playerName": participant.player.name,
        "computerControlled": participant.computerControlled,
        "defeated": participant.defeated,
        "fled": participant.fled,
        "deckCount": own_board["deckCount"],
        "handCount": own_board["handCount"],
        "handCards": [
            _hand_card_payload(hand_card) for hand_card in own_board["handCards"]
        ],
        "allowances": participant.getTurnAllowances(),
        "lanes": [
            {
                "name": lane_row["name"],
                "revealedCount": lane_row["value"],
                "cards": [_lane_card_payload(card) for card in lane_row["cards"]],
                "trustedCards": [_lane_card_payload(card) for card in lane_row["trustedCards"]],
            }
            for lane_row in own_board["laneRows"]
        ],
    }


def _board_state_payload(game, viewer_participant, finished, turn_phase, next_turn_phase, bot_turn_ran, bot_plays):
    game_cards = GameCard.objects.filter(game_id=game.id).select_related(
        "card", "state", "user__player"
    )
    participants = list(game.history.participants.all().select_related("player"))
    return {
        "gameId": game.id,
        "gameTitle": game.title,
        "playerId": viewer_participant.player_id,
        "roundNumber": game.roundNumber,
        "finished": finished,
        "turnPhase": turn_phase,
        "nextTurnPhase": next_turn_phase,
        "botTurnRan": bot_turn_ran,
        "botPlays": [_normalized_play(play) for play in bot_plays],
        "viewer": _participant_state(game_cards, viewer_participant),
        "participants": [
            _participant_state(game_cards, squad_participant)
            for squad_participant in participants
        ],
    }


def _board_action_payload(game, participant, action_name, executed_plays, timeline_steps):
    finished, _, _ = game_outcome(game)
    return {
        "gameId": game.id,
        "playerId": participant.player_id,
        "action": action_name,
        "finished": finished,
        "roundNumber": game.roundNumber,
        "enemyPhasePending": action_name == "end_turn",
        "error": None,
        "plays": [_normalized_play(play) for play in executed_plays],
        "timelineSteps": timeline_steps,
        "turnAllowances": participant.getTurnAllowances(),
    }


@csrf_exempt
@require_GET
def openapi_schema(request):
    return JsonResponse(api_docs.openapi_schema())


@require_GET
def swagger_ui(request):
    template = loader.get_template("MMM/api/swagger_ui.jinja2")
    context = {"schemaUrl": api_docs.SCHEMA_PATH}
    return HttpResponse(template.render(context, request))


@csrf_exempt
@require_POST
def api_reset_games(request):
    removed_games = reset_games()
    return JsonResponse({"status": "reset", "removedGames": removed_games})


@require_GET
def api_board_state(request, game_id, player_id):
    game, viewer_participant, error = _board_participants(request, game_id, player_id)
    if error is not None:
        return error
    turn_phase = request.GET.get("phase", "")
    if turn_phase not in BOARD_PHASES:
        return _error_response("unsupported phase; use player, playerMoves or enemy")
    if not GameCard.objects.filter(game_id=game.id).exists():
        return _error_response(
            "game not initialized yet; confirm the challenge before reading the board",
            status=409,
        )
    bot_plays = []
    bot_turn_ran = False
    if turn_phase == "enemy":
        finished, _, _ = game_outcome(game)
        if not finished:
            bot_plays, _ = run_bot_turn(game, viewer_participant.player_id)
            game.roundNumber = max(game.roundNumber, 1) + 1
            game.save(update_fields=["roundNumber"])
            bot_turn_ran = True
    finished, _, _ = game_outcome(game)
    payload = _board_state_payload(
        game,
        viewer_participant,
        finished,
        turn_phase,
        "player" if bot_turn_ran else "",
        bot_turn_ran,
        bot_plays,
    )
    return JsonResponse(payload)


@csrf_exempt
@require_POST
def api_play_cards(request, game_id, player_id):
    return _respond_board_action(request, game_id, player_id, "play")


@csrf_exempt
@require_POST
def api_draw_card(request, game_id, player_id):
    return _respond_board_action(request, game_id, player_id, "draw")


@csrf_exempt
@require_POST
def api_end_turn(request, game_id, player_id):
    return _respond_board_action(request, game_id, player_id, "end_turn")


def _respond_board_action(request, game_id, player_id, action_name):
    game, participant, error = _board_participants(request, game_id, player_id)
    if error is not None:
        return error
    action_result, error = _execute_board_action(request, game, participant, action_name)
    if error is not None:
        return error
    consumed_plays, executed_plays, timeline_steps = action_result
    payload = _board_action_payload(
        game, participant, action_name, consumed_plays + executed_plays, timeline_steps
    )
    return JsonResponse(payload)
