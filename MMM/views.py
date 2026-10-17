from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template import loader
from django.urls import reverse

from .battle_services import (
    chunk_hand_cards,
    context_board,
    cookie_staged_plays,
    ensure_game_initialized,
    game_outcome,
    parse_play_cookie_payload,
    perform_board_action,
    reset_games,
    run_bot_turn,
)
from .card_tokens import play_card_token_index, timeline_card_tokens
from .demo_flow import (
    TEAM_BOTS,
    anonymous_scenario,
    fresh_demo_deck,
    latest_demo_deck,
    team_scenario,
    team_player,
)
from .demo_greetings import title_greeting
from .models import (
    BattleHistory,
    BattleParticipant,
    Card,
    CardOwnerHistory,
    CardType,
    Deck,
    Game,
    GameCard,
    Player,
)

BASE_URL = "http://127.0.0.1:8000/"
TURN_PHASE_COOKIE = "turn_phase"
CARD_ZOOM_SESSION_KEY = "card_zoom"
OWNED_CARD_SORT_KEYS = {"name", "type", "date"}
DEMO_PLAYER_SESSION_KEY = "demo_player_id"
TITLE_VISITED_SESSION_KEY = "title_visited"


def current_demo_player(request):
    demo_player_id = request.session.get(DEMO_PLAYER_SESSION_KEY)
    if demo_player_id is None:
        return None
    return Player.objects.filter(pk=demo_player_id).first()


def home(request):
    return redirect(reverse("MMM:titlePage"))


def titlePage(request):
    demo_identity = current_demo_player(request)
    visited = request.session.get(TITLE_VISITED_SESSION_KEY, False)
    context = {
        "greeting": title_greeting(visited, demo_identity and demo_identity.name),
        "playUrl": reverse("MMM:play"),
    }
    request.session[TITLE_VISITED_SESSION_KEY] = True
    return _render(request, "MMM/title.jinja2", context)


def play(request):
    if request.method != "POST":
        return redirect(reverse("MMM:titlePage"))
    demo_identity = current_demo_player(request)
    if demo_identity is None:
        annabel, game = anonymous_scenario()
        return redirect(reverse("MMM:viewBoard", args=(game.id, annabel.id)))
    game = team_scenario(demo_identity)
    return redirect(reverse("MMM:viewGameAsPlayer", args=(game.id, demo_identity.id)))


def deckPage(request):
    demo_identity = current_demo_player(request)
    activeDeck = latest_demo_deck(demo_identity) if demo_identity else None
    context = {
        "player": demo_identity,
        "activeDeck": activeDeck,
        "deckCards": activeDeck.cards.all() if activeDeck else [],
        "teamBotPairs": list(TEAM_BOTS.items()),
        "teamPickUrl": reverse("MMM:pickDeckTeam"),
        "renamePlayerUrl": reverse("MMM:renameDeckPlayer"),
    }
    return _render(request, "MMM/deck.jinja2", context)


def pickDeckTeam(request):
    if request.method != "POST":
        return redirect(reverse("MMM:deckPage"))
    demo_identity = team_player(request.POST.get("team", ""))
    fresh_demo_deck(demo_identity)
    request.session[DEMO_PLAYER_SESSION_KEY] = demo_identity.id
    game = team_scenario(demo_identity)
    return redirect(reverse("MMM:viewGameAsPlayer", args=(game.id, demo_identity.id)))


def renameDeckPlayer(request):
    if request.method != "POST":
        return redirect(reverse("MMM:deckPage"))
    demo_identity = current_demo_player(request)
    new_name = request.POST.get("name", "").strip()
    if demo_identity is not None and new_name:
        demo_identity.name = new_name
        demo_identity.save(update_fields=["name"])
    return redirect(reverse("MMM:deckPage"))


def card_zoom_enabled(request):
    return bool(request.session.get(CARD_ZOOM_SESSION_KEY, True))


def demoSettings(request):
    context = {
        "cardZoomEnabled": card_zoom_enabled(request),
        "toggleZoomUrl": reverse("MMM:toggleCardZoom"),
    }
    return _render(request, "MMM/settings.jinja2", context)


def toggleCardZoom(request):
    if request.method != "POST":
        return redirect(reverse("MMM:demoSettings"))
    request.session[CARD_ZOOM_SESSION_KEY] = request.POST.get("enable", "") == "true"
    return redirect(reverse("MMM:demoSettings"))


def index(request):
    context = {
        "latest_cards_list": Card.objects.order_by("title")[:5],
        "players": Player.objects.order_by("name"),
        "assestsDir": "MMM/",
        "landingPage": BASE_URL,
    }
    return _render(request, "MMM/index.jinja2", context)

