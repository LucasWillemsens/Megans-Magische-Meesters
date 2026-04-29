import datetime
import enum
from django.db import models
from django.utils import timezone

import random

# #main game classes

class CardType(enum.Enum):
    Intelligence = 0, #brainpower Ψ ψ
    Speed = 1, #bodily abillity
    Viciousness = 2, #danger level
    Resolve = 3 #at what cost?

laneWidth = 22
laneTypes = [lane.name for lane in CardType]

class Player(models.Model):
    name = models.CharField(max_length=200)
    profilePictureSource = models.CharField(max_length=200, default="")

    #get a list of all cards this player ever owned
    def getKnownCards(self):
        ownerHistories = CardOwnerHistory.objects.filter(cardOwner_id=self.id).all()
        cards = []
        for ownerHistory in ownerHistories:
            if ownerHistory.card.all():
                for card in ownerHistory.card.all():
                    cards.append(card)
        return list(set(cards))

    #get a list of all cards this player ever owned
    def getCollection(self):
        cards = []
        for card in self.getKnownCards(): #should be unique set of all owned cards
            if card.isCurrentlyOwnedBy(self.id):
                cards.append(card)
        return cards #todo check if this works

    def __str__(self):
        return f"{self.name}"


#special attributes of cards
class Symbol(models.Model):
    iconName = models.CharField(max_length=200)
    effectDescription = models.CharField(max_length=400)

    def __str__(self):
        return f"{self.iconName} - {self.effectDescription[:20]}.."

class CardOwnerHistory(models.Model):
    cardOwner = models.ForeignKey(Player, on_delete=models.CASCADE)
    aquiredAt = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.cardOwner.name} at {self.aquiredAt}"

class Card(models.Model):
    title = models.CharField(max_length=200)
    artSource = models.CharField(max_length=200)
    cardType = models.IntegerField(default=-1)
    symbols = models.ManyToManyField(Symbol, related_name="onCards") 
    ownerHistory = models.ManyToManyField(CardOwnerHistory, related_name="card")

    def __str__(self):
        return f"{self.title} - {laneTypes[self.cardType]}"

    def getLatestOwner(self):
        return self.ownerHistory.order_by("-aquiredAt").all()[0]

    def isCurrentlyOwnedBy(self, player_id):
        cardOwner = self.getLatestOwner().cardOwner
        return cardOwner.id == player_id

#a collection of cards
class Deck(models.Model):
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=200)
    artSource = models.CharField(max_length=200, default="")
    cards = models.ManyToManyField(Card, related_name="inDecks")
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    #by default adds all cards a player currently owns
    @classmethod
    def create(cls, player_id, deckTitle="", newDescription="", newDeckCards=None):
        playerOwner = Player.objects.get(pk=player_id)
        if newDeckCards is None:
            newDeckCards = playerOwner.getCollection()
        if deckTitle == "": deckTitle = f"{playerOwner.name}'s new deck"
        if newDescription == "": newDescription = f"all cards of {playerOwner.name}"
        newDeck =  cls(title=deckTitle, player=playerOwner, description=newDescription)
        newDeck.save()
        newDeck.cards.set(list(newDeckCards))
        newDeck.save()
        return newDeck 

    def __str__(self):
        if self.cards:
            return f"{self.title} ({self.cards.count()} cards) - {self.description}"
        else:
            return f"{self.title} - {self.description}"

    def available(self):
        for card in self.cards.all():
            lastOwner = card.ownerHistory.order_by("-aquiredAt").all()[0]

            #not currently owned
            if lastOwner.cardOwner.id != self.player.id: return False

            #currently in use
            if GameCard.objects.filter(card_id=card.id).exists():
                return False
        return True

#games

