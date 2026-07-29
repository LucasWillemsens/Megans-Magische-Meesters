from django.http import HttpResponse
from django.shortcuts import redirect
from django.template import loader

import json
import random
from urllib.parse import unquote

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
TURN_PHASE_COOKIE = "turn_phase"

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


def viewBoard(request, game_id, player_id, error_message="", clear_cookies=False, turn_phase=None, action_plays=None):
    game = Game.objects.get(pk=game_id)
    current_participant = game.history.participants.get(player_id=player_id)
    gameCards = GameCard.objects.filter(game_id=game_id)

    if not gameCards.exists():
        return redirect(f"/game/{game_id}/{player_id}/")
        
    action_render = turn_phase is not None
    phase_from_cookie = turn_phase is None
    if phase_from_cookie:
        turn_phase = request.COOKIES.get(TURN_PHASE_COOKIE, "")

    if phase_from_cookie and turn_phase == "enemy":
        try:
            bot_actions = _run_bot_turn(game, player_id)
        except Exception as exc:
            bot_actions = []
            error_message = str(exc)
        game.roundNumber = max(game.roundNumber, 1) + 1
        game.save(update_fields=["roundNumber"])
        plays_by_card = {}
        for bot_action in bot_actions:
            play = plays_by_card.setdefault(str(bot_action["cardId"]), dict(bot_action))
            play["laneValue"] = bot_action["laneValue"]
            play["flipFaceUp"] = bot_action["flipFaceUp"]
        action_plays = (action_plays or []) + list(plays_by_card.values())

    finished, _, _ = _game_result(game)

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

    own_board = contextBoard(gameCards, current_participant.id)
    enemy_boards = []
    for enemy_participant in game.history.participants.exclude(id=current_participant.id).select_related("player"):
        enemy_board = contextBoard(gameCards, enemy_participant.id)

        enemy_boards.append(
            {
                "participant": enemy_participant,
                "laneRows": enemy_board["laneRows"],
                "deckCount": enemy_board["deckCount"],
                "handCount": enemy_board["handCount"],
                "deckStack": enemy_board["deckStack"],
                "handCards": enemy_board["handCards"],
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

# todo refactor to modular
def boardAction(request, game_id, player_id):
    if request.method != "POST":
        return redirect(f"/game/{game_id}/board/{player_id}/")

    game = Game.objects.get(pk=game_id)
    current_participant = game.history.participants.get(player_id=player_id)
    _ensure_game_initialized(game) #todo remove this

    action = request.POST.get("action", "")
    error_message = ""
    action_plays = []
    try:
        playcards(game, request.COOKIES, current_participant)
        if action == "draw":
            next_deck_card = current_participant.getNextDeckCard()
            source_lane = next_deck_card.state.lane if next_deck_card else None
            source_ordinal = next_deck_card.state.laneOrdinal if next_deck_card else None
            drawn_card = current_participant.drawCard()
            if drawn_card is not None:
                action_plays.append({
                    "cardId": str(drawn_card.id),
                    "participantId": current_participant.id,
                    "laneValue": 0,
                    "sourceLane": source_lane,
                    "sourceOrdinal": source_ordinal,
                    "flipFaceUp": False,
                })
                if current_participant.getNextDeckCard() is None:
                    specialActions(current_participant)
                    current_participant.shuffleBoard()
            else:
                error_message = f"No cards left in {current_participant}'s deck."
        elif action == "end_turn":
            current_participant.resetTurn()
        else:
            error_message = "Unknown action."
    except Exception as exc:
        error_message = str(exc)

    request.session['plays'] = []
    end_turn_done = action == "end_turn" and not error_message
    response = viewBoard(
        request,
        game_id,
        player_id,
        error_message=error_message,
        clear_cookies=True,
        turn_phase="playerMoves" if end_turn_done else "",
        action_plays=action_plays,
    )
    if end_turn_done:
        response.set_cookie(
            TURN_PHASE_COOKIE, "enemy", path=f"/game/{game.id}/board/{player_id}/"
        )
    return response

def playcards(game, plays, participant):
    for play in plays:
        if play =="csrftoken" or play == "sessionid":
            continue
        try:
            card_id = int(play)
        except (TypeError, ValueError):
            continue
        if not GameCard.objects.filter(pk=card_id, game_id=game.id, user_id=participant.id).exists():
            continue
        payload = _parse_play_cookie_value(plays[play])
        participant.playCard(
            card_id,
            int(payload["laneValue"]),
            payload["flipFaceUp"],
            sourceLane=payload["sourceLane"],
            sourceOrdinal=payload["sourceOrdinal"],
        )

def specialActions(participant):
    intCount, spdCount, visCount, resCount, tactics, power, influence = participant.getStats()
    response = ""
    if intCount >= spdCount and intCount >= visCount and intCount >= resCount:
        intSpecial(participant, intCount)

    intCount, spdCount, visCount, resCount, tactics, power, influence = participant.getStats()

    if spdCount >= intCount and spdCount >= visCount and spdCount >= resCount:
        response = spdSpecial(participant, spdCount, power)

    if response == "" and visCount >= intCount and visCount >= spdCount and visCount >= resCount:
        response = visSpecial(participant, visCount)
    
    if response == "" and resCount >= intCount and resCount >= spdCount and resCount >= visCount:
        resSpecial(participant, resCount)

def intSpecial(participant,count):
    print(f"{participant.player.name} enacts master plan (max {count} cards)")
    handCards = GameCard.objects.filter(game_id=participant.getGame().id, user_id=participant.id, state__lane=0)
    random.shuffle(handCards)
    for i in range(min(count,len(handCards))):
        newCard = handCards[i]
        participant.playCard(newCard.id,flipFaceUp=True, specialClause=True)

def spdSpecial(participant,speed, power, opponentId = None):
    opponent = participant.getGame().history.participants.exclude(id=participant.id).filter(defeated=False, fled=False).first()
    if opponentId is not None:
        opponent = participant.getGame().history.participants.get(id=opponentId) #todo overwrite with chosen opponent
    opponentInt, opponentSpd, opponentVis, opponentRes, opponentTactics, opponentPower, opponentInfluence = opponent.getStats()
    
    if opponentPower < power:
        print(f"{participant.player.name} rushes down {opponent.player.name}")
        specialActions(opponent)
    else:
        if opponentSpd < speed:
            print(f"{participant.player.name} flees from {opponent.player.name} and steals a card")
            participant.flee()
            return f"{participant.id} fled from {opponent.id}"
        else:
            print(f"{participant.player.name} fails to flee from {opponent.player.name}")
            #todo maybe have the slower participants lose these participant and oppopent?
    return ""

def visSpecial(participant,visciouisness, opponentId = None):
    #attack opponent
    opponent = participant.getGame().history.participants.exclude(id=participant.id).filter(defeated=False, fled=False).first()
    if opponentId is not None:
        opponent = participant.getGame().history.participants.get(id=opponentId) #todo overwrite with chosen opponent
    opponentInt, opponentSpd, opponentVis, opponentRes, opponentTactics, opponentPower, opponentInfluence = opponent.getStats()
    
    #attacking player needs a res card to trust in order to follow through with the attack
    newTrustedResCard = None
    newTrustedResCards = getTrustableCards(participant,[4])
    if len(newTrustedResCards) > 0:  
        newTrustedResCard = newTrustedResCards[0]
    if newTrustedResCard is None:
        response = f"{participant.player.name} drains the last of their resolve and is defeated"
        print(response)
        #lose
        participant.defeated = True
        participant.save()
        return response
    elif opponentRes < visciouisness:
        response = f"{participant.player.name} attacks and defeats {opponent.player.name} ({visciouisness} > {opponentRes})"
        print(response)
        #win
        opponent.defeated = True
        opponent.save()
    else:
        response = f"{participant.player.name} attacks {opponent.player.name} unsuccesfully ({visciouisness} <= {opponentRes})"
        print(response)
        response = ""
    newTrustedResCard.state.trust()
    newTrustedResCard.state.save()
    return response

def resSpecial(participant,count):
    print(f"{participant.player.name} holds and trusts up to {count} cards")
    newCards = getTrustableCards(participant)
    if newCards == None or len(newCards) < 1:
        return
    random.shuffle(newCards)
    for i in range(min(count,len(newCards))):
        newCard = newCards[i]
        newCard.state.trust()
        newCard.state.save()

def getTrustableCards(participant,laneNumbers = [1,2,3,4]):
    trustableCards = []
    for laneNumber in laneNumbers:
        laneCards = GameCard.objects.filter(game_id=participant.getGame().id, user_id=participant.id, state__lane=laneNumber, state__trusted=False, state__faceDown=False ).order_by("state__laneOrdinal")
        trustableCards += laneCards
    if trustableCards is None: return None
    return trustableCards

def viewResult(request, game_id, player_id):
    game = Game.objects.get(pk=game_id)
    current_participant = game.history.participants.get(player_id=player_id)
    finished, win, last_participants = _game_result(game)
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
    Game.objects.all().delete()
    BattleHistory.objects.all().delete()
    BattleParticipant.objects.all().delete()
    GameCard.objects.all().delete()
    CardState.objects.all().delete()
    Deck.objects.all().delete()
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
    for cookie in request.COOKIES:
        if cookie != "sessionid" and cookie != "csrftoken":
            if not request.COOKIES[cookie]:
                continue
            if not cookie.isdigit():
                continue
            payload = _parse_play_cookie_value(request.COOKIES[cookie])
            plays.append(
                {
                    "cardId": cookie,
                    "participantId": _get_play_cookie_participant_id(game, cookie),
                    "laneValue": payload["laneValue"],
                    "sourceLane": payload["sourceLane"],
                    "sourceOrdinal": payload["sourceOrdinal"],
                    "flipFaceUp": payload["flipFaceUp"],
                }
            )
    context["plays"] = plays
    print(f"Updating loading animations for plays: {plays} at {request.path}")
    context["handCards"] = _update_moved_hand_cards(context["handCards"], plays)
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
    return context


def _get_play_cookie_participant_id(game, card_id):
    if game is None:
        return None
    try:
        game_card = GameCard.objects.only("user_id").get(game_id=game.id, pk=int(card_id))
    except (GameCard.DoesNotExist, ValueError):
        return None
    return game_card.user_id


def _parse_play_cookie_value(cookie_value):
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

    flipFaceUp = decoded_value.endswith("f")
    lane_value = decoded_value[:-1] if flipFaceUp else decoded_value
    return {
        "laneValue": int(lane_value or 0),
        "sourceLane": None,
        "sourceOrdinal": None,
        "flipFaceUp": flipFaceUp,
    }

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

def _game_result(game, force_end=False):
    participants = list(game.history.participants.all())
    if not participants:
        return False,False, None

    active_participants = [p for p in participants if not p.defeated and not p.fled]
    if len(active_participants) == 1:
        others = [other for other in participants if other.fled]
        return True, len(others) < len(participants)-1, active_participants
    elif len(active_participants) >1: 
        return force_end, True, active_participants
    else:
        return True, True, None
    return False, False, None


def _ensure_game_initialized(game):
    for participant in game.history.participants.all():
        participant.startWithDeckInRandomOrder(initializeStartingCard=True)
    if game.roundNumber < 1:
        game.roundNumber = 1
        game.save(update_fields=["roundNumber"])


def _run_bot_turn(game, human_player_id):
    #todo add potential action for bot to flip over faceDown cards in lane
    bot_participants = game.history.participants.exclude(player_id=human_player_id).filter(computerControlled=True)
    bot_actions = []
    for bot_participant in bot_participants:
        hand_card = (
            GameCard.objects.filter(game_id=game.id, user_id=bot_participant.id, state__lane=0)
            .select_related("card")
            .first()
        )
        if hand_card is None:
            next_deck_card = bot_participant.getNextDeckCard()
            if bot_participant.drawCard() is not None:
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
                if bot_participant.getNextDeckCard() is None:
                    specialActions(bot_participant)
                    bot_participant.shuffleBoard()
            # Re-check for hand cards after drawing
            hand_card = (
                GameCard.objects.filter(game_id=game.id, user_id=bot_participant.id, state__lane=0)
                .select_related("card")
                .first()
            )
        if hand_card is not None:
            source_lane = hand_card.state.lane
            source_ordinal = hand_card.state.laneOrdinal
            played_card = bot_participant.playCard(hand_card.id, flipFaceUp=True)
            # played card moved hand -> lane (and possibly flipped)
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
    return bot_actions


def newBoard():
    board = {
        "handCards": [],
        "handCount": 0,
        "laneRows": [
            {"name": "Intelligence", "cards": [], "trustedCards": []}, 
            {"name": "Speed", "cards": [], "trustedCards": []}, 
            {"name": "Visciousness", "cards": [], "trustedCards": []},
            {"name": "Resolve", "cards": [], "trustedCards": []}
        ],
        "deckCount": 0,
        "deckStack": [],
    }
    return board

def contextBoard(gameCards, user_id):
    userCards = [gameCard for gameCard in gameCards if gameCard.user_id == user_id]
    handCards = [gameCard for gameCard in userCards if gameCard.state.lane == 0]
    intelligenceCards = [gameCard for gameCard in userCards if gameCard.state.lane == 1]
    speedCards = [gameCard for gameCard in userCards if gameCard.state.lane == 2]
    visciousnessCards = [gameCard for gameCard in userCards if gameCard.state.lane == 3]
    resolveCards = [gameCard for gameCard in userCards if gameCard.state.lane == 4]
    deckCards = [gameCard for gameCard in userCards if gameCard.state.inDeck == True]

    board = {
        "handCards": handCards,
        "handCount": len(handCards),
        "laneRows": [{"name": "Intelligence", "value": len([revealedCard for revealedCard in intelligenceCards if not revealedCard.state.faceDown]), "cards": [card for card in intelligenceCards if card.state.trusted == False], "trustedCards": [card for card in intelligenceCards if card.state.trusted == True]},
        {"name": "Speed", "value": len([revealedCard for revealedCard in speedCards if not revealedCard.state.faceDown]), "cards": [card for card in speedCards if card.state.trusted == False], "trustedCards": [card for card in speedCards if card.state.trusted == True]}, 
        {"name": "Visciousness", "value": len([revealedCard for revealedCard in visciousnessCards if not revealedCard.state.faceDown]), "cards": [card for card in visciousnessCards if card.state.trusted == False], "trustedCards": [card for card in visciousnessCards if card.state.trusted == True]}, 
        {"name": "Resolve", "value": len([revealedCard for revealedCard in resolveCards if not revealedCard.state.faceDown]), "cards": [card for card in resolveCards if card.state.trusted == False], "trustedCards": [card for card in resolveCards if card.state.trusted == True]}],
        "deckCount": len(deckCards),
        "deckStack": deckCards,
    }
    return board