def viewPlayer(request, player_id):
    player = Player.objects.get(pk=player_id)
    card_owner = CardOwnerHistory.objects.filter(cardOwner_id=player.id).first()
    requested_sort = request.GET.get("sort")
    active_sort = (
        requested_sort if requested_sort in OWNED_CARD_SORT_KEYS else "default"
    )
    owned_cards = _get_owned_cards(player, active_sort)

    histories = (
        BattleHistory.objects.filter(challenger=player)
        .prefetch_related(
            "participants__player",
            "lootPile",
            "game",
        )
        .order_by("-id")
    )
    challenges = [_enrich_challenge(history, player.id) for history in histories]

    context = {
        "player": player,
        "cardOwner": card_owner,
        "ownedCards": owned_cards,
        "activeSort": active_sort,
        "challenges": challenges,
        "assestsDir": "MMM/",
        "returnURL": BASE_URL,
        "error_message": "",
    }
    return _render(request, "MMM/viewPlayer.jinja2", context)


def _enrich_challenge(history, player_id):
    participants = list(history.participants.all())
    game = history.game.first()
    is_participant = any(p.player_id == player_id for p in participants)
    finished = False
    survivors = []
    if game is not None:
        finished, _, survivors = game_outcome(game)
        survivors = survivors or []

    return {
        "history": history,
        "participants": participants,
        "lootPileText": history.printLootPile(),
        "game": game,
        "isParticipant": is_participant,
        "started": min(
            (participant.joinedBattle for participant in participants), default=None
        ),
        "finished": finished,
        "survivors": survivors,
        "won": _challenge_result_for_player(
            participants, player_id, finished, survivors
        ),
        # Own games always link straight to the board (viewBoard redirects to the
        # result page when finished); non-participant/pending rows fall back to
        # the game page because viewBoard requires a matching participant row.
        "boardUrl": (
            f"{BASE_URL}game/{game.id}/board/{player_id}/"
            if game is not None and is_participant
            else None
        ),
        "gameUrl": (
            f"{BASE_URL}game/{game.id}/{player_id}/" if game is not None else None
        ),
    }


def _challenge_result_for_player(participants, player_id, finished, survivors):
    if not finished:
        return None
    own_participant = next(
        (p for p in participants if p.player_id == player_id), None
    )
    if own_participant is None:
        return False
    if own_participant.fled:
        return "fled"
    survivor_ids = {survivor.id for survivor in survivors or []}
    return own_participant.id in survivor_ids


def _get_owned_cards(player, sort_key="default"):
    """Return the player's current cards with optional server-side sorting.

    The collection deliberately uses Player.getCollection() rather than the
    first CardOwnerHistory relation, so a card whose latest history belongs
    to another player cannot appear as currently owned. The default order is
    ascending card id, preserving the existing relation's insertion order for
    the current data. Date sorting uses the latest relevant aquiredAt for the
    player; equal timestamps use case-insensitive title and then id.
    """
    current_card_ids = [card.id for card in player.getCollection()]
    cards = list(Card.objects.filter(id__in=current_card_ids).order_by("id"))

    if sort_key == "name":
        return sorted(cards, key=_card_name_sort_key)
    if sort_key == "type":
        return sorted(
            cards,
            key=lambda card: (card.cardType, *(_card_name_sort_key(card))),
        )
    if sort_key == "date":
        acquisition_dates = _latest_acquisition_dates(player, cards)
        return sorted(
            cards,
            key=lambda card: (
                -acquisition_dates[card.id].timestamp(),
                *_card_name_sort_key(card),
            ),
        )
    return cards


def _card_name_sort_key(card):
    return card.title.casefold(), card.id


def _latest_acquisition_dates(player, cards):
    if not cards:
        return {}

    history_rows = (
        CardOwnerHistory.objects.filter(cardOwner_id=player.id, card__in=cards)
        .values("card__id")
        .annotate(latest_acquired_at=Max("aquiredAt"))
    )
    return {
        row["card__id"]: row["latest_acquired_at"]
        for row in history_rows
    }


def viewCard(request, card_id):
    card = Card.objects.get(pk=card_id)
    context = {
        "card": card,
        "cardType": [lane.name for lane in CardType][card.cardType],
        "symbols": [],
        "assestsDir": "MMM/",
        "returnURL": BASE_URL,
        "error_message": "",
    }
    return _render(request, "MMM/viewCard.jinja2", context)


