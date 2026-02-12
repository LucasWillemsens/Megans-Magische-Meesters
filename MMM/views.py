from django.db.models import F
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.template import loader
from .models import *
from jinja2 import Template, StrictUndefined
import random

from django.utils import timezone

baseUrl = "http://127.0.0.1:8000/"
# assestsDir = "C:\\Users\\Lucas\\Documents\\Programmeren\\Megans Magische Meesters\\djangosite\\djangotutorial\\assets\downloaded"
#real: assestsDir = "C:/Users/Lucas/Documents/Programmeren/Megans Magische Meesters/djangosite/djangotutorial/MMM/static/MMM/"

#returns data used for button that does something to the id of the passed item
def niceButton(buttonItem, typeOf="",DoSomething=""):
    if (typeOf != ""): 
        href = f"{baseUrl}{typeOf}{buttonItem.id}/"
        returnURL = reverse(typeOf)
    else:
        href = f"{baseUrl}{buttonItem.id}/"
        returnURL = reverse("MMM:index")
    if (DoSomething != ""): href += f"{DoSomething}/"
    buttonData = {"object": buttonItem, "href": href, "type":"submit", "returnURL":returnURL}
    return buttonData


def index(request):
    latest_cards_list = Card.objects.order_by("title")[:5]
    players = Player.objects.order_by("name")[::]
    assestsDir = "MMM/"
    template = loader.get_template("MMM/index.html") #looks in jinja2 folder of app
    context = {"latest_cards_list": latest_cards_list,"players":players,"assestsDir":assestsDir,"landingPage":"http://127.0.0.1:8000/"}
    return HttpResponse(template.render(context, request))

def viewPlayer(request,player_id):
    player = Player.objects.get(pk=player_id)
    cardOwner = CardOwnerHistory.objects.filter(cardOwner_id=player.id)[0]
    battles = BattleParticipant.objects.filter(player_id=player.id)
    challenges = []
    for battle in battles:
        for challenge in battle.player.challenges.all():
            challenges.append(challenge)
    challenges = list(set(challenges))
    # BattleParticipant
    # decks_list = Card.objects.filter(usedBy=cardOwner.id)# order_by("title")[:5]
    #for each card, check if another player now owns the card and grey out the card with red letter LOST TO
    assestsDir = "MMM/"
    template = loader.get_template("MMM/viewPlayer.html") #looks in jinja2 folder of app
    context = {"player":player,"cardOwner":cardOwner,"challenges":challenges,"assestsDir":assestsDir,"returnURL":"http://127.0.0.1:8000/", "error_message":""}
    return HttpResponse(template.render(context, request))

def viewCard(request,card_id):
    card = Card.objects.get(pk=card_id)
    cardType = [lane.name for lane in CardType][card.cardType]
    cardOwners = card.ownerHistory.order_by("-aquiredAt").all()
    # symbols= Symbol.objects.filter(id in card.symbols)
    symbols = []
    assestsDir = "MMM/"
    template = loader.get_template("MMM/viewCard.html") #looks in jinja2 folder of app
    context = {"card":card,"cardType":cardType,"symbols":symbols,"assestsDir":assestsDir,"returnURL":"http://127.0.0.1:8000/", "error_message":""}
    return HttpResponse(template.render(context, request))

#generic read of game
def viewGame(request,game_id):
    game = Game.objects.get(pk=game_id) #roundNumber, history, freeForAll
    player = object()
    challenger = game.history.challenger 
    battlers = game.history.participants.all()
    assestsDir = "MMM/"
    template = loader.get_template("MMM/viewGame.html") #looks in jinja2 folder of app
    context = {"player_id":-1,"player":player,"game":game,"challenger":challenger,"battlers":battlers,"assestsDir":assestsDir,"submitUrl":"http://127.0.0.1:8000/game/","returnURL":"http://127.0.0.1:8000/", "error_message":""}
    return HttpResponse(template.render(context, request))

