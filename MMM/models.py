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
    def create(cls, player_id, deckTitle="",newDescription ="", newDeckCards = []):
        playerOwner = Player.objects.get(pk=player_id)
        if newDeckCards == []: newDeckCards = playerOwner.getCollection() 
        if deckTitle == "": deckTitle = f"{playerOwner.name}'s new deck"
        if newDescription == "": newDescription = f"all cards of {playerOwner.name}"
        newDeck =  cls(title=deckTitle, player=playerOwner, description=newDescription)
        newDeck.save()
        newDeck.cards.set(newDeckCards)
        newDeck.save()
        return newDeck 

    def __str__(self):
        if self.cards:
            return f"{self.title} ({self.cards.count()} cards) - {self.description}"
        else:
            return f"{self.title} - {self.description}"

    def available(self):
        for card in self.cards:
            lastOwner = card.ownerHistory.order_by("-aquiredAt").all()[0]

            #not currently owned
            if lastOwner.cardOwner.id != self.player.id: return False

            #currently in use
            if GameCard.objects.get(pk=card.id): return False
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
    def createRobot(cls, player_id, startingCard_id=-1, deck_id=-1):
        if deck_id < 0:
            startingCard, deck = self.newRandomDraft(startingCard_id < 0)
            startingCard_id = startingCard.id
            deck_id = deck.id
        return cls(player_id=player_id, startingCard_id=startingCard_id, deck_id=deck_id,joinedBattle=datetime.datetime.now(), fled=False,defeated=False, computerControlled=True)

    @classmethod
    def createHuman(cls, player_id, startingCard_id, deck_id):
        return cls(player_id=player_id, startingCard_id=startingCard_id,deck_id=deck_id, joinedBattle=datetime.datetime.now(), fled=False,defeated=False, computerControlled=False)

    def __str__(self):
        return f"{self.player.name} (f:{self.fled}, d:{self.defeated}, j{self.joinedBattle})"

    def getGame(self):
        battle = self.battles.all()[0]
        return battle.game.all()[0]

    def newRandomDraft(self, selectStartingCard = False):
        player = self.player
        randomCollection = player.getCollection()
        random.shuffle(randomCollection)
        maxSize = randomCollection.__len__()
        randint = random.randint(1,maxSize-1)
        randomDeckCards = []
        newDecksize = 0
        if selectStartingCard:
            randomCard = random.choice(randomCollection)
            randomDeckCards.append(randomCard)
            newDecksize += 1
        for card in randomCollection:
            if not selectStartingCard and card.id == self.startingCard.id: continue #skip startingCard in this case
            randomDeckCards.append(card)
            newDecksize += 1
            if newDecksize == randint: 
                deckTitle = f"{self.player.name[0:5]}'s randomDeck s{randint} d{datetime.datetime.now().strftime('%d %B %Y %H:%M')}"
                if selectStartingCard: deckTitle = f"{laneTypes[self.startingCard.cardType]} " + deckTitle
                randomDeck = Deck.create(self.player.id,deckTitle,f"random {randint} card subset of {self.player.name}'s entire collection ")
                if selectStartingCard: return randomCard, randomDeck
                else: return self.startingCard, randomDeck
        raise Exception(f"generated deck of size: {newDecksize} but failed to make it random size: {randint}")
    
    #takes a pre-made deck and creates a random order, initialising all gamecards
    def startWithDeckInRandomOrder(self, initializeStartingCard = False):
        size = self.deck.cards.all().count()
        game_id = self.getGame().id
        randomOrderDeck = list(self.deck.cards.all())
        random.shuffle(randomOrderDeck)
        for cardIndex in range(size):
            if randomOrderDeck[cardIndex].id == self.startingCard.id: 
                if initializeStartingCard:
                    startCard = GameCard.create(self.startingCard.id, game_id, self.id)
                    startCard.state.draw()
                    startCard.state.play(startCard.card.cardType+1)
                    startCard.state.reveal()
                    startCard.state.trust()
                    startCard.save()
            else:
                deckCard = GameCard.create(randomOrderDeck[cardIndex].id,game_id, self.id)
                deckCard.lane = (cardIndex+1) * -1 #order in deck
                deckCard.save()
                randomOrderDeck.append(deckCard)
        return startCard, randomOrderDeck

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
        if deck_id < 0:
            selectStartingCard = startingCard_id<0
            player = Player.objects.get(pk=challengerPlayer_id)
            randomCollection = player.getCollection()
            random.shuffle(randomCollection)
            maxSize = randomCollection.__len__()
            randint = random.randint(1,maxSize-1)
            randomDeckCards = []
            newDecksize = 0
            if selectStartingCard:
                randomCard = random.choice(randomCollection)
                randomDeckCards.append(randomCard)
                newDecksize += 1
            for card in randomCollection:
                if not selectStartingCard and card.id == startingCard_id: continue #skip startingCard in this case
                randomDeckCards.append(card)
                newDecksize += 1
                if newDecksize == randint: 
                    deckTitle = f"{player.name[0:5]}'s randomDeck s{randint} d{datetime.datetime.now().strftime('%d %B %Y %H:%M')}"
                    if selectStartingCard: deckTitle = f"{laneTypes[randomCard.cardType]} " + deckTitle
                    randomDeck = Deck.create(player.id,deckTitle,f"random {randint} card subset of {player.name}'s entire collection ")
                    break
            if selectStartingCard: startingCard_id = randomCard.id
            challengerPlayer = BattleParticipant.createHuman(player_id=challengerPlayer_id, startingCard_id=startingCard_id, deck_id=randomDeck.id)
        else: challengerPlayer = BattleParticipant.createHuman(player_id=challengerPlayer_id, startingCard_id=startingCard_id, deck_id=deck_id)
        challengerPlayer.save()
        self.participants.add(challengerPlayer)
        startCard = Card.objects.get(pk=startingCard_id)
        self.lootPile.add(startCard)
        self.save()

    def addRobotChallenger(self, challengerPlayer_id, startingCard_id=-1, deck_id=-1):
        challengerPlayer = BattleParticipant.createRobot(player_id=challengerPlayer_id, startingCard_id=startingCard_id, deck_id=deck_id)
        challengerPlayer.save()
        self.participants.add(challengerPlayer)
        if startingCard_id == -1:
            startCard =  challengerPlayer.player.getCollection()[0] 
        else: startCard = Card.objects.get(pk=startingCard_id)
        self.lootPile.add(startCard)
        self.save()

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
        return self.history.participants.exclude(pk_isnull=True).exists()

    def over(self):
        if not self.freeForAll: raise Exception("not implemented")
        playersStillGaming = self.history.participants.filter(fled=False,defeated=False).all()
        return playersStillGaming.count() == 1 and playersStillGaming[0].player != self.history.challenger.player


