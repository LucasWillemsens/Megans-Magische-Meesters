# mysite.jinja2.

from jinja2 import Environment
# from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static
from django.urls import reverse

from django.utils.timezone import localtime

RANK_NAMES = ['Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Jack', 'Queen', 'King', 'Ace']
RANK_ABBREV = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
SUIT_SYMBOLS = ['♣', '♠', '♦', '♥']

_rank_map = dict(zip(RANK_NAMES, RANK_ABBREV))

def printLocalTime(dateTimeValue):
    return localtime(dateTimeValue).strftime("%d %B %Y %H:%M")

def playing_card_rank(title):
    """Convert 'Ace of Clubs' -> 'A', 'Ten of Spades' -> '10', etc."""
    rank_word = title.split(' of ')[0] if ' of ' in title else title
    return _rank_map.get(rank_word, '?')

def playing_card_suit_symbol(card_type):
    """Convert cardType (0-3) to suit symbol: Clubs, Spades, Diamonds, Hearts."""
    return SUIT_SYMBOLS[card_type] if 0 <= card_type < 4 else '?'

def environment(**options):
    env = Environment(**options)
    env.undefined="StrictUndefined"
    env.globals.update({
        # 'static': staticfiles_storage.url,
        'static': static,
        'url': reverse,
        "printLocalTime": printLocalTime,
    })
    env.filters.update({
        "playing_card_rank": playing_card_rank,
        "playing_card_suit_symbol": playing_card_suit_symbol,
    })
    return env