class BattleParticipant(models.Model): #1-to-1 with player, battlehistory and cards 
    player = models.ForeignKey(Player, on_delete=models.CASCADE) #battler
    startingCard = models.ForeignKey(Card, on_delete=models.CASCADE)
    deck = models.ForeignKey(Deck, on_delete=models.CASCADE)
    # ManyToManyField(Deck, related_name="usedBy")
    joinedBattle = models.DateTimeField(default=timezone.now)
    fled = models.BooleanField()
    defeated = models.BooleanField()
    computerControlled = models.BooleanField(default=True)
    #TODO could add a "board per round snapshot" as a log

    @classmethod
    def createRandomDeck(cls, player_id, starting_card_id=-1, deck_label="random deck"):
        player = Player.objects.get(pk=player_id)
        collection = list(player.getCollection())
        if not collection:
            raise Exception("player has no cards in collection")

        if starting_card_id < 0:
            starting_card = random.choice(collection)
        else:
            starting_card = next((card for card in collection if card.id == starting_card_id), None)
            if starting_card is None:
                raise Exception("starting card not in player collection")

        remaining_cards = [card for card in collection if card.id != starting_card.id]
        random.shuffle(remaining_cards)
        if remaining_cards:
            remaining_cards = remaining_cards[: random.randint(1, len(remaining_cards))]

        timestamp = timezone.now().strftime("%d %B %Y %H:%M")
        deck = Deck.create(
            player_id=player_id,
            deckTitle=f"{player.name}'s {deck_label} {timestamp}",
            newDescription=f"random subset of {player.name}'s collection",
            newDeckCards=[starting_card] + remaining_cards,
        )
        return starting_card, deck

    @classmethod
    def createRobot(cls, player_id, startingCard_id=-1, deck_id=-1):
        if deck_id < 0:
            startingCard, deck = cls.createRandomDeck(
                player_id=player_id,
                starting_card_id=startingCard_id,
                deck_label="auto deck",
            )
            startingCard_id = startingCard.id
            deck_id = deck.id
        elif startingCard_id < 0:
            deck = Deck.objects.get(pk=deck_id)
            firstDeckCard = deck.cards.first()
            if firstDeckCard is None:
                raise Exception("robot deck has no cards")
            startingCard_id = firstDeckCard.id
        return cls(
            player_id=player_id,
            startingCard_id=startingCard_id,
            deck_id=deck_id,
            joinedBattle=timezone.now(),
            fled=False,
            defeated=False,
            computerControlled=True,
        )

    @classmethod
    def createHuman(cls, player_id, startingCard_id, deck_id):
        return cls(
            player_id=player_id,
            startingCard_id=startingCard_id,
            deck_id=deck_id,
            joinedBattle=timezone.now(),
            fled=False,
            defeated=False,
            computerControlled=False,
        )

    def __str__(self):
        return f"{self.player.name} (f:{self.fled}, d:{self.defeated}, j{self.joinedBattle})"

    def getGame(self):
        battle = self.battles.all()[0]
        return battle.game.all()[0]
    
    #takes a pre-made deck and creates a random order, initialising all gamecards
    def startWithDeckInRandomOrder(self, initializeStartingCard = False):
        game_id = self.getGame().id
        #todo remove bandaid: make it so this button is never reachable for this condition
        existingGameCards = list(
            GameCard.objects.filter(game_id=game_id, user_id=self.id).select_related("card", "state")
        )
        # print(f"existing game cards for participant {self.id} in game {game_id}: {existingGameCards}, self.startingCard_id: {self.startingCard_id}, selected deck: {self.deck}" )
        if existingGameCards: return (gameCard for gameCard in existingGameCards if gameCard.card_id == self.startingCard_id), existingGameCards

        #order of deck not selected yet, game must be initialized
        randomOrderDeck = list(self.deck.cards.all())

        #no starting card selected yet
        if initializeStartingCard and not any(card.id == self.startingCard_id for card in randomOrderDeck):
            randomOrderDeck.append(self.startingCard)
        random.shuffle(randomOrderDeck)

        createdGameCards = []
        startCard = None
        deckPosition = 1
        for deckCard in randomOrderDeck:
            if initializeStartingCard and deckCard.id == self.startingCard_id and startCard is None:
                startCard = GameCard.create(self.startingCard_id, game_id, self.id)
                startCard.save()
                startCard.state.draw()
                startCard.state.play(startCard.card.cardType + 1)
                startCard.state.reveal()
                startCard.state.trust()
                startCard.state.save()
                createdGameCards.append(startCard)
                continue

            newGameCard = GameCard.create(deckCard.id, game_id, self.id)
            newGameCard.save()
            newGameCard.state.inDeck = True
            newGameCard.state.lane = deckPosition * -1
            newGameCard.state.laneOrdinal = 0
            newGameCard.state.faceDown = True
            newGameCard.state.trusted = False
            newGameCard.state.save()
            deckPosition += 1
            createdGameCards.append(newGameCard)

        if initializeStartingCard and startCard is None:
            raise Exception("starting card failed to initialize")
        return startCard, createdGameCards

    def getNewMaxCardInHandOrdinal(self):
        handCards = GameCard.objects.filter(game_id=self.getGame().id, user_id=self.id, state__lane=0).all()
        if not handCards:
            return 1
        return max(gameCard.state.laneOrdinal for gameCard in handCards) +1

    def getNewMaxCardInLaneOrdinal(self, lane:int):
        laneCards = GameCard.objects.filter(game_id=self.getGame().id, user_id=self.id, state__lane=lane).all()
        if not laneCards:
            return 1
        return max(gameCard.state.laneOrdinal for gameCard in laneCards)+1

    def getNextDeckCard(self):
        return (
            GameCard.objects.filter(
                game_id=self.getGame().id,
                user_id=self.id,
                state__inDeck=True,
            )
            .select_related("state", "card")
            .order_by("-state__lane", "id")
            .first()
        )

    def drawCard(self):
        gameCard = self.getNextDeckCard()
        if gameCard is None:
            return None

        newOrdinal = self.getNewMaxCardInHandOrdinal()
        gameCard.state.draw()
        gameCard.state.updateOrdinal(newOrdinal)
        gameCard.state.save(update_fields=["lane", "inDeck", "laneOrdinal"])
        return gameCard

    def playCard(self, game_card_id, lane=None):
        gameCard = GameCard.objects.select_related("state", "card").get(
            pk=game_card_id,
            game_id=self.getGame().id,
            user_id=self.id,
        )
        if lane is None:
            lane = gameCard.card.cardType + 1
        if lane < 1 or lane > 4:
            raise Exception("invalid lane selected")

        gameCard.state.play(lane)
        gameCard.state.updateOrdinal(self.getNewMaxCardInLaneOrdinal(lane))
        gameCard.state.save(update_fields=["lane", "laneOrdinal"])
        return gameCard

