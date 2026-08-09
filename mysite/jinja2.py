# mysite.jinja2.

from jinja2 import Environment
# from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static
from django.urls import reverse

from django.utils.timezone import localtime


_RANK_CLASSES = (
    "rank-2", "rank-3", "rank-4", "rank-5", "rank-6", "rank-7",
    "rank-8", "rank-9", "rank-10", "rank-j", "rank-q", "rank-k", "rank-a",
)
_RANK_DISPLAY = (
    "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A",
)
_RANK_NAMES = (
    "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Jack", "Queen", "King", "Ace",
)
_RANK_INDEX_BY_NAME = {name: index for index, name in enumerate(_RANK_NAMES)}
_SUITS = (
    ("clubs", "\u2663", "Clubs"),
    ("spades", "\u2660", "Spades"),
    ("diams", "\u2666", "Diamonds"),
    ("hearts", "\u2665", "Hearts"),
)


def printLocalTime(dateTimeValue):
    return localtime(dateTimeValue).strftime("%d %B %Y %H:%M")


def _rank_index(card):
    title = getattr(card, "title", "")
    if isinstance(title, str) and " of " in title:
        rank_name = title.split(" of ", 1)[0]
        if rank_name in _RANK_INDEX_BY_NAME:
            return _RANK_INDEX_BY_NAME[rank_name]
    return int(card.id) % len(_RANK_CLASSES)


def _suit(card):
    return _SUITS[int(card.cardType)]


def playing_card_rank_class(card):
    """Return the CSS Playing Cards rank class for a Card instance."""
    return _RANK_CLASSES[_rank_index(card)]


def playing_card_rank_display(card):
    """Return the short rank shown in the top-left of a CSS card."""
    return _RANK_DISPLAY[_rank_index(card)]


def playing_card_suit_class(card):
    """Return the CSS Playing Cards suit class for a Card instance."""
    return _suit(card)[0]


def playing_card_suit_display(card):
    """Return the Unicode suit symbol shown in the top-left of a CSS card."""
    return _suit(card)[1]


def playing_card_default_name(card):
    """Return a readable generated name for a CSS-only playing card."""
    return f"{_RANK_NAMES[_rank_index(card)]} of {_suit(card)[2]}"


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
