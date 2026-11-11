import random

from .battle_services import game_outcome
from .models import BattleHistory, Deck, Game, Player

DEMO_DECK_CARD_COUNT = 10
ANNABEL_NAME = "Annabel"
LUCAS_NAME = "Lucas"
DEMO_DECK_DESCRIPTION = f"ten cards from {LUCAS_NAME}'s collection"
TEAM_BOTS = {
    "Owlbears": "Lucasbot",
    "Hunters": "Annabelbot",
}


def demo_player(name):
    return Player.objects.filter(name=name).first() or Player.objects.create(name=name)


def team_player(team_name):
    if team_name not in TEAM_BOTS:
        raise Exception(f"{team_name} is not one of the demo teams {list(TEAM_BOTS)}")
    return demo_player(team_name)


def team_bot(team_player):
    bot_name = TEAM_BOTS.get(team_player.name)
    if bot_name is None:
        raise Exception(f"no demo bot mapping for team player {team_player.name}")
    return demo_player(bot_name)


def lucas_collection_cards():
    cards = demo_player(LUCAS_NAME).getCollection()
    if len(cards) < DEMO_DECK_CARD_COUNT:
        raise Exception(
            f"{LUCAS_NAME}'s collection holds {len(cards)} cards, demo decks need "
            f"at least {DEMO_DECK_CARD_COUNT} cards from {LUCAS_NAME}'s collection"
        )
    return cards


def fresh_demo_deck(player):
    cards = random.sample(lucas_collection_cards(), DEMO_DECK_CARD_COUNT)
    return Deck.create(
        player_id=player.id,
        deckTitle=f"{player.name}'s demo deck",
        newDescription=DEMO_DECK_DESCRIPTION,
        newDeckCards=cards,
    )


def latest_demo_deck(player):
    return player.deck_set.order_by("-id").first()


def latest_unfinished_participant_game(player):
    games = (
        Game.objects.filter(history__participants__player=player)
        .distinct()
        .order_by("-id")
    )
    for game in games:
        if not game_outcome(game)[0]:
            return game
    return None


def create_demo_scenario(human_player, bot_player, title):
    human_deck = latest_demo_deck(human_player) or fresh_demo_deck(human_player)
    human_starting_card = random.choice(list(human_deck.cards.all()))
    bot_deck = fresh_demo_deck(bot_player)
    bot_starting_card = random.choice(list(bot_deck.cards.all()))

    game = Game.createHumanChallenge(human_player.id)
    game.title = title
    game.save()
    game.history.addHumanChallenger(human_player.id, human_starting_card.id, human_deck.id)
    game.history.addRobotChallenger(bot_player.id, bot_starting_card.id, bot_deck.id)
    return game


def open_demo_scenario(human_player, bot_player, title):
    game = latest_unfinished_participant_game(human_player)
    if game is None:
        game = create_demo_scenario(human_player, bot_player, title)
    return game


def anonymous_scenario():
    annabel = demo_player(ANNABEL_NAME)
    lucas = demo_player(LUCAS_NAME)
    game = open_demo_scenario(annabel, lucas, f"{ANNABEL_NAME} vs {LUCAS_NAME}")
    return annabel, game


def team_scenario(team_player):
    bot_player = team_bot(team_player)
    return open_demo_scenario(team_player, bot_player, f"{team_player.name} vs {bot_player.name}")
