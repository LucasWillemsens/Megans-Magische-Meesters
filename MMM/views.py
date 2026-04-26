from django.http import HttpResponse
from django.shortcuts import redirect
from django.template import loader

from .models import (
    BattleHistory,
    BattleParticipant,
    Card,
    CardOwnerHistory,
    CardState,
    CardType,
    Deck,
    Game,
    GameCard,
    Player,
)

BASE_URL = "http://127.0.0.1:8000/"

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
    battles = BattleParticipant.objects.filter(player_id=player.id)

    challenges = []
    for battle in battles:
        for challenge in battle.player.challenges.all():
            challenges.append(challenge)

    context = {
        "player": player,
        "cardOwner": card_owner,
        "challenges": list(set(challenges)),
        "assestsDir": "MMM/",
        "returnURL": BASE_URL,
        "error_message": "",
    }
    return _render(request, "MMM/viewPlayer.jinja2", context)


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
    _ensure_game_initialized(game)
    return redirect(f"/game/{game_id}/board/{player_id}/")


def viewBoard(request, game_id, player_id, error_message=""):
    game = Game.objects.get(pk=game_id)
    current_participant = game.history.participants.get(player_id=player_id)

    if not GameCard.objects.filter(game_id=game_id, user_id=current_participant.id).exists():
        return redirect(f"/game/{game_id}/{player_id}/")

    finished, _ = _game_result(game)
    if finished:
        return redirect(f"/game/{game_id}/winner/{player_id}/")

    own_board = newBoard()
    # _board_state(game.id, current_participant.id)
    enemy_boards = []
    for enemy_participant in game.history.participants.exclude(id=current_participant.id).select_related("player"):
        enemy_board = newBoard()
        #  _board_state(game.id, enemy_participant.id)
        
        enemy_boards.append(
            {
                "participant": enemy_participant,
                "laneRows": enemy_board["laneRows"],
                "deckCount": enemy_board["deckCount"],
                "handCount": enemy_board["handCount"],
            }
        )

    context = {
        "player_id": player_id,
        "player": current_participant.player,
        "game": game,
        "assestsDir": "MMM/",
        "returnURL": BASE_URL,
        "error_message": error_message,
        "actionUrl": f"{BASE_URL}game/{game.id}/board/{player_id}/action/",
        "handCards": own_board["handCards"],
        "ownLaneRows": own_board["laneRows"],
        "ownDeckCount": own_board["deckCount"],
        "ownDeckStack": own_board["deckStack"],
        "enemyBoards": enemy_boards,
    }
    return _render(request, "MMM/battle/viewBoard.jinja2", context)


def boardAction(request, game_id, player_id):
    if request.method != "POST":
        return redirect(f"/game/{game_id}/board/{player_id}/")

    game = Game.objects.get(pk=game_id)
    current_participant = game.history.participants.get(player_id=player_id)
    _ensure_game_initialized(game) #todo remove this

    action = request.POST.get("action", "")
    error_message = ""
    try:
        if action == "draw":
            if participant.drawCard() is None:
                error_message = "No cards left in deck."
        elif action == "play":
            card_id = int(request.POST.get("card_id", "0"))
            lane_value = request.POST.get("lane", "")
            lane = int(lane_value) if lane_value else None
            participant.playCard(card_id, lane)
        elif action == "end_turn":
            _run_bot_turn(game, player_id)
            game.roundNumber = max(game.roundNumber, 1) + 1
            game.save(update_fields=["roundNumber"])
        else:
            error_message = "Unknown action."
    except Exception as exc:
        error_message = str(exc)

    finished, _ = _game_result(game)
    if finished:
        return redirect(f"/game/{game_id}/winner/{player_id}/")
    return viewBoard(request, game_id, player_id, error_message=error_message)


def viewWinner(request, game_id, player_id):
    game = Game.objects.get(pk=game_id)
    current_participant = game.history.participants.get(player_id=player_id)
    finished, winner_participant = _game_result(game)
    if not finished:
        return redirect(f"/game/{game_id}/board/{player_id}/")

    context = {
        "player": current_participant.player,
        "game": game,
        "winnerParticipant": winner_participant,
        "participants": game.history.participants.all(),
        "returnURL": BASE_URL,
        "playAgainUrl": f"{BASE_URL}player/{player_id}/",
    }
    return _render(request, "MMM/battle/viewWinner.jinja2", context)

def resetGames(request):
    Game.objects.all().delete()
    BattleHistory.objects.all().delete()
    BattleParticipant.objects.all().delete()
    GameCard.objects.all().delete()
    CardState.objects.all().delete()
    Deck.objects.all().delete()
    return redirect("/")

def _render(request, template_name, context):
    template = loader.get_template(template_name)
    return HttpResponse(template.render(context, request))

def _participant_game_cards(game_id, participant_id):
    return list(
        GameCard.objects.filter(game_id=game_id, user_id=participant_id)
        .select_related("card", "state")
        .order_by("state__lane", "state__laneOrdinal", "id")
    )


def _participant_has_actions(game_id, participant_id):
    cards = GameCard.objects.filter(game_id=game_id, user_id=participant_id)
    return cards.filter(state__inDeck=True).exists() or cards.filter(state__lane=0).exists()

def _game_result(game):
    participants = list(game.history.participants.all())
    if not participants:
        return False, None

    active_participants = [
        participant for participant in participants if _participant_has_actions(game.id, participant.id)
    ]

    if len(active_participants) == len(participants):
        return False, None
    if len(active_participants) == 1:
        return True, active_participants[0]
    if len(active_participants) == 0:
        return True, None
    return False, None


def _ensure_game_initialized(game):
    for participant in game.history.participants.all():
        participant.startWithDeckInRandomOrder(initializeStartingCard=True)
    if game.roundNumber < 1:
        game.roundNumber = 1
        game.save(update_fields=["roundNumber"])


def _run_bot_turn(game, human_player_id):
    bot_participants = game.history.participants.exclude(player_id=human_player_id).filter(computerControlled=True)
    for bot_participant in bot_participants:
        hand_card = (
            GameCard.objects.filter(game_id=game.id, user_id=bot_participant.id, state__lane=0)
            .select_related("card")
            .first()
        )
        if hand_card is None:
            bot_participant.drawCard()
            hand_card = (
                GameCard.objects.filter(game_id=game.id, user_id=bot_participant.id, state__lane=0)
                .select_related("card")
                .first()
            )
        if hand_card is not None:
            bot_participant.playCard(hand_card.id)

def newBoard():
    board = {
        "handCards": [],
        "handCount": 0,
        "laneRows": [{"name": "Intelligence", "cards": [], "trustedCards": []}, 
        {"name": "Speed", "cards": [], "trustedCards": []}, {"name": "Visciousness", "cards": [], "trustedCards": []}, {"name": "Resolve", "cards": [], "trustedCards": []}],
        "deckCount": 0,
        "deckStack": [],
    }
    return board