def viewGame(request, game_id):
    game = Game.objects.get(pk=game_id)
    context = {
        "player_id": -1,
        "player": object(),
        "game": game,
        "challenger": game.history.challenger,
        "battlers": game.history.participants.all(),
        "assestsDir": "MMM/",
        "submitUrl": f"{BASE_URL}game/",
        "returnURL": BASE_URL,
        "error_message": "",
    }
    return _render(request, "MMM/viewGame.jinja2", context)


def viewGameAsPlayer(request, game_id, player_id):
    game = Game.objects.get(pk=game_id)
    current_battler = Player.objects.get(pk=player_id)
    request.session['player_id'] = player_id
    request.session.get('player_id')

    context = {
        "player_id": player_id,
        "player": current_battler,
        "game": game,
        "challenger": game.history.challenger,
        "battlers": game.history.participants.all(),
        "assestsDir": "MMM/",
        "submitUrl": f"{BASE_URL}game/{game.id}/{player_id}/confirm",
        "returnURL": BASE_URL,
        "error_message": "",
    }
    return _render(request, "MMM/viewGame.jinja2", context)

def createGame(request, player_id):
    if not CardOwnerHistory.objects.filter(cardOwner_id=player_id).exists():
        return redirect(f"/player/{player_id}/")

    new_game = Game.createHumanChallenge(player_id=player_id)
    new_game.save()
    context = {
        "cardOwner": CardOwnerHistory.objects.filter(cardOwner_id=player_id).first(),
        "newGameId": new_game.id,
        "decks": Deck.objects.filter(player_id=player_id),
        "players": Player.objects.exclude(id=player_id),
        "assestsDir": "MMM/",
        "submitUrl": f"{BASE_URL}game/initialize/",
        "returnURL": f"{BASE_URL}player/{player_id}/",
        "error_message": "",
    }
    return _render(request, "MMM/createGame.jinja2", context)

def initializeGame(request):
    if request.method != "POST":
        return redirect("/")

    new_game_id = int(request.POST["newGameIdValue"])
    challenger_id = int(request.POST["challenger"])
    challenge_id = int(request.POST["challengePlayer"])
    new_game_starting_deck = request.POST["startingDeck"]
    new_game_starting_card = int(request.POST["startingCard"])

    if new_game_starting_deck == "New":
        deck = Deck.create(player_id=challenger_id)
    else:
        deck = Deck.objects.get(pk=int(new_game_starting_deck))

    starting_card = Card.objects.get(pk=new_game_starting_card)
    if not deck.cards.filter(pk=new_game_starting_card).exists():
        deck.cards.add(starting_card)

    game = Game.objects.get(pk=new_game_id)
    human_participant = game.history.addHumanChallenger(challenger_id, new_game_starting_card, deck.id)

    if challenge_id == challenger_id:
        fallback_opponent = Player.objects.exclude(id=challenger_id).first()
        if fallback_opponent is None:
            raise Exception("no opponent available")
        challenge_id = fallback_opponent.id

    robot_participant = game.history.addRobotChallenger(challenge_id)
    if game.title == "new challenge":
        game.title = f"{human_participant.player.name} vs {robot_participant.player.name}"
        game.save(update_fields=["title"])

    return redirect(f"/game/{new_game_id}/{challenger_id}/")


def confirmChallenge(request, game_id, player_id):
    if request.method != "POST":
        return redirect(f"/game/{game_id}/{player_id}/")

    game = Game.objects.get(pk=game_id)
    ensure_game_initialized(game)
    return redirect(f"/game/{game_id}/board/{player_id}/")