class BattleHistory(models.Model):
    challenger = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="challenges") #the participant matching the player_id is used for data
    participants = models.ManyToManyField(BattleParticipant, related_name="battles")
    # started: time of first participant join is the start time

    #cards that will we be handed to the final  
    lootPile = models.ManyToManyField(Card, related_name="wonIn") 
    
    def __str__(self):
        return f"{self.challenger.name} vs {self.participants.all().count()}-1 others"
    
    def printLootPile(self):
        lootPile = [loot.title for loot in self.lootPile.all()]
        return str.join(",",lootPile)

    def addHumanChallenger(self, challengerPlayer_id, startingCard_id = -1, deck_id=-1):
        existingParticipant = self.participants.filter(player_id=challengerPlayer_id).first()
        if existingParticipant is not None:
            return existingParticipant

        if deck_id < 0:
            starting_card, random_deck = BattleParticipant.createRandomDeck(
                player_id=challengerPlayer_id,
                starting_card_id=startingCard_id,
                deck_label="random deck",
            )
            startingCard_id = starting_card.id
            deck_id = random_deck.id
        else:
            if startingCard_id < 0:
                raise Exception("starting card required for predefined deck")
            deck = Deck.objects.get(pk=deck_id)
            startingCard = Card.objects.get(pk=startingCard_id)
            if not deck.cards.filter(pk=startingCard_id).exists():
                deck.cards.add(startingCard)

        challengerPlayer = BattleParticipant.createHuman(
            player_id=challengerPlayer_id,
            startingCard_id=startingCard_id,
            deck_id=deck_id,
        )
        challengerPlayer.save()
        self.participants.add(challengerPlayer)
        startCard = Card.objects.get(pk=startingCard_id)
        self.lootPile.add(startCard)
        self.save()
        return challengerPlayer

    def addRobotChallenger(self, challengerPlayer_id, startingCard_id=-1, deck_id=-1):
        existingParticipant = self.participants.filter(player_id=challengerPlayer_id).first()
        if existingParticipant is not None:
            return existingParticipant

        challengerPlayer = BattleParticipant.createRobot(player_id=challengerPlayer_id, startingCard_id=startingCard_id, deck_id=deck_id)
        challengerPlayer.save()
        self.participants.add(challengerPlayer)
        startCard = challengerPlayer.startingCard
        self.lootPile.add(startCard)
        self.save()
        return challengerPlayer

    @classmethod
    def create(cls, challengerPlayer_id):
        return cls(challenger_id=challengerPlayer_id)