# models for gamestate and battles in progress
#   when a card is in play, it has a certain state described by this class
#   basically -> draw() = not inDeck -> play() = lane > 0 -> reveal() = not faceDown -> trust() = trusted
class CardState(models.Model):
    inDeck = models.BooleanField(default=True)
    lane = models.IntegerField(default=-1) 
    faceDown = models.BooleanField(default=True)
    trusted = models.BooleanField(default=False)

    def reset(self):
        self.inDeck = True 
        self.lane = -1 #-1: default state unordered in deck. 0 (in hand) or < -1 (order in deck), else in play
        self.faceDown = True
        self.trusted = False

    def draw(self):
        if (not self.inDeck or not self.lane <= -1):
            raise Exception("in play")
        # sanity checks: if (not self.inDeck or not self.faceDown or self.trusted): 
        self.lane = 0
        self.inDeck = False

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

    @classmethod
    def create(cls, card_id, game_id, battleParticipant_id):
        newGameCardState = CardState.create()
        newGameCardState.save()
        return cls(card_id=card_id, game_id=game_id,user_id=battleParticipant_id,state=newGameCardState)

# tutorial classes
class Question(models.Model):
    question_text = models.CharField(max_length=200)
    pub_date = models.DateTimeField("date published")

    def __str__(self):
        return f"({self.pub_date}){self.question_text}"

    def was_published_recently(self):
        return self.pub_date >= timezone.now() - datetime.timedelta(days=1)

class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choice_text = models.CharField(max_length=200)
    votes = models.IntegerField(default=0)
    
    def __str__(self):
        return f"({self.votes}){self.choice_text}"