def viewBoard(request, game_id, player_id, error_message="", clear_cookies=False, turn_phase=None, action_plays=None, timeline_steps=None):
    game = Game.objects.get(pk=game_id)
    current_participant = game.history.participants.get(player_id=player_id)
    gameCards = GameCard.objects.filter(game_id=game_id)

    if not gameCards.exists():
        return redirect(f"/game/{game_id}/{player_id}/")
        
    action_render = turn_phase is not None
    phase_from_cookie = turn_phase is None
    if phase_from_cookie:
        turn_phase = request.COOKIES.get(TURN_PHASE_COOKIE, "")

    bot_actions = []
    bot_timelines = []
    if phase_from_cookie and turn_phase == "enemy":
        finished, _, _ = game_outcome(game)
        if not finished:
            try:
                bot_result = run_bot_turn(game, player_id)
                if isinstance(bot_result, tuple):
                    bot_actions, bot_timelines = bot_result
                else:
                    bot_actions = bot_result
                    bot_timelines = []
            except Exception as exc:
                bot_actions = []
                bot_timelines = []
                error_message = str(exc)
            game.roundNumber = max(game.roundNumber, 1) + 1
            game.save(update_fields=["roundNumber"])
        plays_by_card = {}
        for bot_action in bot_actions:
            play = plays_by_card.setdefault(str(bot_action["cardId"]), dict(bot_action))
            play["laneValue"] = bot_action["laneValue"]
            play["flipFaceUp"] = bot_action["flipFaceUp"]
        action_plays = (action_plays or []) + list(plays_by_card.values())
        if bot_timelines:
            timeline_steps = (timeline_steps or []) + bot_timelines

    finished, _, _ = game_outcome(game)

    if not clear_cookies:
        clear_cookies = turn_phase == "enemy"

    sequence_render = action_render or clear_cookies or turn_phase == "enemy"
    if finished and not sequence_render:
        response = redirect(f"/game/{game_id}/result/{player_id}/")
        if TURN_PHASE_COOKIE in request.COOKIES:
            response.delete_cookie(
                TURN_PHASE_COOKIE, path=f"/game/{game.id}/board/{player_id}/"
            )
        return response

    own_board = context_board(gameCards, current_participant.id)
    enemy_boards = []
    for enemy_participant in game.history.participants.exclude(id=current_participant.id).select_related("player"):
        enemy_board = context_board(gameCards, enemy_participant.id)

        enemy_boards.append(
            {
                "participant": enemy_participant,
                "laneRows": enemy_board["laneRows"],
                "deckCount": enemy_board["deckCount"],
                "handCount": enemy_board["handCount"],
                "deckStack": enemy_board["deckStack"],
                "deckIndicators": enemy_board["deckIndicators"],
                "handCards": enemy_board["handCards"],
                "handFans": enemy_board["handFans"],
            }
        )

    context = {
        "player_id": player_id,
        "player": current_participant.player,
        "current_participant": current_participant,
        "game": game,
        "assestsDir": "MMM/",
        "returnURL": BASE_URL,
        "error_message": error_message,
        "actionUrl": f"{BASE_URL}game/{game.id}/board/{player_id}/action/",
        "handCards": own_board["handCards"],
        "handFans": own_board["handFans"],
        "ownLaneRows": own_board["laneRows"],
        "ownDeckCount": own_board["deckCount"],
        "ownDeckStack": own_board["deckStack"],
        "ownDeckIndicators": own_board["deckIndicators"],
        "drawnCardsAmount": current_participant.drawnCardsAmount,
        "playedCardsAmount": current_participant.playedCardsAmount,
        "flippedCardsAmount": current_participant.flippedCardsAmount,
        "turnAllowances": current_participant.getTurnAllowances(),
        "enemyBoards": enemy_boards,
        "turnPhase": turn_phase,
        "nextUrl": (
            f"/game/{game_id}/result/{player_id}/"
            if finished and turn_phase != "playerMoves"
            else f"/game/{game_id}/board/{player_id}/"
        ),
        "actionPlays": action_plays or [],
        "timelineSteps": timeline_card_tokens(timeline_steps or [], game.id),
        "cardZoomEnabled": card_zoom_enabled(request),
    }
    response = _render(request, "MMM/battle/viewBoard.jinja2", context, clear_cookies=clear_cookies)

    if phase_from_cookie:
        cookie_path = f"/game/{game.id}/board/{player_id}/"
        if turn_phase == "enemy":
            if finished:
                response.delete_cookie(TURN_PHASE_COOKIE, path=cookie_path)
            else:
                response.set_cookie(TURN_PHASE_COOKIE, "player", path=cookie_path)
        elif turn_phase == "player":
            response.delete_cookie(TURN_PHASE_COOKIE, path=cookie_path)
    return response

def boardAction(request, game_id, player_id):
    if request.method != "POST":
        return redirect(f"/game/{game_id}/board/{player_id}/")

    game = Game.objects.get(pk=game_id)
    current_participant = game.history.participants.get(player_id=player_id)
    ensure_game_initialized(game)

    action = request.POST.get("action", "")
    focused_hand_card_raw = request.POST.get("focused_hand_card", "")
    if focused_hand_card_raw.isdigit():
        focused_hand_card = int(focused_hand_card_raw)
        if 1 <= focused_hand_card <= 6561:
            current_participant.focusedHandCard = focused_hand_card
            current_participant.save(update_fields=["focusedHandCard"])
    action_plays, timeline_steps, error_message = perform_board_action(
        game,
        current_participant,
        action,
        cookie_staged_plays(request.COOKIES, game),
    )

    request.session['plays'] = []
    end_turn_done = (action == "end_turn" and not error_message) or (action == "draw" and bool(timeline_steps))
    # Set playerMoves phase when specials trigger on draw, so the JS
    # plays the timeline animation (otherwise the empty phase skips it).
    needs_timeline_play = bool(timeline_steps)
    response = viewBoard(
        request,
        game_id,
        player_id,
        error_message=error_message,
        clear_cookies=True,
        turn_phase="playerMoves" if (end_turn_done or needs_timeline_play) else "",
        action_plays=action_plays,
        timeline_steps=timeline_steps,
    )
    if end_turn_done:
        response.set_cookie(
            TURN_PHASE_COOKIE, "enemy", path=f"/game/{game.id}/board/{player_id}/"
        )
    return response