#the master object. GameCards linked to this game are removed after game is completed
class Game(models.Model):
    title = models.CharField(max_length=200, default="error")
    artSource = models.CharField(max_length=200, default="")
    #stores all player info, start time and loot
    history = models.ForeignKey(BattleHistory, on_delete=models.CASCADE, related_name="game")
    #players take turns in the order that they join the game
    roundNumber = models.IntegerField(default=-1) 
    freeForAll = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title}{self.id} - round {self.roundNumber}\n{self.history.challenger.name} vs {self.history.participants.all().count()}-1 others"

    @classmethod
    def createHumanChallenge(cls, player_id):
        newGameHistory = BattleHistory.create(challengerPlayer_id=player_id)
        newGameHistory.save()
        return cls(history_id=newGameHistory.id, title="new challenge")

    def initialized(self):
        if not self.freeForAll: raise Exception("not implemented")
        return self.history.participants.exclude(pk__isnull=True).exists()

    def over(self):
        if not self.freeForAll: raise Exception("not implemented")
        if not self.history.participants.filter(fled=True,defeated=True).exists(): return False
            # raise Exception("no one has lost yet")
        playersStillGaming = self.history.participants.filter(fled=False,defeated=False).all()
        return playersStillGaming.count() <= 1


# models for gamestate and battles in progress
#   when a card is in play, it has a certain state described by this class
#   basically -> draw() = not inDeck -> play() = lane > 0 -> reveal() = not faceDown -> trust() = trusted
class CardState(models.Model):
    inDeck = models.BooleanField(default=True)
    lane = models.IntegerField(default=-1) 
    laneOrdinal = models.PositiveIntegerField(default=0)
    faceDown = models.BooleanField(default=True)
    trusted = models.BooleanField(default=False)

    def reset(self):
        self.inDeck = True 
        self.lane = -1 #-1: default state unordered in deck. 0 (in hand) or < -1 (order in deck), else in play
        self.laneOrdinal = 0
        self.faceDown = True
        self.trusted = False

    def draw(self):
        if (not self.inDeck or not self.lane <= -1):
            raise Exception("in play")
        self.lane = 0
        self.inDeck = False

    def updateOrdinal(self, numberInLaneOrHand:int):
        if (self.inDeck or self.lane < 0):
            self.laneOrdinal = 0
        else: self.laneOrdinal = numberInLaneOrHand

    def shuffleBack(self):
        if (self.inDeck): 
            raise Exception("inDeck")
        if (self.faceDown): 
            raise Exception("faceDown")
        if (self.trusted): 
            raise Exception("trusted")
        self.reset()
    
    def changeLane(self, lane:int, playClause:bool=False):
        if (lane < 1 or lane > 4 ): 
            raise Exception(f"invalid lane argument: {lane}")
        if (self.inDeck): 
            raise Exception("inDeck")
        if ((self.lane < 0 or self.lane > 4) or (self.lane == 0 and not playClause)):
            raise Exception(f"invalid lane state: {self.lane}")
        if (self.faceDown and not playClause): 
            raise Exception("faceDown")
        if (self.trusted): 
            raise Exception("trusted")
        self.lane = lane

    def play(self, lane:int):
        if (self.lane != 0): 
            raise Exception("not in hand")
        self.changeLane(lane, playClause=True)
    
    def reveal(self):
        if (self.inDeck): 
            raise Exception("inDeck")
        if (self.lane < 1 or self.lane > 4): 
            raise Exception("invalid lane")
        if (not self.faceDown): 
            raise Exception("not faceDown")
        if (self.trusted): 
            raise Exception("trusted")
        self.faceDown = False
    
    def trust(self):
        if (self.inDeck): 
            raise Exception("inDeck")
        if (self.lane < 1 or self.lane > 4): 
            raise Exception("invalid lane")
        if (self.faceDown): 
            raise Exception("faceDown")
        if (self.trusted): 
            raise Exception("trusted")
        self.trusted = True

    @classmethod
    def create(cls):
        return cls()

#a card in play. Only one gamecard per card possible, gets deleted after game is complete
class GameCard(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="inGame")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="gameCards")
    user = models.ForeignKey(BattleParticipant,on_delete=models.CASCADE, related_name="usingCards")
    state = models.ForeignKey(CardState, on_delete=models.CASCADE, related_name="cardsInState") #strange relation back
    cssClass = models.CharField(max_length=200, default="")

    @classmethod
    def create(cls, card_id, game_id, battleParticipant_id):
        newGameCardState = CardState.create()
        newGameCardState.save()
        return cls(card_id=card_id, game_id=game_id,user_id=battleParticipant_id,state=newGameCardState)