#read game as specific player
def viewGameAsPlayer(request,game_id, player_id):
    game = Game.objects.get(pk=game_id) #roundNumber, history, freeForAll
    challenger = game.history.challenger 
    battlers = game.history.participants.all()
    notInBattle = True
    for battler in battlers:
        if (battler.player_id == player_id):
            notInBattle = False
            player = battler.player
    if notInBattle:
        # return viewGame(request,game_id)
        raise Exception(f"player with id: {player_id} not in battle")
    assestsDir = "MMM/"
    template = loader.get_template("MMM/viewGame.html") #looks in jinja2 folder of app
    context = {"player_id":player_id,"player":player,"game":game,"challenger":challenger,"battlers":battlers,"assestsDir":assestsDir,"submitUrl":f"http://127.0.0.1:8000/game/{game.id}/{player_id}/confirm","returnURL":"http://127.0.0.1:8000/", "error_message":""}
    return HttpResponse(template.render(context, request))

def createGame(request,player_id):
    cardOwner = CardOwnerHistory.objects.filter(cardOwner_id=player_id)[0]
    decks = Deck.objects.filter(player_id=player_id)
    players = Player.objects.exclude(id=player_id).all()
    assestsDir = "MMM/"
    template = loader.get_template("MMM/createGame.html") #looks in jinja2 folder of app
    newGame = Game.createHumanChallenge(player_id=player_id)
    newGame.save()
    context = {"cardOwner":cardOwner,"newGameId":newGame.id,"decks":decks,"players":players,"assestsDir":assestsDir,"submitUrl":"http://127.0.0.1:8000/game/initialize/", "returnURL":f"{baseUrl}player/{player_id}/", "error_message":""}
    return HttpResponse(template.render(context, request))

#dev function to delete all games and history objects
def resetGames(request):
    # cardOwner = CardOwnerHistory.objects.filter(cardOwner_id=player_id)[0]
    Game.objects.all().delete()
    BattleHistory.objects.all().delete()
    BattleParticipant.objects.all().delete()
    GameCard.objects.all().delete()
    CardState.objects.all().delete()
    Deck.objects.all().delete()

    return redirect("/")

def initializeGame(request):
    newGameId = -1
    challengerId = -1
    challengeId = -1
    newGameStartingDeck = -1
    if request.method == "POST":
        newGameId = int(request.POST["newGameIdValue"])
        challengerId = int(request.POST["challenger"])
        challengeId = int(request.POST["challengePlayer"])
        newGameStartingDeck = request.POST["startingDeck"] #could be id or 'new'
        newGameStartingCard = int(request.POST["startingCard"])
    
    if (newGameStartingDeck == "New"):
        deck = Deck.create(player_id=challengerId)
    else:
        deck = Deck.objects.get(id=int(newGameStartingDeck))
        if not(int(newGameStartingCard) in [card.id for card in deck.cards.all()]): raise Exception("startingCard not in Deck")
    #add participant
    
    game = Game.objects.get(pk=newGameId)
    game.history.addHumanChallenger(challengerId, newGameStartingCard)
    
    return viewGameAsPlayer(request=request,game_id=newGameId, player_id=challengerId)

#read game as specific player
def viewBoard(request,game_id, player_id):
    game = Game.objects.get(pk=game_id) #roundNumber, history, freeForAll
    challenger = game.history.challenger 
    battlers = game.history.participants.all()
    cardsInHand = []
    notInBattle = True
    for battler in battlers:
        if (battler.player_id == player_id):
            notInBattle = False
            player = battler.player
            # load the cards currently in the players hand
            for gameCard in battler.usingCards.all():
                cardsInHand.append(gameCard.card)
                
                # # this currently selects all gamecards across all games
                # if battler.deck.contains(gameCard.Card) and gameCard.Card != battler.startingCard:

                #     #draw one card to start
                #     cardsInHand.append(gameCard.Card)
                #     gameCard.state.draw()
                #     break
    if notInBattle:
        # return viewGame(request,game_id)
        raise Exception(f"player with id: {player_id} not in battle")

    assestsDir = "MMM/"
    template = loader.get_template("MMM/battle/viewBoard.html") #looks in jinja2 folder of app
    context = {"player_id":player_id,"cardsInHand":cardsInHand,"player":player,"game":game,"challenger":challenger,"battlers":battlers,"assestsDir":assestsDir,"submitUrl":f"http://127.0.0.1:8000/game/{game.id}/{player_id}/confirm","returnURL":"http://127.0.0.1:8000/", "error_message":""}
    return HttpResponse(template.render(context, request))