def viewResult(request, game_id, player_id):
    game = Game.objects.get(pk=game_id)
    current_participant = game.history.participants.get(player_id=player_id)
    finished, win, last_participants = game_outcome(game)
    if not finished:
        return redirect(f"/game/{game_id}/board/{player_id}/")

    context = {
        "player": current_participant.player,
        "game": game,
        "lastParticipants": last_participants,
        "result": win and "winners" or "losers",
        "participants": game.history.participants.all(),
        "returnURL": BASE_URL,
        "playAgainUrl": f"{BASE_URL}player/{player_id}/",
    }
    return _render(request, "MMM/battle/viewResult.jinja2", context)

def resetGames(request):
    reset_games()
    return redirect("/")

def _render(request, template_name, context, clear_cookies=False):
    template = loader.get_template(template_name)
    
    if clear_cookies:
        context = _addLoadingAnimations(context, request)
    response = HttpResponse(template.render(context, request))
    if "action" in request.path:
        requestPath = request.path[0: request.path.rfind("action")]
    else:
        requestPath = request.path

    if clear_cookies:
        for cookie in request.COOKIES:
            if cookie in ("sessionid", "csrftoken", TURN_PHASE_COOKIE):
                continue
            response.delete_cookie(cookie, path=requestPath)
    return response

def _addLoadingAnimations(context, request):
    plays = list(context.get("actionPlays", []))
    game = context.get("game")
    token_index = play_card_token_index(game.id) if game else {}
    for cookie_name, cookie_value in request.COOKIES.items():
        if cookie_name not in token_index or not cookie_value:
            continue
        card_id, participant_id = token_index[cookie_name]
        payload = parse_play_cookie_payload(cookie_value)
        plays.append(
            {
                "cardId": str(card_id),
                "participantId": participant_id,
                "laneValue": payload["laneValue"],
                "sourceLane": payload["sourceLane"],
                "sourceOrdinal": payload["sourceOrdinal"],
                "flipFaceUp": payload["flipFaceUp"],
            }
        )
    context["plays"] = plays
    print(f"Updating loading animations for plays: {plays} at {request.path}")
    context["handCards"] = _update_moved_hand_cards(context["handCards"], plays)
    context["handFans"] = chunk_hand_cards(context["handCards"])
    context["ownLaneRows"] = _update_played_cards(context["ownLaneRows"],plays)
    for enemy_board in context.get("enemyBoards", []):
        enemy_plays = [
            play
            for play in plays
            if play["participantId"] == enemy_board["participant"].id
        ]
        if enemy_plays:
            enemy_board["laneRows"] = _update_played_cards(enemy_board["laneRows"], enemy_plays)
            enemy_board["handCards"] = _update_moved_hand_cards(
                enemy_board["handCards"], enemy_plays
            )
            enemy_board["handFans"] = chunk_hand_cards(enemy_board["handCards"])
    return context


def _update_moved_hand_cards(hand_cards, plays):
    for play in plays:
        card_id = int(play["cardId"])
        for card in hand_cards:
            if card.id == card_id:
                if play["sourceLane"] is not None:
                    card.state.lane = play["sourceLane"]
                if play["sourceOrdinal"] is not None:
                    card.state.laneOrdinal = play["sourceOrdinal"]
                card.cssClass = "loading"
    return hand_cards


def _update_played_cards(lane_rows, plays):
    for play in plays:
        card_id = int(play["cardId"])
        for row in lane_rows:
            for card in row["cards"]:
                if card.id == card_id:
                    if play["sourceLane"] is not None:
                        card.state.lane = play["sourceLane"]
                    if play["sourceOrdinal"] is not None:
                        card.state.laneOrdinal = play["sourceOrdinal"]
                    card.cssClass = "loading"
                    print(f"{card.card.title}(card{card.id}) {card.state.lane}({card.state.laneOrdinal}) -> {row['name']} .")
    return lane_rows
