# mysite.jinja2.

from jinja2 import Environment
# from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static
from django.urls import reverse

from django.utils.timezone import localtime

def printLocalTime(dateTimeValue):
    return localtime(dateTimeValue).strftime("%d %B %Y %H:%M")

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
        "playing_card_rank_class": playing_card_rank_class,
        "playing_card_rank_display": playing_card_rank_display,
        "playing_card_suit_class": playing_card_suit_class,
        "playing_card_suit_display": playing_card_suit_display,
        "playing_card_default_name": playing_card_default_name,
    })
    return env


# ── Playing card helpers ──────────────────────────────────────────
# These filters generate CSS Playing Cards framework classes and
# display text from a Card (or GameCard.card) model instance.

_RANK_CLASSES = [
    "rank-2", "rank-3", "rank-4", "rank-5", "rank-6", "rank-7",
    "rank-8", "rank-9", "rank-10", "rank-j", "rank-q", "rank-k",
    "rank-a",
]
_RANK_DISPLAY = [
    "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A",
]
_RANK_NAMES = [
    "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Jack", "Queen", "King", "Ace",
]
_SUIT_MAP = [
    {"class": "clubs",  "symbol": "\u2663", "name": "Clubs"},      # Intelligence
    {"class": "spades", "symbol": "\u2660", "name": "Spades"},     # Speed
    {"class": "diams",  "symbol": "\u2666", "name": "Diamonds"},   # Viciousness
    {"class": "hearts", "symbol": "\u2665", "name": "Hearts"},     # Resolve
]


def playing_card_rank_class(card):
    """Return CSS rank class (e.g. 'rank-j') based on card.id % 13."""
    return _RANK_CLASSES[card.id % 13]


def playing_card_rank_display(card):
    """Return rank display text (e.g. 'J') based on card.id % 13."""
    return _RANK_DISPLAY[card.id % 13]


def playing_card_suit_class(card):
    """Return CSS suit class (e.g. 'spades', 'diams') based on card.cardType."""
    return _SUIT_MAP[card.cardType]["class"]


def playing_card_suit_display(card):
    """Return suit symbol (e.g. '♠', '♦') based on card.cardType."""
    return _SUIT_MAP[card.cardType]["symbol"]


def playing_card_default_name(card):
    """Return a generated default name like 'Jack of Spades' or 'Three of Clubs'."""
    rank_name = _RANK_NAMES[card.id % 13]
    suit_name = _SUIT_MAP[card.cardType]["name"]
    return f"{rank_name} of {suit_name}"