#Also add a cancel challenge button that is disabled after confirmation

#currently does nothing really
#TODO add and send notification to other player. then start game and draw first hand
# will then wait on other player. Computer player joins automatically
def confirmChallenge(request,game_id, player_id):
    game = Game.objects.get(pk=game_id) #roundNumber, history, freeForAll
    challenger = game.history.challenger
    player = Player.objects.get(pk=player_id)
    battlers = game.history.participants.all()
    currentBattler = game.history.participants.filter(player_id=player_id).all()[0]

    checkboxShuffle=True
    #validate that challenger is participant 1 or that no prticipants exist yet
    #do something with log in
    assestsDir = "MMM/"
    template = loader.get_template("MMM/viewGame.html") #looks in jinja2 folder of app
    context = {"player_id":player_id,"player":player,"game":game,"challenger":challenger,"battlers":battlers,"assestsDir":assestsDir,"submitUrl":f"http://127.0.0.1:8000/game/{game.id}/{player_id}/confirm","returnURL":"http://127.0.0.1:8000/", "error_message":""}

    #lane is used for determining order in deck or (hand=0)
    if request.method == "POST":
        if checkboxShuffle:
            currentBattler.startWithDeckInRandomOrder(True)
            # shuffledDeck = currentBattler.deck.all()
            # random.shuffle(shuffledDeck)
            # #should check if original deck remains in same order
            # for cardNum in range(len(shuffledDeck)):
            #     gameCard = initializeGameCard(card,game=game,user=currentBattler)
            #     gameCard.lane = (cardNum+1) * -1
            #     gameCard.save()
    else:
        print("invalid request")
    #TODO something with trustedCard
    
    return viewBoard(request=request,game_id=game_id, player_id=player_id)

def initializeGameCard(card_id,game_id,battleParticipant_id):
    print()
    newGameCard = GameCard.create(card_id=card_id,game_id=game_id,battleParticipant_id=battleParticipant_id)
    newGameCard.save()
    print(f"gameCard initialised: {newGameCard}")
    return newGameCard
#TODO view logic:

# def presentCardToPlayer(card):
#     print(f"title: {card.title}  symbols:{[symbol for symbol in card.symbols]} \n{card.artSource}\ntype:{card.cardType.name}")

# # returns startingcard + unshuffled list of Cards in deck
# def draft(player):
#     newDeckCards = [] #cards
#     startingCard = False
#     print(f"hi {player.name}, please choose cards from your collection to put in your new deck:")
#     for card in player.collection:
#         presentCardToPlayer(card)
        
#         if startingCard:
#             inputchars = input("add? (y/n) :")
#         else:
#             inputchars = input("add? (y/n or s to use as starting card) :")

#         if inputchars.__len__() < 1: break
#         if inputchars[0] == "y":
#             newDeckCards.append(GameCard(card,player))
#             continue
#         elif inputchars[0] == "n":
#             continue
#         elif inputchars[0] == "s":
#             startingCard = GameCard(card,player)
#             startingCard.state.draw()
#             startingCard.state.play(laneTypes.index(startingCard.card.cardType.name))
#             startingCard.state.reveal()
#             startingCard.state.trust()
#             continue
#         elif inputchars[0] == "q":
#             # save()
#             break
#         else:
#             print(f"unkown chars {inputchars}")
#             break

#     if (startingCard):
#         return startingCard, newDeckCards
#     else:
#         raise Exception("no starting card")

#TODO create pages
    # path("<int:player_id>/history/", views.viewPlayerHistory, name="viewPlayerHistory"),
    # path("<int:player_id>/login/", views.loginPlayer, name="loginPlayer"),

    # path("<int:card_id>/", views.viewCard, name="viewCard"),
    # path("<int:symbol_id>/", views.viewSymbol, name="viewSymbol"),
    # path("<int:card_id>/history/", views.viewCardHistory, name="viewCardHistory"),