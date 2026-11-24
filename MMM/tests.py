import importlib
import json
import os
import re
import sys
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from io import StringIO
from types import SimpleNamespace
from datetime import timedelta
from pathlib import Path
from unittest import mock

import mysite.settings

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from django.contrib.staticfiles import finders

from . import views
from . import battle_services
from . import api_docs
from .band_views import NEWS_ITEMS
from .demo_flow import (
    DEMO_DECK_CARD_COUNT,
    create_demo_scenario,
    demo_player,
)
from .demo_greetings import (
    GENERIC_GREETINGS,
    LOGGED_IN_NAME_GREETINGS,
    NEW_VISITOR_GREETING,
    applicable_title_greetings,
    title_greeting,
)
from .models import (
    BattleHistory,
    BattleParticipant,
    Card,
    CardOwnerHistory,
    CardState,
    Deck,
    Game,
    GameCard,
    Player,
)

STATIC_TEST_DIR = os.path.join(os.path.dirname(__file__), "..", "var", "www", "static")

ADMIN_ACCOUNT_EMAIL = "paintedpillars@gmail.com"


def _verified_account(username, email):
    """Create the rows a completed Google sign-in leaves behind: an auth
    user with the address the provider verified, and that verified email
    address itself."""
    user = get_user_model().objects.create_user(username=username, email=email)
    EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    return user

FAKE_ELEMENT_NAVIGATION_CORE = r'''const matchPart = (el, part) => {
    if (!el || !el.tagName) return false;
    const tagMatch = part.match(/^[a-zA-Z][\w-]*/);
    if (tagMatch && el.tagName.toLowerCase() !== tagMatch[0].toLowerCase()) return false;
    const idMatch = part.match(/#([\w-]+)/);
    if (idMatch && (el.id || '') !== idMatch[1]) return false;
    for (const cls of part.match(/\.([\w-]+)/g) || []) {
        if (!el.classList || !el.classList.contains(cls.slice(1))) return false;
    }
    const attrRe = /\[([\w-]+)(?:="([^"]*)")?\]/g;
    let match;
    while ((match = attrRe.exec(part))) {
        const value = el.getAttribute ? el.getAttribute(match[1]) : null;
        if (match[2] === undefined) {
            if (value === null) return false;
        } else if (String(value) !== match[2]) return false;
    }
    const notRe = /:not\(\.([\w-]+)\)/g;
    while ((match = notRe.exec(part))) {
        if (el.classList && el.classList.contains(match[1])) return false;
    }
    if (part.replace(/:not\([^)]*\)/g, '').includes(':')) return false;
    return true;
};

const matchChainFrom = (el, tokens) => {
    const last = tokens[tokens.length - 1];
    if (!matchPart(el, last.part)) return false;
    if (tokens.length === 1) return true;
    const rest = tokens.slice(0, -1);
    if (last.combinator === '>') {
        return Boolean(el.parentNode) && matchChainFrom(el.parentNode, rest);
    }
    let node = el.parentNode;
    while (node) {
        if (matchChainFrom(node, rest)) return true;
        node = node.parentNode;
    }
    return false;
};

const tokenizeChain = (chain) => {
    const tokens = [];
    const re = /(\s*>\s*|\s+)?([^>\s]+)/g;
    let match;
    while ((match = re.exec(chain)) !== null) {
        let combinator = null;
        if (match[1] && match[1].includes('>')) combinator = '>';
        else if (match[1] && match[1].trim() !== '') combinator = ' ';
        tokens.push({ part: match[2], combinator });
    }
    if (tokens.length > 0 && tokens[0].part === ':scope') {
        const [head, ...rest] = tokens;
        rest[0].combinator = '>';
        return rest;
    }
    return tokens;
};

const descendantsInOrder = (root) => {
    const result = [];
    const stack = [...root.children];
    while (stack.length) {
        const node = stack.shift();
        result.push(node);
        stack.unshift(...node.children);
    }
    return result;
};

class FakeElement {
    constructor(tag, className = '') {
        this.tagName = String(tag).toUpperCase();
        this.classes = new Set(String(className).split(/\s+/).filter(Boolean));
        this.attributes = new Map();
        this.dataset = {};
        this.children = [];
        this.parentNode = null;
        this.removed = false;
        this.id = '';
        this.title = '';
        this.eventHandlers = {};
        this.classList = {
            add: (...names) => names.forEach((name) => this.classes.add(name)),
            remove: (...names) => names.forEach((name) => this.classes.delete(name)),
            contains: (name) => this.classes.has(name),
            toggle: (name) => {
                if (this.classes.has(name)) this.classes.delete(name);
                else this.classes.add(name);
            },
        };
        this.style = {
            setProperty: () => {},
            getPropertyValue: () => '',
            getPropertyPriority: () => '',
            removeProperty: () => {},
        };
        this.getBoundingClientRect = () => ({ left: 0, top: 0, width: 10, height: 10 });
    }

    matches(selector) {
        return String(selector).split(',').some((part) => part.trim() &&
            matchChainFrom(this, tokenizeChain(part.trim())));
    }

    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches(selector)) return node;
            node = node.parentNode;
        }
        return null;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] ?? null;
    }

    querySelectorAll(selector) {
        const alternatives = String(selector).split(',').map(
            (part) => tokenizeChain(part.trim()),
        );
        return descendantsInOrder(this).filter((candidate) =>
            alternatives.some((tokens) => matchChainFrom(candidate, tokens)));
    }

    appendChild(child) {
        this.children.push(child);
        child.parentNode = this;
        return child;
    }

    insertBefore(newNode, reference) {
        let index = reference ? this.children.indexOf(reference) : this.children.length;
        if (index === -1) index = this.children.length;
        this.children.splice(index, 0, newNode);
        newNode.parentNode = this;
        return newNode;
    }

    get firstChild() {
        return this.children[0] ?? null;
    }

    contains(other) {
        let node = other;
        while (node) {
            if (node === this) return true;
            node = node.parentNode;
        }
        return false;
    }

    remove() {
        if (this.parentNode) {
            const index = this.parentNode.children.indexOf(this);
            if (index !== -1) this.parentNode.children.splice(index, 1);
        }
        this.parentNode = null;
        this.removed = true;
    }

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
        if (name === 'id') this.id = String(value);
        if (/^[a-zA-Z][\w-]*$/.test(name)) this[name] = String(value);
        if (name === 'hidden') this.hidden = true;
    }

    getAttribute(name) {
        return this.attributes.has(name) ? this.attributes.get(name) : null;
    }

    removeAttribute(name) {
        this.attributes.delete(name);
    }

    hasAttribute(name) {
        return this.attributes.has(name);
    }

    addEventListener(name, handler) {
        (this.eventHandlers[name] ??= []).push(handler);
    }

    removeEventListener(name, handler) {
        this.eventHandlers[name] = (this.eventHandlers[name] ?? []).filter((h) => h !== handler);
    }

    replaceChildren(...replacements) {
        this.children.length = 0;
        for (const child of replacements) this.appendChild(child);
    }

    cloneNode(deep) {
        const clone = new FakeElement(this.tagName, [...this.classes].join(' '));
        this.attributes.forEach((value, name) => clone.setAttribute(name, value));
        if (this.id) clone.id = this.id;
        Object.assign(clone.dataset, this.dataset);
        if (deep) this.children.forEach((child) => clone.appendChild(child.cloneNode(true)));
        return clone;
    }
}
'''


FAKE_ELEMENT_DATASET_CORE = r'''
const matchPart = (el, part) => {
    if (!el || !el.tagName) return false;
    const tagMatch = part.match(/^[a-zA-Z][\w-]*/);
    if (tagMatch && el.tagName.toLowerCase() !== tagMatch[0].toLowerCase()) return false;
    const idMatch = part.match(/#([\w-]+)/);
    if (idMatch && (el.id || '') !== idMatch[1]) return false;
    for (const cls of part.match(/\.([\w-]+)/g) || []) {
        if (!el.classList || !el.classList.contains(cls.slice(1))) return false;
    }
    const attrRe = /\[([\w-]+)(?:="([^"]*)")?\]/g;
    let match;
    while ((match = attrRe.exec(part))) {
        const value = el.getAttribute ? el.getAttribute(match[1]) : null;
        if (match[2] === undefined) {
            if (value === null) return false;
        } else if (String(value) !== match[2]) return false;
    }
    const notRe = /:not\(\.([\w-]+)\)/g;
    while ((match = notRe.exec(part))) {
        if (el.classList && el.classList.contains(match[1])) return false;
    }
    if (part.replace(/:not\([^)]*\)/g, '').includes(':')) return false;
    return true;
};

const matchChainFrom = (el, tokens) => {
    const last = tokens[tokens.length - 1];
    if (!matchPart(el, last.part)) return false;
    if (tokens.length === 1) return true;
    const rest = tokens.slice(0, -1);
    if (last.combinator === '>') {
        return Boolean(el.parentNode) && matchChainFrom(el.parentNode, rest);
    }
    let node = el.parentNode;
    while (node) {
        if (matchChainFrom(node, rest)) return true;
        node = node.parentNode;
    }
    return false;
};

const tokenizeChain = (chain) => {
    const tokens = [];
    const re = /(\s*>\s*|\s+)?([^>\s]+)/g;
    let match;
    while ((match = re.exec(chain)) !== null) {
        let combinator = null;
        if (match[1] && match[1].includes('>')) combinator = '>';
        else if (match[1] && match[1].trim() !== '') combinator = ' ';
        tokens.push({ part: match[2], combinator });
    }
    if (tokens.length > 0 && tokens[0].part === ':scope') {
        const [head, ...rest] = tokens;
        rest[0].combinator = '>';
        return rest;
    }
    return tokens;
};

const descendantsInOrder = (root) => {
    const result = [];
    const stack = [...root.children];
    while (stack.length) {
        const node = stack.shift();
        result.push(node);
        stack.unshift(...node.children);
    }
    return result;
};

class FakeElement {
    constructor(tag, className = '') {
        this.tagName = String(tag).toUpperCase();
        this.classes = new Set(String(className).split(/\s+/).filter(Boolean));
        this.attributes = new Map();
        this.dataset = new Proxy({}, {
            set: (target, key, value) => {
                target[key] = value;
                this.setAttribute('data-' + String(key).replace(/[A-Z]/g, (c) => '-' + c.toLowerCase()), value);
                return true;
            },
            deleteProperty: (target, key) => {
                delete target[key];
                this.removeAttribute('data-' + String(key).replace(/[A-Z]/g, (c) => '-' + c.toLowerCase()));
                return true;
            },
        });
        this.children = [];
        this.parentNode = null;
        this.removed = false;
        this.id = '';
        this.title = '';
        this.eventHandlers = {};
        this.classList = {
            add: (...names) => names.forEach((name) => this.classes.add(name)),
            remove: (...names) => names.forEach((name) => this.classes.delete(name)),
            contains: (name) => this.classes.has(name),
            toggle: (name) => {
                if (this.classes.has(name)) this.classes.delete(name);
                else this.classes.add(name);
            },
        };
        this.style = {
            setProperty: () => {},
            getPropertyValue: () => '',
            getPropertyPriority: () => '',
            removeProperty: () => {},
        };
        this.getBoundingClientRect = () => ({ left: 0, top: 0, width: 10, height: 10 });
    }

    matches(selector) {
        return String(selector).split(',').some((part) => part.trim() &&
            matchChainFrom(this, tokenizeChain(part.trim())));
    }

    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches(selector)) return node;
            node = node.parentNode;
        }
        return null;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] ?? null;
    }

    querySelectorAll(selector) {
        const alternatives = String(selector).split(',').map(
            (part) => tokenizeChain(part.trim()),
        );
        return descendantsInOrder(this).filter((candidate) =>
            alternatives.some((tokens) => matchChainFrom(candidate, tokens)));
    }

    appendChild(child) {
        this.children.push(child);
        child.parentNode = this;
        return child;
    }

    insertBefore(newNode, reference) {
        let index = reference ? this.children.indexOf(reference) : this.children.length;
        if (index === -1) index = this.children.length;
        this.children.splice(index, 0, newNode);
        newNode.parentNode = this;
        return newNode;
    }

    get firstChild() {
        return this.children[0] ?? null;
    }

    contains(other) {
        let node = other;
        while (node) {
            if (node === this) return true;
            node = node.parentNode;
        }
        return false;
    }

    remove() {
        if (this.parentNode) {
            const index = this.parentNode.children.indexOf(this);
            if (index !== -1) this.parentNode.children.splice(index, 1);
        }
        this.parentNode = null;
        this.removed = true;
    }

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
        if (name === 'id') this.id = String(value);
        if (/^[a-zA-Z][\w-]*$/.test(name)) this[name] = String(value);
        if (name === 'hidden') this.hidden = true;
    }

    getAttribute(name) {
        return this.attributes.has(name) ? this.attributes.get(name) : null;
    }

    removeAttribute(name) {
        this.attributes.delete(name);
    }

    hasAttribute(name) {
        return this.attributes.has(name);
    }

    addEventListener(name, handler) {
        (this.eventHandlers[name] ??= []).push(handler);
    }

    removeEventListener(name, handler) {
        this.eventHandlers[name] = (this.eventHandlers[name] ?? []).filter((h) => h !== handler);
    }

    cloneNode(deep) {
        const clone = new FakeElement(this.tagName, [...this.classes].join(' '));
        this.attributes.forEach((value, name) => clone.setAttribute(name, value));
        if (this.id) clone.id = this.id;
        Object.assign(clone.dataset, this.dataset);
        if (deep) this.children.forEach((child) => clone.appendChild(child.cloneNode(true)));
        return clone;
    }
}
'''


class BattleBoardFixture(TestCase):
    """Two-participant game fixture shared by browser and API tests."""

    def _create_owned_card(self, owner_history, title, card_type):
        card = Card.objects.create(title=title, artSource="", cardType=card_type)
        card.ownerHistory.add(owner_history)
        return card

    def _initialize_with_hand_card(self, participant, card, ordinal=99):
        participant.startWithDeckInRandomOrder(initializeStartingCard=True)
        game_card = GameCard.objects.get(
            game_id=self.game.id,
            user_id=participant.id,
            card_id=card.id,
        )
        game_card.state.draw()
        game_card.state.updateOrdinal(ordinal)
        game_card.state.save()
        return game_card

    def _replace_deck_with_count(self, participant, count):
        GameCard.objects.filter(
            game_id=self.game.id,
            user_id=participant.id,
        ).delete()
        for index in range(count):
            card = Card.objects.create(
                title=f"{participant.player.name}-deck-{count}-{index}",
                artSource="",
                cardType=index % 4,
            )
            game_card = GameCard.create(card.id, self.game.id, participant.id)
            game_card.save()
            game_card.state.inDeck = True
            game_card.state.lane = -(index + 1)
            game_card.state.laneOrdinal = 0
            game_card.state.faceDown = True
            game_card.state.trusted = False
            game_card.state.save()
        if count == 0:
            card = Card.objects.create(
                title=f"{participant.player.name}-empty-deck-board-card",
                artSource="",
                cardType=0,
            )
            game_card = GameCard.create(card.id, self.game.id, participant.id)
            game_card.save()
            game_card.state.inDeck = False
            game_card.state.lane = 1
            game_card.state.laneOrdinal = 1
            game_card.state.faceDown = False
            game_card.state.trusted = True
            game_card.state.save()

    def _replace_hand_with_count(self, participant, count):
        GameCard.objects.filter(
            game_id=self.game.id,
            user_id=participant.id,
        ).delete()
        for index in range(count):
            card = Card.objects.create(
                title=f"{participant.player.name}-hand-{count}-{index}",
                artSource="",
                cardType=index % 4,
            )
            game_card = GameCard.create(card.id, self.game.id, participant.id)
            game_card.save()
            game_card.state.draw()
            game_card.state.updateOrdinal(index + 1)
            game_card.state.save()

    def setUp(self):
        self.human = Player.objects.create(name="Human")
        self.bot = Player.objects.create(name="Bot")

        human_owner = CardOwnerHistory.objects.create(cardOwner=self.human)
        bot_owner = CardOwnerHistory.objects.create(cardOwner=self.bot)

        self.human_cards = [
            self._create_owned_card(human_owner, f"Human-{index}", index % 4) for index in range(4)
        ]
        self.bot_cards = [
            self._create_owned_card(bot_owner, f"Bot-{index}", index % 4) for index in range(4)
        ]

        self.human_deck = Deck.create(
            self.human.id,
            deckTitle="Human deck",
            newDescription="test deck",
            newDeckCards=self.human_cards,
        )
        self.bot_deck = Deck.create(
            self.bot.id,
            deckTitle="Bot deck",
            newDescription="test deck",
            newDeckCards=self.bot_cards,
        )

        history = BattleHistory.objects.create(challenger=self.human)
        self.game = Game.objects.create(title="Test game", history=history, roundNumber=0)
        self.human_participant = history.addHumanChallenger(
            challengerPlayer_id=self.human.id,
            startingCard_id=self.human_cards[0].id,
            deck_id=self.human_deck.id,
        )
        self.bot_participant = history.addRobotChallenger(
            challengerPlayer_id=self.bot.id,
            startingCard_id=self.bot_cards[0].id,
            deck_id=self.bot_deck.id,
        )


class BattleFlowTests(BattleBoardFixture):
    def test_turn_allowances_match_fresh_board(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)

        allowances = self.human_participant.getTurnAllowances()
        self.assertEqual(allowances["draws_left"], 2)
        self.assertEqual(allowances["flips_left"], 1)
        self.assertEqual(allowances["plays_left"], 3)
        self.assertEqual(allowances["int_count"], 1)
        self.assertEqual(allowances["spd_count"], 0)
        self.assertEqual(allowances["tactics"], 1)
        self.assertEqual(allowances["drawn"], 0)
        self.assertEqual(allowances["played"], 0)
        self.assertEqual(allowances["flipped"], 0)
        for key in ("draw", "play", "flip"):
            self.assertIn(key, allowances["blocked_titles"])

    def test_draw_parity(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        draws_left = self.human_participant.getTurnAllowances()["draws_left"]
        self.assertEqual(draws_left, 2)

        for i in range(draws_left):
            response = self.client.post(draw_url, {"action": "draw"})
            self.assertNotContains(response, "Action error")

        # At this point drawnCardsAmount == 2, draws_left should be 0
        self.human_participant.refresh_from_db()
        self.assertEqual(self.human_participant.getTurnAllowances()["draws_left"], 0)

        # The (draws_left+1)th POST must fail with the enforcement error
        response = self.client.post(draw_url, {"action": "draw"})
        self.assertContains(response, "Action error")
        self.assertContains(response, "cannot draw more cards")

    def test_space_draw_roundtrip_restores_draw_button_focusability(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        response = self.client.get(board_url)
        self.assertContains(
            response, '<button type="submit" class="card back draw" title="Draw card">'
        )
        self.assertContains(response, '<script type="module" src="/static/cardDragDrop.js"></script>')
        self.assertContains(
            response, '<script type="module" src="/static/loadingAnimations.js"></script>'
        )

        response = self.client.post(draw_url, {"action": "draw"})
        self.assertNotContains(response, "Action error")
        loading_tag = re.search(
            r'<li class="cardContainer loading"[^>]*>', response.content.decode()
        )
        self.assertIsNotNone(loading_tag)
        self.assertIn('data-source-lane="-', loading_tag.group(0))
        self.assertEqual([name for name in response.cookies if name.isdigit()], [])
        self.assertNotIn("turn_phase", response.cookies)

        # the focus restore target must survive the space-draw reload itself
        response = self.client.get(board_url)
        self.assertContains(
            response, '<button type="submit" class="card back draw" title="Draw card">'
        )
        self.assertNotContains(response, 'data-phase=')

        response = self.client.post(draw_url, {"action": "draw"})
        self.assertNotContains(response, "Action error")
        response = self.client.get(board_url)
        content = response.content.decode()
        self.assertRegex(content, r'class="card back draw blocked" disabled title="Draw limit reached')
        self.assertRegex(content, r'class="deck blocked(?:\s|")')

    def test_space_draw_roundtrip_renders_no_draw_button_when_deck_is_depleted(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        self._replace_deck_with_count(self.human_participant, 0)

        response = self.client.post(draw_url, {"action": "draw"})
        self.assertContains(response, "No cards left in")
        self.assertNotContains(response, "cardContainer loading")

        response = self.client.get(board_url)
        self.assertContains(response, '<div class="card back emptyDeck">')
        self.assertNotContains(response, 'class="card back draw"')
        self.assertNotContains(response, 'data-phase=')

    def test_board_renders_turn_limits_data(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.get(board_url)
        content = response.content.decode()

        self.assertIn('id="turnLimits"', content)
        self.assertIn('data-draws-left="2"', content)
        self.assertIn('data-plays-left="3"', content)
        self.assertIn('data-flips-left="1"', content)
        self.assertIn("0d", content)
        self.assertIn("0p", content)
        self.assertIn("0f", content)

    def test_hand_fans_preserve_order_and_repeat_every_nine_cards(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        for hand_count, expected_fan_sizes in (
            (9, [9]),
            (10, [9, 1]),
            (18, [9, 9]),
            (19, [9, 9, 1]),
        ):
            self._replace_hand_with_count(self.human_participant, hand_count)
            response = self.client.get(board_url)
            content = response.content.decode()
            fan_matches = re.findall(
                r'<ul class="hand hand-fan" data-fan-index="(\d+)">(.*?)</ul>',
                content,
                re.DOTALL,
            )

            self.assertEqual(
                [int(index) for index, _ in fan_matches],
                list(range(len(expected_fan_sizes))),
            )
            self.assertEqual(
                [fan_html.count('class="cardContainer') for _, fan_html in fan_matches],
                expected_fan_sizes,
            )
            self.assertEqual(
                [
                    card.state.laneOrdinal
                    for card in GameCard.objects.filter(
                        game_id=self.game.id,
                        user_id=self.human_participant.id,
                        state__lane=0,
                    ).order_by("state__laneOrdinal")
                ],
                list(range(1, hand_count + 1)),
            )

    def test_empty_hand_has_one_fan_placeholder(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        self._replace_hand_with_count(self.human_participant, 0)
        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))
        content = response.content.decode()
        fan_matches = re.findall(
            r'<ul class="hand hand-fan" data-fan-index="(\d+)">(.*?)</ul>',
            content,
            re.DOTALL,
        )

        self.assertEqual(len(fan_matches), 1)
        self.assertEqual(fan_matches[0][0], "0")
        self.assertIn("emptyHand", fan_matches[0][1])
        self.assertEqual(content.count("emptyHand"), 1)

    def test_hand_fan_cards_keep_action_and_source_attributes(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        self._replace_hand_with_count(self.human_participant, 14)
        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))
        content = response.content.decode()
        hand_fans = re.findall(
            r'<ul class="hand hand-fan" data-fan-index="\d+">(.*?)</ul>',
            content,
            re.DOTALL,
        )
        hand_html = "".join(hand_fans)
        hand_card_ids = re.findall(
            r'<li class="cardContainer [^>]+data-card-id="([^"]+)"[^>]*>',
            hand_html,
        )

        self.assertEqual(len(hand_card_ids), 14)
        self.assertEqual(len(set(hand_card_ids)), 14)
        for card in GameCard.objects.filter(
            game_id=self.game.id, user_id=self.human_participant.id, state__lane=0
        ):
            self.assertIn(str(card.id), hand_card_ids)
        self.assertEqual(hand_html.count('name="card_id"'), 14)
        hidden_card_id_values = re.findall(r'name="card_id" value="([^"]+)"', hand_html)
        self.assertEqual(set(hidden_card_id_values), set(hand_card_ids))
        self.assertEqual(hand_html.count('data-source-lane="0"'), 14)
        self.assertEqual(hand_html.count('data-source-ordinal="'), 14)
        self.assertEqual(hand_html.count('draggable="true"'), 14)
        self.assertEqual(hand_html.count('tabindex="0"'), 14)

        self.assertNotIn("cardActionForm", hand_html)
        self.assertNotIn("cardActionButton", hand_html)

    def test_play_budget_blocks_cards_in_every_hand_fan(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        self._replace_hand_with_count(self.human_participant, 14)
        self.human_participant.playedCardsAmount = 3
        self.human_participant.save(update_fields=["playedCardsAmount"])

        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))
        fan_matches = re.findall(
            r'<ul class="hand hand-fan" data-fan-index="\d+">(.*?)</ul>',
            response.content.decode(),
            re.DOTALL,
        )

        self.assertEqual([fan.count("cardContainer") for fan in fan_matches], [9, 5])
        for fan in fan_matches:
            self.assertEqual(fan.count("blocked"), fan.count("cardContainer"))
            self.assertEqual(
                len(re.findall(r'<li class="cardContainer[^>]*draggable="false"', fan)),
                fan.count("cardContainer"),
            )
            self.assertNotIn("tabindex", fan)

    def test_artless_cards_render_with_css_playing_card_markup(self):
        from mysite.jinja2 import (
            playing_card_default_name,
            playing_card_rank_class,
            playing_card_rank_display,
            playing_card_suit_class,
        )

        helper_card = SimpleNamespace(id=9, cardType=1)
        self.assertEqual(playing_card_rank_class(helper_card), "rank-j")
        self.assertEqual(playing_card_rank_display(helper_card), "J")
        self.assertEqual(playing_card_suit_class(helper_card), "spades")
        self.assertEqual(playing_card_default_name(helper_card), "Jack of Spades")

        card = self.human_cards[0]
        response = self.client.get(reverse("MMM:viewCard", args=[card.id]))
        content = response.content.decode()
        self.assertIn("/static/MMM/1flubeltje.jpg", content)
        self.assertNotIn("playing-card-spotlight card staticCard", content)

        card.artSource = "static"
        card.save(update_fields=["artSource"])
        response = self.client.get(reverse("MMM:viewCard", args=[card.id]))
        content = response.content.decode()
        rank_class = playing_card_rank_class(card)
        suit_class = playing_card_suit_class(card)
        self.assertIn(
            f'class="spotlight playing-card-spotlight card staticCard {rank_class} {suit_class}"',
            content,
        )
        self.assertIn(
            f'<span class="rank">{playing_card_rank_display(card)}</span>',
            content,
        )
        self.assertNotIn("1flubeltje.jpg", content)

    def test_generated_deck_cards_use_css_markup_in_collection(self):
        from io import StringIO
        from django.core.management import call_command
        from mysite.jinja2 import playing_card_rank_class, playing_card_suit_class

        lucas = Player.objects.create(name="Lucas")
        owner_history = CardOwnerHistory.objects.create(cardOwner=lucas)
        legacy_card = Card.objects.create(
            title="Two of Clubs", artSource="", cardType=0
        )
        legacy_card.ownerHistory.add(owner_history)

        call_command("add_deck_cards", stdout=StringIO())
        call_command("add_deck_cards", stdout=StringIO())
        legacy_card.refresh_from_db()
        self.assertEqual(legacy_card.artSource, "static")
        self.assertEqual(
            Card.objects.filter(ownerHistory=owner_history).count(),
            52,
        )
        generated_card = Card.objects.filter(
            ownerHistory__cardOwner=lucas,
        ).order_by("id").first()

        response = self.client.get(reverse("MMM:viewPlayer", args=[lucas.id]))
        content = response.content.decode()
        self.assertIn(
            f'class="card smallCard staticCard {playing_card_rank_class(generated_card)} '
            f'{playing_card_suit_class(generated_card)}"',
            content,
        )
        self.assertIn(f'href="{reverse("MMM:viewCard", args=[generated_card.id])}"', content)
        self.assertNotIn("/static/1flubeltje.jpg", content)
        self.assertNotIn("class=\"cardTitle\">Two of Clubs", content)
        self.assertIn("Intelligence", content)

    def test_confirm_is_idempotent(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        self.client.post(confirm_url)

        human_game_cards = GameCard.objects.filter(game_id=self.game.id, user_id=self.human_participant.id)
        self.assertEqual(human_game_cards.count(), self.human_deck.cards.count())
        self.assertEqual(human_game_cards.values("card_id").distinct().count(), human_game_cards.count())

    def test_drawing_cards_never_duplicates(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        drawable_cards = GameCard.objects.filter(
            game_id=self.game.id,
            user_id=self.human_participant.id,
            state__inDeck=True,
        ).count()
        for _ in range(drawable_cards + 2):
            self.client.post(draw_url, {"action": "draw"})

        hand_cards = list(
            GameCard.objects.filter(game_id=self.game.id, user_id=self.human_participant.id, state__lane=0)
            .values_list("card_id", flat=True)
        )

        self.assertLessEqual(len(hand_cards), drawable_cards)
        self.assertEqual(len(hand_cards), len(set(hand_cards)))

    def test_play_cookie_payload_contains_source_state(self):
        payload = battle_services.parse_play_cookie_payload(
            '{"laneValue": 2, "sourceLane": 0, "sourceOrdinal": 3, "flipFaceUp": true}'
        )

        self.assertEqual(payload["laneValue"], 2)
        self.assertEqual(payload["sourceLane"], 0)
        self.assertEqual(payload["sourceOrdinal"], 3)
        self.assertTrue(payload["flipFaceUp"])

    def test_starting_card_has_positive_ordinal_and_occupies_trusted_lane(self):
        self.human_participant.startWithDeckInRandomOrder(initializeStartingCard=True)

        starting_card = GameCard.objects.get(
            game_id=self.game.id,
            user_id=self.human_participant.id,
            card_id=self.human_cards[0].id,
        )

        self.assertEqual(starting_card.state.lane, 1)
        self.assertEqual(starting_card.state.laneOrdinal, 1)
        self.assertTrue(starting_card.state.trusted)

    def test_play_card_uses_trusted_destination_max_not_hand_or_source_ordinal(self):
        hand_card = self._initialize_with_hand_card(
            self.human_participant,
            self.human_cards[1],
        )

        played_card = self.human_participant.playCard(
            hand_card.id,
            lane=1,
            sourceLane=0,
            sourceOrdinal=99,
        )

        self.assertEqual(played_card.state.laneOrdinal, 2)
        self.assertEqual(
            GameCard.objects.get(pk=played_card.id).state.laneOrdinal,
            2,
        )
        intelligence_lane = next(
            lane
            for lane in battle_services.context_board(
                GameCard.objects.filter(game_id=self.game.id),
                self.human_participant.id,
            )["laneRows"]
            if lane["name"] == "Intelligence"
        )
        self.assertEqual(
            intelligence_lane["trustedCards"][0].state.laneOrdinal,
            1,
        )
        self.assertEqual(intelligence_lane["cards"][0].state.laneOrdinal, 2)

    def test_play_card_uses_one_for_empty_lane_not_hand_or_source_ordinal(self):
        hand_card = self._initialize_with_hand_card(
            self.human_participant,
            self.human_cards[1],
        )

        played_card = self.human_participant.playCard(
            hand_card.id,
            lane=3,
            sourceLane=0,
            sourceOrdinal=99,
        )

        self.assertEqual(played_card.state.laneOrdinal, 1)

    def test_context_board_orders_lane_cards_by_ordinal_for_stacking(self):
        first_card = self._initialize_with_hand_card(
            self.human_participant,
            self.human_cards[1],
        )
        self.human_participant.playCard(first_card.id, lane=1)

        second_card = GameCard.objects.get(
            game_id=self.game.id,
            user_id=self.human_participant.id,
            card_id=self.human_cards[2].id,
        )
        second_card.state.draw()
        second_card.state.updateOrdinal(100)
        second_card.state.save()
        self.human_participant.playCard(second_card.id, lane=1)

        board = battle_services.context_board(
            GameCard.objects.filter(game_id=self.game.id).order_by("-state__laneOrdinal"),
            self.human_participant.id,
        )
        intelligence_lane = board["laneRows"][0]

        self.assertEqual(
            [card.state.laneOrdinal for card in intelligence_lane["trustedCards"]],
            [1],
        )
        self.assertEqual(
            [card.state.laneOrdinal for card in intelligence_lane["cards"]],
            [2, 3],
        )

    def test_cookie_play_uses_destination_lane_ordinal(self):
        hand_card = self._initialize_with_hand_card(
            self.human_participant,
            self.human_cards[1],
        )

        battle_services.consume_staged_plays(
            self.game,
            {
                str(hand_card.id): {
                    "laneValue": 4,
                    "sourceLane": 0,
                    "sourceOrdinal": 99,
                    "flipFaceUp": False,
                }
            },
            self.human_participant,
        )

        hand_card.refresh_from_db()
        self.assertEqual(hand_card.state.lane, 4)
        self.assertEqual(hand_card.state.laneOrdinal, 1)

    def test_bot_play_uses_destination_lane_max(self):
        hand_card = self._initialize_with_hand_card(
            self.bot_participant,
            self.bot_cards[1],
        )
        existing_card = GameCard.objects.get(
            game_id=self.game.id,
            user_id=self.bot_participant.id,
            card_id=self.bot_cards[2].id,
        )
        existing_card.state.draw()
        existing_card.state.play(2)
        existing_card.state.reveal()
        existing_card.state.updateOrdinal(3)
        existing_card.state.save()

        bot_actions, _ = battle_services.run_bot_turn(self.game, self.human.id)

        self.assertEqual(len(bot_actions), 1)
        self.assertEqual(bot_actions[0]["sourceOrdinal"], 99)
        hand_card.refresh_from_db()
        self.assertEqual(hand_card.state.lane, 2)
        self.assertEqual(hand_card.state.laneOrdinal, 4)

    def test_special_play_uses_destination_lane_ordinal(self):
        hand_card = self._initialize_with_hand_card(
            self.human_participant,
            self.human_cards[1],
        )

        timeline = []
        battle_services.run_int_special(self.human_participant, 1, timeline)

        hand_card.refresh_from_db()
        self.assertEqual(hand_card.state.lane, 2)
        self.assertEqual(hand_card.state.laneOrdinal, 1)
        effect_cards = [
            card
            for step in timeline
            if step["kind"] == "card-effect"
            for card in step["affectedCards"]
        ]
        self.assertEqual(effect_cards[0]["destinationOrdinal"], 1)

    def test_end_turn_defers_bot_turn_to_enemy_phase_get(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        def bot_state():
            return {
                "lane": GameCard.objects.filter(
                    game_id=self.game.id, user_id=self.bot_participant.id, state__lane__gt=0
                ).count(),
                "hand": GameCard.objects.filter(
                    game_id=self.game.id, user_id=self.bot_participant.id, state__lane=0
                ).count(),
                "deck": GameCard.objects.filter(
                    game_id=self.game.id, user_id=self.bot_participant.id, state__inDeck=True
                ).count(),
            }

        # the end_turn POST mutates no bot state and sets no bot cookies
        before = bot_state()
        response = self.client.post(end_turn_url, {"action": "end_turn"})

        self.game.refresh_from_db()
        self.assertEqual(bot_state(), before)
        self.assertEqual(self.game.roundNumber, 1)
        self.assertFalse([name for name in response.cookies if name.isdigit()])

        self.client.get(board_url)
        self.game.refresh_from_db()
        after = bot_state()
        self.assertGreater(after["lane"], before["lane"])
        self.assertEqual(self.game.roundNumber, 2)

        self.client.get(board_url)
        self.client.get(board_url)
        self.game.refresh_from_db()
        self.assertEqual(bot_state(), after)
        self.assertEqual(self.game.roundNumber, 2)

    def test_end_turn_sets_no_bot_action_cookies(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.post(end_turn_url, {"action": "end_turn"})

        self.assertFalse([name for name in response.cookies if name.isdigit()])
        self.assertEqual(response.cookies["turn_phase"].value, "enemy")

    def test_enemy_phase_get_runs_bots_and_marks_moves_loading(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        self.client.post(end_turn_url, {"action": "end_turn"})
        
        response = self.client.get(board_url)
        self.assertContains(response, 'data-phase="enemy"')
        self.assertContains(response, 'cardContainer loading')
        
        loading_tag = re.search(
            r'<li class="cardContainer loading"[^>]*>', response.content.decode()
        )
        self.assertIsNotNone(loading_tag)
        self.assertIn('data-source-lane="-', loading_tag.group(0))
        self.assertIn('data-source-ordinal="0"', loading_tag.group(0))

        self.client.cookies = SimpleCookie()
        response = self.client.get(board_url)
        self.assertNotContains(response, "cardContainer loading")

    def test_enemy_phase_static_play_carries_deck_source_and_card_face(self):
        """A bot's drawn-and-played static card flies deck->lane with its face.

        The enemy-phase GET merges the bot's draw and play of the same card
        into one move: the played card is marked loading in its destination
        enemy lane with the deck position as its source, carrying the full
        static card face (rank, suit, card type) that the landed card shows.
        The flight clone built from that markup must render under the board's
        .playingCards CSS scope so the flying card looks exactly like a card a
        player plays face-up to a lane.
        """
        for card in self.human_cards + self.bot_cards:
            card.artSource = "static"
            card.save(update_fields=["artSource"])

        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        self.client.post(end_turn_url, {"action": "end_turn"})
        response = self.client.get(board_url)

        loading_card = re.search(
            r'<li class="cardContainer loading".*?</li>',
            response.content.decode(),
            re.DOTALL,
        )
        self.assertIsNotNone(loading_card)
        loading_markup = loading_card.group(0)
        self.assertIn('data-source-lane="-', loading_markup)
        self.assertIn('data-source-ordinal="0"', loading_markup)
        self.assertIn("staticCard", loading_markup)
        self.assertIn('<span class="rank">', loading_markup)
        self.assertIn('<span class="suit">', loading_markup)
        self.assertIn('class="smallCardInfo"', loading_markup)
        self.assertNotIn("fit-picture", loading_markup)

    def test_enemy_phase_dims_player_hand_and_board_from_phase_start(self):
        """Ending a turn darkens the player's hand while the enemy phase runs.

        The enemy phase starts on the first board GET after the end-turn POST:
        that render carries data-phase="enemy" while the bot's moves animate,
        so the dimming is driven by the enemy-phase marker itself, never by a
        bot-finished condition. The dim rules must match the DOM the board
        renders: the deckHand row is nested inside the board table, not a
        direct child of .playerScreen, so a direct-child rule can never hit it.
        """
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()

        dim_rule = re.search(
            r'\.playerScreen\.enemyTurnFocus[^{]*\{[^}]*\}', cards_css
        )
        self.assertIsNotNone(dim_rule, "enemy turn dim rule missing from cards.css")
        self.assertIn('.playerScreen.enemyTurnFocus .deckHand', dim_rule.group(0))
        self.assertIn('.playerScreen.enemyTurnFocus .playerBoard', dim_rule.group(0))
        self.assertNotIn('.playerScreen.enemyTurnFocus > .deckHand', cards_css)

        enemy_phase_block = _extract_js_brace_block(loading_js, "if (phase === 'enemy')")
        self.assertIn('focusEnemySide();', enemy_phase_block)
        self.assertLess(
            enemy_phase_block.index('focusEnemySide();'),
            enemy_phase_block.index('schedule('),
            "the dim must start with the enemy phase, not after its animations",
        )
        focus_enemy_side = _extract_js_brace_block(loading_js, 'function focusEnemySide()')
        self.assertIn("playerScreen.classList.add('enemyTurnFocus')", focus_enemy_side)

        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)
        self.client.post(end_turn_url, {"action": "end_turn"})

        response = self.client.get(board_url)
        self.assertContains(response, 'data-phase="enemy"')
        content = response.content.decode()
        direct_child = re.search(
            r'<div class="playerScreen[^"]*"[^>]*>\s*<div class="deckHand', content
        )
        self.assertIsNone(
            direct_child,
            "the rendered deckHand is not a direct .playerScreen child; the dim "
            "rule must stay a descendant selector",
        )
        nested_deck_hand = re.search(
            r'<ul class="basic-mat table">.*?<div class="deckHand[^"]*"', content,
            re.DOTALL,
        )
        self.assertIsNotNone(nested_deck_hand)
        self.assertContains(response, '<li class="playerBoard ')

    def test_draw_renders_drawn_card_loading_from_deck(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        response = self.client.post(draw_url, {"action": "draw"})
        self.assertContains(response, 'cardContainer loading')
        self.assertContains(response, '<div class="card smallCard">')
        self.assertContains(response, "/static/MMM/1flubeltje.jpg")
        self.assertContains(response, 'data-source-lane="-')

        loading_tag = re.search(
            r'<li class="cardContainer loading"[^>]*>', response.content.decode()
        )
        self.assertIsNotNone(loading_tag)
        self.assertIn('data-source-lane="-', loading_tag.group(0))
        self.assertIn('data-source-ordinal="0"', loading_tag.group(0))

        # the draw itself still happened: one card sits in the player's hand
        self.assertEqual(
            GameCard.objects.filter(
                game_id=self.game.id,
                user_id=self.human_participant.id,
                state__lane=0,
            ).count(),
            1,
        )

    def test_static_hand_card_uses_the_same_css_face_as_field_cards(self):
        for card in self.human_cards + self.bot_cards:
            card.artSource = "static"
            card.save(update_fields=["artSource"])

        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.post(draw_url, {"action": "draw"})

        self.assertContains(response, 'class="card smallCard staticCard')
        self.assertContains(response, "staticCard")
        self.assertContains(response, '<span class="suit">')
        self.assertContains(response, 'class="cardType"')
        self.assertNotContains(response, 'class="cardTitle"')
        self.assertNotContains(response, "/static/1flubeltje.jpg")

    def test_draw_sets_no_play_cookie(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.post(draw_url, {"action": "draw"})

        drawn_card = GameCard.objects.get(
            game_id=self.game.id, user_id=self.human_participant.id, state__lane=0
        )

        self.assertNotIn(str(drawn_card.id), response.cookies)
        self.assertFalse([name for name in response.cookies if name.isdigit()])

    def test_action_posts_render_no_board_veil(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        action_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        response = self.client.post(action_url, {"action": "draw"})
        self.assertNotContains(response, "boardVeil")

        response = self.client.post(action_url, {"action": "end_turn"})
        self.assertNotContains(response, "boardVeil")

    def test_enemy_deck_and_hand_render_as_card_elements(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.get(board_url)

        # enemy deck and hand render as real face-down card elements so enemy
        # animations have a source element to fly from
        self.assertContains(response, "enemyDeckHand")
        bot_deck_count = GameCard.objects.filter(
            game_id=self.game.id, user_id=self.bot_participant.id, state__inDeck=True
        ).count()
        bot_hand_count = GameCard.objects.filter(
            game_id=self.game.id, user_id=self.bot_participant.id, state__lane=0
        ).count()
        self.assertGreater(bot_deck_count, 0)
        content = response.content.decode()
        enemy_deck_hand = re.search(
            r'<div class="enemyDeckHand">(.*?)<ul class="lanes">',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(enemy_deck_hand)
        enemy_board = battle_services.context_board(
            GameCard.objects.filter(game_id=self.game.id),
            self.bot_participant.id,
        )
        self.assertEqual(
            enemy_deck_hand.group(1).count("cardContainer faceDown"),
            len(enemy_board["deckStack"]) + bot_hand_count,
        )
        self.assertNotIn("fourColours", content)
        self.assertIn(
            f'title="{self.bot_cards[0].title} of {self.bot.name}"',
            content,
        )

    def test_large_decks_keep_real_counts_and_active_top_card(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)

        for deck_count in (32, 40, 64, 65):
            self._replace_deck_with_count(self.human_participant, deck_count)
            self._replace_deck_with_count(self.bot_participant, deck_count)

            own_board = battle_services.context_board(
                GameCard.objects.filter(game_id=self.game.id),
                self.human_participant.id,
            )
            enemy_board = battle_services.context_board(
                GameCard.objects.filter(game_id=self.game.id),
                self.bot_participant.id,
            )
            expected_indicator_count = max(0, (deck_count - 1) // 32)
            expected_active_count = deck_count - expected_indicator_count * 32

            for board, participant in (
                (own_board, self.human_participant),
                (enemy_board, self.bot_participant),
            ):
                self.assertEqual(board["deckCount"], deck_count)
                self.assertEqual(len(board["deckStack"]), expected_active_count)
                self.assertEqual(
                    len(board["deckIndicators"]), expected_indicator_count
                )
                self.assertEqual(
                    board["deckStack"][-1].id,
                    participant.getNextDeckCard().id,
                )

            response = self.client.get(board_url)
            content = response.content.decode()
            own_section = re.search(
                r'<div class="deck-stack own-deck-stack"[^>]*>(.*?)<div class="hand-scroll"[^>]*>',
                content,
                re.DOTALL,
            )
            enemy_section = re.search(
                r'<div class="enemyDeckHand">(.*?)<ul class="lanes">',
                content,
                re.DOTALL,
            )
            self.assertIsNotNone(own_section)
            self.assertIsNotNone(enemy_section)

            for section in (own_section.group(1), enemy_section.group(1)):
                indicators = re.findall(
                    r'<ul class="deck-indicator"[^>]*>.*?</ul>',
                    section,
                    re.DOTALL,
                )
                self.assertEqual(len(indicators), expected_indicator_count)
                for indicator in indicators:
                    self.assertIn('aria-hidden="true"', indicator)
                    self.assertNotIn("<form", indicator)
                    self.assertNotIn("<button", indicator)
                    self.assertNotIn("data-card-id", indicator)

            own_active = re.search(
                r'<ul class="deck(?: blocked)? active-deck">(.*?)</ul>',
                own_section.group(1),
                re.DOTALL,
            )
            enemy_active = re.search(
                r'<ul class="deck enemyDeck active-deck">(.*?)</ul>',
                enemy_section.group(1),
                re.DOTALL,
            )
            self.assertIsNotNone(own_active)
            self.assertIsNotNone(enemy_active)
            self.assertEqual(own_active.group(1).count("<li>"), expected_active_count)
            self.assertEqual(
                enemy_active.group(1).count("<li"), expected_active_count
            )
            self.assertEqual(own_active.group(1).count("<button"), 1)
            self.assertNotIn("<form", enemy_active.group(1))
            self.assertNotIn("<button", enemy_active.group(1))

    def test_empty_decks_keep_active_empty_indicators_and_no_draw_button(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)
        self._replace_deck_with_count(self.human_participant, 0)
        self._replace_deck_with_count(self.bot_participant, 0)

        response = self.client.get(board_url)
        content = response.content.decode()
        self.assertContains(response, "emptyDeck")
        self.assertNotContains(response, "deck-indicator")
        self.assertNotContains(response, 'class="card back draw"')

        enemy_section = re.search(
            r'<div class="enemyDeckHand">(.*?)<ul class="lanes">',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(enemy_section)
        self.assertIn("emptyDeck", enemy_section.group(1))
        for button_tag in re.findall(r'<button[^>]*>', enemy_section.group(1)):
            self.assertIn(
                'disabled', button_tag,
                "the enemy section may only carry inert controls; the empty deck "
                "must not gain an active button",
            )

    def test_board_renders_backdrop_and_deck_indicator_face_art(self):
        """The wood-texture backdrop and the deck-indicator card-back faces are
        real visible art served from static files in deployment; phantom-asset
        sweeps must not strip them from the board again."""
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)
        self._replace_deck_with_count(self.human_participant, 64)
        self._replace_deck_with_count(self.bot_participant, 64)

        response = self.client.get(board_url)
        content = response.content.decode()

        self.assertIn(
            '<img draggable="false" class="fit-picture fullpage-background" '
            'src="/static/woodtextureorangedark2.jpg"',
            content,
        )

        deck_face = (
            '<img class="deck-indicator-face" draggable="false" '
            'src="/static/extradeck.png"'
        )
        own_section = re.search(
            r'<div class="deck-stack own-deck-stack"[^>]*>(.*?)<div class="hand-scroll"[^>]*>',
            content,
            re.DOTALL,
        )
        enemy_section = re.search(
            r'<div class="enemyDeckHand">(.*?)<ul class="lanes">',
            content,
            re.DOTALL,
        )
        for section_name, section in (
            ("own", own_section),
            ("enemy", enemy_section),
        ):
            self.assertIsNotNone(section)
            self.assertIn(
                deck_face,
                section.group(1),
                f"the {section_name} deck indicator lost its card-back face art",
            )

    def test_deck_animation_and_draw_selectors_use_active_deck_only(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        self.assertIn("board.querySelector('.deck-stack .active-deck')", loading_js)
        self.assertIn('.playerBoard .deck-stack .active-deck', loading_js)
        self.assertIn('.playerBoard .deck-stack .active-deck', drag_js)
        self.assertNotIn(".playerScreen .deckHand .active-deck", loading_js)
        self.assertNotIn(".playerScreen .deckHand .active-deck", drag_js)
        self.assertNotIn(".deck-stack .deck')", loading_js)

        # the selectors must match the DOM the board actually renders: the
        # active deck lives inside the playerBoard section, never inside the
        # deckHand row
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)
        content = self.client.get(board_url).content.decode()
        player_board_section = re.search(
            r'<li class="playerBoard[^>]*>(.*?)<div class="deckHand', content, re.DOTALL,
        )
        deck_hand_section = re.search(
            r'<div class="deckHand[^"]*"[^>]*>(.*)', content, re.DOTALL,
        )
        self.assertIsNotNone(player_board_section)
        self.assertIsNotNone(deck_hand_section)
        self.assertIn('active-deck', player_board_section.group(1))
        self.assertIn('deck-stack', player_board_section.group(1))
        self.assertNotIn('active-deck', deck_hand_section.group(1))

    def test_end_turn_turn_phase_sequence_across_reloads(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.post(end_turn_url, {"action": "end_turn"})

        self.assertContains(response, 'data-phase="playerMoves"')
        self.assertEqual(response.cookies["turn_phase"].value, "enemy")
        self.assertEqual(response.cookies["turn_phase"]["path"], board_url)

        response = self.client.get(board_url)
        self.assertContains(response, 'data-phase="enemy"')
        self.assertEqual(response.cookies["turn_phase"].value, "player")
        self.assertEqual(response.cookies["turn_phase"]["max-age"], "")
        self.assertEqual(response.cookies["turn_phase"]["expires"], "")

        response = self.client.get(board_url)
        self.assertContains(response, 'data-phase="player"')
        self.assertEqual(response.cookies["turn_phase"].value, "")
        self.assertEqual(response.cookies["turn_phase"]["max-age"], 0)

        self.client.cookies = SimpleCookie()
        response = self.client.get(board_url)
        self.assertNotContains(response, "data-phase=")

    def test_enemy_phase_renders_even_without_bot_actions(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        for game_card in GameCard.objects.filter(
            game_id=self.game.id, user_id=self.bot_participant.id
        ):
            game_card.state.inDeck = False
            game_card.state.lane = 1
            game_card.state.laneOrdinal = 1
            game_card.state.faceDown = False
            game_card.state.trusted = True
            game_card.state.save()

        response = self.client.post(end_turn_url, {"action": "end_turn"})
        
        self.assertFalse([name for name in response.cookies if name.isdigit()])
        self.assertEqual(response.cookies["turn_phase"].value, "enemy")

        response = self.client.get(board_url)
        self.assertContains(response, 'data-phase="enemy"')
        self.assertNotContains(response, "cardContainer loading")
        self.assertEqual(response.cookies["turn_phase"].value, "player")

    def test_enemy_resolve_special_hands_off_to_player_phase(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        
        bot_cards = list(
            GameCard.objects.filter(
                game_id=self.game.id, user_id=self.bot_participant.id
            ).order_by("id")
        )
        last_card = bot_cards[-1]
        for ordinal, game_card in enumerate(bot_cards[:-1], start=1):
            game_card.state.inDeck = False
            game_card.state.lane = 4
            game_card.state.laneOrdinal = ordinal
            game_card.state.faceDown = False
            game_card.state.trusted = True
            game_card.state.save()
        last_card.state.inDeck = True
        last_card.state.lane = -1
        last_card.state.laneOrdinal = 0
        last_card.state.faceDown = True
        last_card.state.trusted = False
        last_card.state.save()

        response = self.client.post(end_turn_url, {"action": "end_turn"})
        self.assertEqual(response.cookies["turn_phase"].value, "enemy")

        response = self.client.get(board_url)
        self.assertContains(response, 'data-phase="enemy"')
        self.assertContains(response, 'id="timelineSteps"')
        self.assertEqual(response.cookies["turn_phase"].value, "player")
        self.assertFalse(
            GameCard.objects.filter(
                game_id=self.game.id,
                user_id=self.bot_participant.id,
                cssClass="loading",
            ).exists()
        )

        response = self.client.get(board_url)
        self.assertContains(response, 'data-phase="player"')
        self.assertEqual(response.cookies["turn_phase"].value, "")

    def test_enemy_hand_cards_can_be_marked_loading(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        deck_card = self.bot_participant.getNextDeckCard()
        deck_card.state.draw()
        deck_card.state.updateOrdinal(1)
        deck_card.state.save()

        hand_cards = list(
            GameCard.objects.filter(
                game_id=self.game.id, user_id=self.bot_participant.id, state__lane=0
            )
        )
        self.assertEqual(len(hand_cards), 1)

        plays = [
            {
                "cardId": str(deck_card.id),
                "participantId": self.bot_participant.id,
                "laneValue": 0,
                "sourceLane": -2,
                "sourceOrdinal": 0,
                "flipFaceUp": False,
            }
        ]
        updated = views._update_moved_hand_cards(hand_cards, plays)

        self.assertEqual(updated[0].cssClass, "loading")
        self.assertEqual(updated[0].state.lane, -2)
        self.assertEqual(updated[0].state.laneOrdinal, 0)

    def test_update_played_cards_marks_source_state(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        self.client.post(end_turn_url, {"action": "end_turn"})
        self.client.get(board_url)

        bot_lane_card = GameCard.objects.filter(
            game_id=self.game.id,
            user_id=self.bot_participant.id,
            state__lane__gt=0,
            state__trusted=False,
        ).first()
        self.assertIsNotNone(bot_lane_card)
        final_ordinal = bot_lane_card.state.laneOrdinal

        lane_rows = battle_services.context_board(
            GameCard.objects.filter(game_id=self.game.id), self.bot_participant.id
        )["laneRows"]
        plays = [
            {
                "cardId": str(bot_lane_card.id),
                "participantId": self.bot_participant.id,
                "laneValue": bot_lane_card.state.lane,
                "sourceLane": 0,
                "sourceOrdinal": 2,
                "flipFaceUp": True,
            }
        ]
        updated = views._update_played_cards(lane_rows, plays)

        marked = [
            card
            for row in updated
            for card in row["cards"]
            if card.id == bot_lane_card.id
        ]
        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0].cssClass, "loading")
        self.assertEqual(marked[0].state.lane, 0)
        self.assertEqual(marked[0].state.laneOrdinal, 2)
        self.assertNotEqual(marked[0].state.laneOrdinal, final_ordinal)

    def test_foreign_play_cookies_not_consumed_as_player_actions(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        action_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        bot_card = GameCard.objects.filter(
            game_id=self.game.id, user_id=self.bot_participant.id
        ).first()
        bot_lane_cards = GameCard.objects.filter(
            game_id=self.game.id,
            user_id=self.bot_participant.id,
            state__lane__gt=0,
        ).count()
        
        self.client.cookies[str(bot_card.id)] = (
            '{"laneValue": 2, "sourceLane": 0, "sourceOrdinal": 1, "flipFaceUp": true}'
        )
        response = self.client.post(action_url, {"action": "draw"})

        self.assertNotContains(response, "Action error")
        human_hand_cards = GameCard.objects.filter(
            game_id=self.game.id,
            user_id=self.human_participant.id,
            state__lane=0,
        ).count()
        self.assertEqual(human_hand_cards, 1)
        self.assertEqual(
            GameCard.objects.filter(
                game_id=self.game.id,
                user_id=self.bot_participant.id,
                state__lane__gt=0,
            ).count(),
            bot_lane_cards,
        )

    def test_staged_play_cookie_from_board_consumes_the_play(self):
        """A play staged under the card id rendered on the board lands the card."""
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        self.client.post(draw_url, {"action": "draw"})

        hand_card = GameCard.objects.filter(
            game_id=self.game.id,
            user_id=self.human_participant.id,
            state__lane=0,
        ).get()

        # The drag-drop JS reads the card id the board renders and stages the
        # play cookie under that exact name, so the rendered id must be the
        # name the board action resolves back to this card.
        board = self.client.get(board_url)
        hand_fans = re.findall(
            r'<ul class="hand hand-fan" data-fan-index="\d+">(.*?)</ul>',
            board.content.decode(),
            re.DOTALL,
        )
        rendered_hand_card_ids = re.findall(
            r'<li class="cardContainer [^>]+data-card-id="([^"]+)"[^>]*>',
            "".join(hand_fans),
        )

        self.assertEqual(rendered_hand_card_ids, [str(hand_card.id)])

        self.client.cookies[rendered_hand_card_ids[0]] = (
            '{"laneValue": "2", "sourceLane": 0, "sourceOrdinal": 1, "flipFaceUp": false}'
        )
        response = self.client.post(end_turn_url, {"action": "end_turn"})

        self.assertNotContains(response, "Action error")
        hand_card.refresh_from_db()
        self.assertEqual(hand_card.state.lane, 2)
        self.assertTrue(hand_card.state.faceDown)
        self.assertEqual(
            GameCard.objects.filter(
                game_id=self.game.id,
                user_id=self.human_participant.id,
                state__lane=0,
            ).count(),
            0,
        )

    def test_empty_enemy_hand_renders_no_empty_indicator(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        
        self.assertFalse(
            GameCard.objects.filter(game_id=self.game.id, state__lane=0).exists()
        )

        response = self.client.get(board_url)
        content = response.content.decode()

        self.assertEqual(content.count("emptyHand"), 1)

        enemy_hand = re.search(
            r'<ul class="hand enemyHand">(.*?)</ul>', content, re.DOTALL
        )
        self.assertIsNotNone(enemy_hand)
        self.assertNotIn("emptyHand", enemy_hand.group(1))
        self.assertEqual(enemy_hand.group(1).strip(), "")

    def test_enemy_deck_and_hand_have_no_interactive_hooks(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        
        revealed_lane_card = self._initialize_with_hand_card(
            self.human_participant, self.human_cards[1]
        )
        self.human_participant.playCard(
            revealed_lane_card.id, flipFaceUp=True, specialClause=True
        )
        facedown_lane_card = self._initialize_with_hand_card(
            self.human_participant, self.human_cards[2]
        )
        self.human_participant.playCard(facedown_lane_card.id, specialClause=True)

        response = self.client.get(board_url)
        content = response.content.decode()
        
        enemy_deck_hand = re.search(
            r'<div class="enemyDeckHand">(.*?)<ul class="lanes">', content, re.DOTALL
        )
        self.assertIsNotNone(enemy_deck_hand)
        block = enemy_deck_hand.group(1)
        self.assertNotIn("<form", block)
        for button_tag in re.findall(r'<button[^>]*>', block):
            self.assertIn(
                'disabled', button_tag,
                "the enemy deck and hand may only carry inert controls",
            )
        self.assertNotIn("draggable", block)
        self.assertNotIn("data-card-id", block)

        enemy_section = re.search(
            r'<ul class="enemyBoards.*?>(.*?)</ul>\s*<ul class="basic-mat table">',
            content, re.DOTALL
        )
        self.assertIsNotNone(enemy_section)
        self.assertNotIn('tabindex', enemy_section.group(1))
        
        own_board = re.search(
            r'<li class="playerBoard.*?(?=<div class="deckHand)',
            content, re.DOTALL
        )
        self.assertIsNotNone(own_board)
        own_board_markup = own_board.group(0)

        def row_container_tags(row_title):
            return [
                tag
                for row in re.findall(
                    rf'<ul class="cardRow" title="{row_title}">(.*?)</ul>',
                    own_board_markup,
                    re.DOTALL,
                )
                for tag in re.findall(r'<li class="cardContainer[^>]*>', row)
            ]

        flippable_tags = row_container_tags("cards")
        self.assertTrue(flippable_tags)
        for tag in flippable_tags:
            if "faceDown" in tag:
                self.assertIn('tabindex="0"', tag)
            else:
                self.assertNotIn("tabindex", tag)

        trusted_tags = row_container_tags("trustedCards")
        self.assertTrue(trusted_tags)
        for tag in trusted_tags:
            self.assertNotIn("tabindex", tag)
            self.assertIn("data-card-id", tag)

        self.assertContains(response, 'class="card back draw"')

    def test_flip_exhaustion_blocks_but_keeps_face_down_cards_focusable(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        revealed_lane_card = self._initialize_with_hand_card(
            self.human_participant, self.human_cards[1]
        )
        self.human_participant.playCard(
            revealed_lane_card.id, flipFaceUp=True, specialClause=True
        )
        facedown_lane_card = self._initialize_with_hand_card(
            self.human_participant, self.human_cards[2]
        )
        self.human_participant.playCard(facedown_lane_card.id, specialClause=True)

        self.human_participant.flippedCardsAmount = 5
        self.human_participant.save(update_fields=["flippedCardsAmount"])

        response = self.client.get(board_url)
        content = response.content.decode()
        self.assertIn('data-flips-left="0"', content)

        own_board = re.search(
            r'<li class="playerBoard.*?(?=<div class="deckHand)',
            content, re.DOTALL,
        )
        self.assertIsNotNone(own_board)
        own_board_markup = own_board.group(0)

        def row_container_tags(row_title):
            return [
                tag
                for row in re.findall(
                    rf'<ul class="cardRow" title="{row_title}">(.*?)</ul>',
                    own_board_markup,
                    re.DOTALL,
                )
                for tag in re.findall(r'<li class="cardContainer[^>]*>', row)
            ]

        flip_blocked_title = self.human_participant.getTurnAllowances()["blocked_titles"]["flip"]
        lane_tags = row_container_tags("cards")
        self.assertTrue(any("faceDown" in tag for tag in lane_tags))
        for tag in lane_tags:
            css_class = re.search(r'class="([^"]*)"', tag).group(1)
            if "faceDown" in tag:
                self.assertIn("blocked", css_class.split())
                self.assertIn('tabindex="0"', tag)
                self.assertIn(flip_blocked_title, tag)
            else:
                self.assertNotIn("tabindex", tag)

        for tag in row_container_tags("trustedCards"):
            self.assertNotIn("tabindex", tag)

    def test_game_ending_end_turn_renders_player_moves_instead_of_redirecting(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        self.human_participant.defeated = True
        self.human_participant.save()

        response = self.client.post(end_turn_url, {"action": "end_turn"})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-phase="playerMoves"')
        self.assertContains(response, f'data-next-url="{board_url}"')
        self.assertEqual(response.cookies["turn_phase"].value, "enemy")

    def test_finished_game_enemy_phase_targets_result_and_ends_phase_chain(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        result_url = reverse("MMM:viewResult", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        self.human_participant.defeated = True
        self.human_participant.save()

        self.client.post(end_turn_url, {"action": "end_turn"})

        response = self.client.get(board_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-phase="enemy"')
        self.assertContains(response, f'data-next-url="{result_url}"')

        self.assertEqual(response.cookies["turn_phase"].value, "")
        self.assertEqual(response.cookies["turn_phase"]["max-age"], 0)

        response = self.client.get(board_url)
        self.assertRedirects(response, result_url)

    def test_game_ending_draw_targets_result_url(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        result_url = reverse("MMM:viewResult", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        # force the game to be over before the draw POST
        self.bot_participant.defeated = True
        self.bot_participant.save()

        # a non-end_turn action render on a finished game still renders its
        # animation (200, not a redirect), but navigates to the result page
        response = self.client.post(draw_url, {"action": "draw"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-next-url="{result_url}"')

    def test_plain_board_get_on_finished_game_redirects_to_result(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        result_url = reverse("MMM:viewResult", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        self.human_participant.defeated = True
        self.human_participant.save()

        # a plain board visit on a finished game (no animation cookies, no
        # phase signal) has nothing left to play out and skips to the results
        self.client.cookies = SimpleCookie()
        response = self.client.get(board_url)
        self.assertRedirects(response, result_url)

    def test_finished_game_redirect_deletes_stale_phase_cookie(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        result_url = reverse("MMM:viewResult", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        self.human_participant.defeated = True
        self.human_participant.save()

        # a stale phase signal never lingers on a finished game: the redirect
        # response deletes it (a stale "player" signal renders nothing, so
        # this visit has no sequence left to play out)
        self.client.cookies = SimpleCookie()
        self.client.cookies["turn_phase"] = "player"
        response = self.client.get(board_url)
        self.assertRedirects(response, result_url)
        self.assertEqual(response.cookies["turn_phase"].value, "")
        self.assertEqual(response.cookies["turn_phase"]["max-age"], 0)
        self.assertEqual(response.cookies["turn_phase"]["path"], board_url)

    def test_result_redirects_back_to_board_when_unfinished(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        result_url = reverse("MMM:viewResult", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        # the viewResult guard is unchanged: an unfinished game has no result
        # page yet and bounces back to the board
        response = self.client.get(result_url)
        self.assertRedirects(response, board_url)

    # ------------------------------------------------------------------
    # Blocked-board-visuals tests
    # ------------------------------------------------------------------

    def _create_all_resolve_game(self):
        """Create a game where the human has 4 all-Resolve cards (intCount=0, spdCount=0, tactics=0)."""
        player = Player.objects.create(name="ResolvePlayer")
        owner = CardOwnerHistory.objects.create(cardOwner=player)
        cards = [self._create_owned_card(owner, f"Resolve-{i}", 3) for i in range(4)]
        deck = Deck.create(
            player.id, deckTitle="All Resolve", newDescription="all resolve", newDeckCards=cards
        )
        bot = Player.objects.create(name="ResolveBot")
        bot_owner = CardOwnerHistory.objects.create(cardOwner=bot)
        bot_cards = [self._create_owned_card(bot_owner, f"Bot-{i}", i % 4) for i in range(4)]
        bot_deck = Deck.create(
            bot.id, deckTitle="Bot deck", newDescription="test", newDeckCards=bot_cards
        )
        history = BattleHistory.objects.create(challenger=player)
        game = Game.objects.create(title="ResolveGame", history=history, roundNumber=0)
        participant = history.addHumanChallenger(
            challengerPlayer_id=player.id, startingCard_id=cards[0].id, deck_id=deck.id,
        )
        history.addRobotChallenger(
            challengerPlayer_id=bot.id, startingCard_id=bot_cards[0].id, deck_id=bot_deck.id,
        )
        return game, player, participant

    def test_fresh_board_no_blocked(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.get(board_url)
        content = response.content.decode()

        # No element has "blocked" as a CSS class on a fresh board
        for pattern in ('class="deck blocked"', 'class="card back draw blocked"'):
            self.assertNotIn(pattern, content)
        self.assertNotRegex(content, r'class="[^"]*blocked[^"]*"')

        # The draw button renders with its standard class
        self.assertContains(response, 'class="card back draw"')

    def test_hand_cards_draggable_when_not_blocked(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.post(draw_url, {"action": "draw"})
        content = response.content.decode()

        # Hand card has draggable="true" when plays_left > 0
        self.assertIn('draggable="true"', content)
        # No blocked class on the hand card container
        self.assertNotIn('blocked"', content)

    def test_all_resolve_draw_exhaustion(self):
        game, player, participant = self._create_all_resolve_game()
        confirm_url = reverse("MMM:confirmChallenge", args=[game.id, player.id])
        draw_url = reverse("MMM:boardAction", args=[game.id, player.id])

        self.client.post(confirm_url)

        # Exhaust the single draw (intCount=0 → draws_left=1)
        response = self.client.post(draw_url, {"action": "draw"})

        self.assertRegex(response.content.decode(), r'class="deck blocked(?:\s|")')
        self.assertContains(response, "disabled")
        self.assertContains(response, "Draw limit reached")

    def test_mid_turn_play_flip_exhaustion(self):
        game, player, participant = self._create_all_resolve_game()
        confirm_url = reverse("MMM:confirmChallenge", args=[game.id, player.id])
        draw_url = reverse("MMM:boardAction", args=[game.id, player.id])
        end_turn_url = reverse("MMM:boardAction", args=[game.id, player.id])
        board_url = reverse("MMM:viewBoard", args=[game.id, player.id])

        self.client.post(confirm_url)

        # Round 1: draw, end_turn, enemy GET, board GET (to clear phase)
        self.client.post(draw_url, {"action": "draw"})
        self.client.post(end_turn_url, {"action": "end_turn"})
        self.client.get(board_url)
        self.client.get(board_url)

        # Round 2: draw 1 card into hand
        self.client.post(draw_url, {"action": "draw"})

        # Find a card in hand (there are 2 — one from each round)
        hand_card = GameCard.objects.filter(
            game_id=game.id, user_id=participant.id, state__lane=0
        ).first()

        # Stage a play cookie that plays the card face-down (no flip) to consume
        # both a play and leave the card face-down in the lane
        self.client.cookies[str(hand_card.id)] = (
            '{"laneValue": 4, "sourceLane": 0, "sourceOrdinal": 1, "flipFaceUp": false}'
        )

        # POST draw: cookie consumption exhausts plays+flips, then draw fails
        response = self.client.post(draw_url, {"action": "draw"})
        content = response.content.decode()

        # Hand cards are blocked with draggable="false" and play tooltip
        self.assertIn('draggable="false"', content)
        self.assertIn("Play limit reached", content)

        # Face-down lane cards are blocked with flip tooltip
        self.assertIn("faceDown", content)
        self.assertIn("Flip limit reached", content)

    def test_turn_counters_hidden(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.post(draw_url, {"action": "draw"})
        content = response.content.decode()

        # id="turnCounters" hidden is in the DOM
        self.assertContains(response, 'id="turnCounters"')
        self.assertContains(response, "hidden")
        # Counter text still rendered inside the hidden span
        self.assertIn("1d", content)

    # ------------------------------------------------------------------
    # Staged-action-blocking tests
    # ------------------------------------------------------------------

    def test_staged_play_blocks_remaining_hand(self):
        """After staging a play via cookie, remaining hand cards get .blocked and draggable="false"."""
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        # Draw 2 cards into hand (intCount=1 → draws_left=2)
        for _ in range(2):
            self.client.post(draw_url, {"action": "draw"})

        self.human_participant.refresh_from_db()
        # plays_left = max(0, 2+tactics-drawn-flipped-played) = max(0, 2+1-2-0-0) = 1
        self.assertEqual(self.human_participant.getTurnAllowances()["plays_left"], 1)

        hand_cards = list(GameCard.objects.filter(
            game_id=self.game.id, user_id=self.human_participant.id, state__lane=0
        ))
        self.assertEqual(len(hand_cards), 2)

        # Stage 1 play via the card's id (play to lane 4, face down)
        self.client.cookies[str(hand_cards[0].id)] = (
            '{"laneValue": 4, "sourceLane": 0, "sourceOrdinal": 1, "flipFaceUp": false}'
        )

        # POST draw: cookie consumption exhausts the single play slot
        response = self.client.post(draw_url, {"action": "draw"})

        # Remaining hand card must be blocked (draggable="false" on the hand card,
        # not the profile image)
        self.assertIn("Play limit reached", response.content.decode())

    def test_staged_flip_blocks_remaining_lane_cards(self):
        """After exhausting flips via a play+flip cookie, face-down lane cards show blocked."""
        game, player, participant = self._create_all_resolve_game()
        confirm_url = reverse("MMM:confirmChallenge", args=[game.id, player.id])
        draw_url = reverse("MMM:boardAction", args=[game.id, player.id])

        self.client.post(confirm_url)

        # Draw 1 card into hand
        self.client.post(draw_url, {"action": "draw"})

        hand_card = GameCard.objects.filter(
            game_id=game.id, user_id=participant.id, state__lane=0
        ).first()

        # Play it face-down to lane 4 (flipFaceUp=false) via its card id.
        # With int=0, spd=0, after 1 draw + 1 face-down play:
        # flips_left = max(0, 1+min(0, 1-1-1)-0) = 0
        self.client.cookies[str(hand_card.id)] = (
            '{"laneValue": 4, "sourceLane": 0, "sourceOrdinal": 1, "flipFaceUp": false}'
        )

        response = self.client.post(draw_url, {"action": "draw"})
        self.assertIn("Flip limit reached", response.content.decode())

    def test_over_playing_shrinks_draw_budget(self):
        """With low int+spd, staging plays reduces draws_left via the min clause so the deck shows .blocked."""
        game, player, participant = self._create_all_resolve_game()
        confirm_url = reverse("MMM:confirmChallenge", args=[game.id, player.id])
        board_url = reverse("MMM:viewBoard", args=[game.id, player.id])

        self.client.post(confirm_url)

        # int=0, spd=0 → draws_left = max(0, 1 + min(0, 1-played-flipped) - drawn)
        # Over-playing: played=2, drawn=0 → min(0, 1-2) = -1 → draws_left = 0
        participant.playedCardsAmount = 2
        participant.save()

        allowances = participant.getTurnAllowances()
        self.assertEqual(allowances["draws_left"], 0)

        response = self.client.get(board_url)
        self.assertRegex(response.content.decode(), r'class="deck blocked(?:\s|")')

    # ------------------------------------------------------------------
    # Hologram row tests
    # ------------------------------------------------------------------

    def test_player_lanes_have_hologram_row(self):
        """Player lanes render an empty .hologramRow above the card rows."""
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.get(board_url)
        content = response.content.decode()

        # Count hologramRow elements in player lanes (should be 4 — one per lane)
        self.assertEqual(content.count('class="hologramRow"'), 4)

    def test_enemy_lanes_have_no_hologram_row(self):
        """Enemy lanes must NOT contain a .hologramRow."""
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.get(board_url)
        content = response.content.decode()

        # Enemy board section should not mention hologramRow
        enemy_section = re.search(
            r'<ul class="enemyBoards.*?>(.*?)</ul>\s*<ul class="basic-mat table">',
            content, re.DOTALL
        )
        if enemy_section:
            self.assertNotIn('hologramRow', enemy_section.group(1))

    def test_ghost_class_defined_in_stylesheet(self):
        """The .ghost CSS class must be defined in the card drag-drop stylesheet."""
        import os
        css_path = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static', 'cardDragDrop.css')
        with open(css_path) as f:
            css_content = f.read()
        self.assertIn('.ghost', css_content)
        self.assertIn('opacity: 0.4', css_content)
        self.assertIn('filter: grayscale(0.3)', css_content)
        self.assertIn('pointer-events: none', css_content)

    def test_board_cursor_affordances_are_scoped_and_budget_guarded(self):
        """Active flip and draw affordances do not leak to blocked/enemy/empty controls."""
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.css')) as css_file:
            drag_css = css_file.read()
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()

        self.assertIn(
            '.playerScreen .playerBoard ul.cardRow > li.cardContainer.faceDown:not(.blocked)',
            drag_css,
        )
        self.assertIn(
            '.playerScreen .playerBoard ul.hologramRow .hologram li.cardContainer.faceDown:not(.blocked)',
            drag_css,
        )
        self.assertNotIn(
            '.hologram .cardContainer.faceDown:hover {\n     cursor: pointer;',
            drag_css,
        )
        self.assertIn('cursor: not-allowed', cards_css)

        drawable_draw = (
            '.playerBoard .deck-stack .active-deck:not(.blocked) '
            'button.draw:not(.blocked):not(:disabled)'
        )
        self.assertIn(drawable_draw, cards_css)
        # The draw button is itself a card element: it reacts to hover only
        # through the JS-managed .card-hover class, never a native rule.
        self.assertNotIn(drawable_draw + ':hover', cards_css)
        self.assertIn(drawable_draw + '.card-hover', cards_css)
        self.assertIn(drawable_draw + ':focus-visible', cards_css)
        self.assertIn('transition: transform 0.15s ease-out', cards_css)
        self.assertIn('transform: rotate(', cards_css)

    def test_played_hand_ghost_cards_never_show_grab_cursor(self):
        """Staged hand ghosts cannot be grabbed, so their cursor must stay neutral."""
        import os

        with open(os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static', 'cards.css')) as css_file:
            cards_css = css_file.read()

        def rule_block(source, selector):
            start = source.index(selector)
            depth = 0
            for offset in range(source.index('{', start), len(source)):
                depth += source[offset] == '{'
                depth -= source[offset] == '}'
                if depth == 0:
                    return source[start:offset + 1]
            raise AssertionError(f'unclosed rule block for {selector}')

        ghost_selector = 'ul.hand li.cardContainer.ghost{'
        ghost_rule = rule_block(cards_css, ghost_selector)
        self.assertLess(cards_css.index('ul.hand li.cardContainer{'), cards_css.index(ghost_selector))

        self.assertEqual(ghost_rule.count('cursor: default'), 2)
        self.assertIn('&::after', ghost_rule)
        self.assertNotIn('grab', ghost_rule)
        self.assertNotIn('pointer', ghost_rule)

        hand_rule = rule_block(cards_css, 'ul.hand li.cardContainer{')
        self.assertEqual(hand_rule.count('cursor:'), 1)
        self.assertIn('&::after', hand_rule)
        self.assertIn('cursor: grab', hand_rule)

    def test_hand_card_visibility_css_keeps_footer_and_body_separated(self):
        """Card-type footers keep the original bottom-anchored look on every card."""
        import os

        css_path = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static', 'cards.css')
        with open(css_path) as css_file:
            cards_css = css_file.read()

        # The normal small-card footer keeps its original bottom-anchored style.
        self.assertIn('font-size: 7px', cards_css)
        self.assertIn('margin-bottom: -2.75rem', cards_css)
        self.assertIn('.smallCardInfo .cardType', cards_css)
        # Static cards reuse the same footer look as normal cards.
        self.assertIn('.playingCards .card.staticCard .smallCardInfo .cardType', cards_css)
        self.assertIn('margin-bottom: -1px', cards_css)
        # No centered suit overlay was introduced on static small cards.
        self.assertNotIn('.playingCards .card.smallCard.staticCard .suit::after', cards_css)
        self.assertIn('height: var(--hand-row-height)', cards_css)
        self.assertIn('margin-bottom: 0', cards_css)

    def test_large_hand_layout_and_animation_hooks_are_fan_aware(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()

        self.assertIn('.hand-scroll', cards_css)
        self.assertIn('.hand-fan', cards_css)
        self.assertIn('overflow-x: auto', cards_css)
        self.assertIn(
            '.playerScreen .deckHand .hand-scroll ul.hand li.cardContainer',
            drag_js,
        )
        self.assertIn('HAND_FAN_SIZE = 9', loading_js)
        self.assertIn('handSourceForOrdinal', loading_js)
        self.assertNotIn("document.querySelector('.playerScreen .deckHand .hand')", loading_js)

    def test_keyboard_selection_contract_uses_playable_fans_and_preview_hooks(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.css')) as css_file:
            drag_css = css_file.read()

        self.assertIn('keyboardSelection', drag_js)
        self.assertIn('playableKeyboardCards', drag_js)
        self.assertIn('input[name="card_id"]', drag_js)
        self.assertIn('_noZeroOrdinal', drag_js)
        self.assertIn("if (key === '0' || key === 'Backspace') {", drag_js)
        self.assertIn('keyboard-preview', drag_js)
        self.assertIn('clearKeyboardSelection', drag_js)
        self.assertIn('createupdateCookie', drag_js)

        self.assertIn('class KeyboardSelectionControl {', drag_js)
        self.assertIn('class CardDragDropSystem {', drag_js)
        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]
        self.assertIn('selectKeyboardCard(card', control_class)
        self.assertIn('clearKeyboardSelection({removePreview', control_class)
        self.assertIn('flipKeyboardFocusedCard(event)', control_class)
        self.assertIn('_keyboardFlipTarget(event)', control_class)
        self.assertIn('_keyboardHologramRow(laneValue)', control_class)
        self.assertIn('onFocusIn(card)', control_class)
        self.assertIn('onFocusOut(card)', control_class)
        self.assertIn('this.parent', control_class)

        parent_class = drag_js[control_class_end:]
        self.assertIn('    onKeyboardKeyDown(event)', parent_class)
        self.assertIn('    onHandCardClick(event)', parent_class)
        self.assertIn(
            'this._keyboardSelectionControl._noZeroOrdinal(digitBuffer)',
            parent_class,
        )
        self.assertIn(
            'this._keyboardSelectionControl._noZeroOrdinal(lastDigitBuffer)',
            parent_class,
        )
        self.assertIn(
            'this._keyboardSelectionControl._confirmGhostFlipSelection(event)',
            parent_class,
        )

        keydown_code = drag_js[
            drag_js.index('    onKeyboardKeyDown(event)'):
            drag_js.index('    selectOrderedCard(')
        ]
        backspace_branch_start = keydown_code.index("if (key === '0' || key === 'Backspace') {")
        backspace_branch = keydown_code[
            backspace_branch_start:
            keydown_code.index('}', backspace_branch_start) + 1
        ]
        self.assertIn('this._cancelKeyboardSelectionFromEvent(event);', backspace_branch)
        self.assertIn(
            'this._keyboardSelectionControl._noZeroOrdinal(digitBuffer)',
            keydown_code,
        )
        self.assertIn('digitBuffer.slice(-1)', keydown_code)
        self.assertLess(
            keydown_code.index('digitBuffer.slice(-1)'),
            keydown_code.rindex('this.clearKeyboardSelection();'),
        )

        arrow_branch_index = keydown_code.index('ArrowDown: 1')
        step_block_start = keydown_code.index('const stepDirection =')
        digit_guard_index = keydown_code.index("event.repeat || !/^[1-9]$/.test(key)")
        self.assertLess(arrow_branch_index, step_block_start)
        self.assertLess(step_block_start, digit_guard_index)
        self.assertIn("event.code === 'NumpadAdd'", keydown_code)
        self.assertIn("event.code === 'NumpadSubtract'", keydown_code)
        step_block = keydown_code[step_block_start:digit_guard_index]
        self.assertNotIn('event.repeat', step_block)
        self.assertIn("key === '+'", step_block)
        self.assertIn("key === '='", step_block)
        self.assertIn("key === '-'", step_block)
        self.assertIn("key === '_'", step_block)
        self.assertIn('(currentIndex + stepDirection) % eligibleCards.length', step_block)
        self.assertIn('eligibleCards.length >= 2', step_block)
        self.assertIn("selectKeyboardCard(eligibleCards[0], '1')", step_block)
        self.assertIn(
            'selectKeyboardCard(eligibleCards[nextIndex], String(nextIndex + 1))',
            step_block,
        )

        flip_branch_start = keydown_code.index(
            "if (!activeSelection && (key === 'Enter' || key === ' ')) {"
        )
        selection_confirm_index = keydown_code.index(
            'this.confirmKeyboardSelection()) event.preventDefault();'
        )
        self.assertLess(flip_branch_start, selection_confirm_index)
        self.assertIn('this.flipKeyboardFocusedCard(event)', keydown_code[flip_branch_start:])

        flip_method_code = control_class[
            control_class.index('    flipKeyboardFocusedCard(event)'):
            control_class.index('    _keyboardHologramRow(laneValue)')
        ]
        self.assertIn('.playerBoard ul.cardRow li.cardContainer.faceDown', flip_method_code)
        self.assertIn('.hologram.keyboard-staged .cardContainer.faceDown', flip_method_code)
        self.assertIn('this.parent._laneValueForCard(card)', flip_method_code)
        self.assertIn(
            'this._predicates.remainingAllowances().flips <= 0',
            flip_method_code,
        )
        self.assertIn("classList.contains('blocked')", flip_method_code)
        self.assertIn("classList.contains('ghost')", flip_method_code)
        self.assertIn(
            'this.parent.onFaceDownCardClick(event, laneValue)',
            flip_method_code,
        )
        self.assertIn('event.preventDefault()', flip_method_code)
        self.assertIn('_laneValueForCard(card) {', drag_js)
        self.assertIn("card.closest('li.lane').classList[1]", drag_js)
        selection_code = control_class[
            control_class.index('    selectKeyboardCard(card'):
            control_class.index('    moveKeyboardSelection(laneValue)')
        ]
        self.assertNotIn('createupdateCookie', selection_code)
        self.assertIn('card.focus({ preventScroll: true })', selection_code)
        self.assertIn("typeof card.focus === 'function'", selection_code)
        self.assertIn('activeElement.blur()', control_class)
        self.assertIn('card.contains(activeElement)', control_class)

        self.assertIn("document.addEventListener('click', this.keyboardClickHandler);", drag_js)
        self.assertIn("document.removeEventListener('click', this.keyboardClickHandler);", drag_js)
        click_code = drag_js[
            drag_js.index('    onHandCardClick(event)'):
            drag_js.index('    onCardDragStart(e)')
        ]
        self.assertIn(
            "closest('.playerScreen .deckHand .hand-scroll ul.hand li.cardContainer')",
            click_code,
        )
        self.assertIn('event.button !== 0', click_code)
        self.assertIn('_isTextControlTarget(target)', click_code)
        self.assertIn('_keyboardTransitionActive()', click_code)
        self.assertIn('_keyboardActionAllowed(event)', click_code)
        self.assertIn('lastDragEndedAt', click_code)
        self.assertIn('playableKeyboardCards()', click_code)
        self.assertIn('this.selectKeyboardCard(card, String(index + 1))', click_code)
        self.assertNotIn('confirmKeyboardSelection', click_code)
        self.assertNotIn('_stagePlay', click_code)
        self.assertNotIn('createupdateCookie', click_code)
        drag_end_code = drag_js[
            drag_js.index('    onCardDragEnd(e)'):
            drag_js.index('    onDropZoneDragOver(e)')
        ]
        self.assertIn('this.lastDragEndedAt = Date.now();', drag_end_code)

        self.assertIn('li.cardContainer.keyboard-selected', drag_css)
        self.assertIn('.hologram.keyboard-preview', drag_css)

        selected_block = drag_css[drag_css.index('li.cardContainer.keyboard-selected {'):]
        selected_block = selected_block[:selected_block.index('}')]
        preview_block = drag_css[drag_css.index('ul.hologramRow .hologram.keyboard-preview {'):]
        preview_block = preview_block[:preview_block.index('}')]
        for selection_block in (selected_block, preview_block):
            self.assertIn('outline: 3px solid', selection_block)
            self.assertIn('outline-offset: 4px', selection_block)
            self.assertNotIn('rgba(255, 204, 0', selection_block)

        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        response = self.client.post(
            reverse("MMM:boardAction", args=[self.game.id, self.human.id]),
            {"action": "draw"},
        )
        content = response.content.decode()
        self.assertIn('data-fan-index="0"', content)
        self.assertIn('data-card-id=', content)
        self.assertIn('name="card_id"', content)

    def test_keyboard_confirmation_contract_preserves_staging_and_guards(self):
        import os

        js_path = os.path.join(
            os.path.dirname(__file__), '..', 'var', 'www', 'static', 'cardDragDrop.js'
        )
        with open(js_path) as js_file:
            drag_js = js_file.read()

        self.assertIn("zone.addEventListener('click', this.onDropZoneClick.bind(this));", drag_js)
        self.assertIn('confirmKeyboardSelection', drag_js)
        self.assertIn('moveKeyboardSelection', drag_js)
        self.assertIn('ArrowLeft: -1', drag_js)
        self.assertIn('ArrowRight: 1', drag_js)
        self.assertIn('ArrowUp: -1', drag_js)
        self.assertIn('ArrowDown: 1', drag_js)
        self.assertIn(
            'this.createupdateCookie(cardId, laneValue, false, sourceLane, sourceOrdinal);',
            drag_js,
        )
        self.assertIn("clearKeyboardSelection({removePreview: false})", drag_js)
        staging_code = drag_js[
            drag_js.index('    _stagePlay('):
            drag_js.index('    _buildPlayHologram(')
        ]
        self.assertIn("card.classList.add('ghost')", staging_code)
        self.assertIn("card.setAttribute('draggable', 'false')", staging_code)
        self.assertIn("card.setAttribute('tabindex', '0')", staging_code)
        self.assertNotIn("card.removeAttribute('tabindex')", staging_code)
        self.assertIn('this.staged.plays++;', staging_code)
        self.assertIn('this.applyTurnAffordances();', staging_code)

        keyboard_preview_code = drag_js[
            drag_js.index('        if (keyboardPreview) {', drag_js.index('    _buildPlayHologram(')):
            drag_js.index('        } else {', drag_js.index('    _buildPlayHologram('))
        ]
        self.assertNotIn('onFaceDownCardClick', keyboard_preview_code)
        self.assertIn("hologram.classList.add('keyboard-preview')", drag_js)

        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]
        self.assertIn('    confirmKeyboardSelection(laneValue = null)', control_class)
        self.assertIn('    moveKeyboardSelection(laneValue)', control_class)

        parent_class = drag_js[control_class_end:]
        self.assertIn(
            'this._keyboardSelectionControl.confirmKeyboardSelection(laneValue)',
            parent_class,
        )
        self.assertIn(
            'this._keyboardSelectionControl.moveKeyboardSelection(laneValue)',
            parent_class,
        )

        confirm_code = control_class[
            control_class.index('    confirmKeyboardSelection(laneValue'):
            control_class.index('    clearKeyboardSelection({removePreview')
        ]
        self.assertIn('moveKeyboardSelection(requestedLane)', confirm_code)
        self.assertIn('selection.hologram.remove()', confirm_code)
        self.assertIn(
            'this.parent._buildPlayHologram(card, requestedLane, false, selection.rotation)',
            confirm_code,
        )
        self.assertIn('this._keyboardHologramRow(requestedLane)', confirm_code)
        self.assertIn("hologram.classList.add('keyboard-staged')", confirm_code)
        self.assertIn("hologram.dataset.keyboardStaged = 'true'", confirm_code)
        self.assertNotIn("hologram.classList.add('keyboard-preview')", confirm_code)
        self.assertIn(
            'this.parent._stagePlay(card, requestedLane, hologram, true, selection)',
            confirm_code,
        )
        self.assertNotIn('createupdateCookie', confirm_code)
        self.assertNotIn('tabindex', confirm_code)
        self.assertNotIn('remainingAllowances().flips', confirm_code)

        else_branch_start = drag_js.index(
            '        } else {', drag_js.index('    _buildPlayHologram(')
        )
        non_preview_code = drag_js[
            else_branch_start:drag_js.index('        }', else_branch_start + 1)
        ]
        self.assertIn("copycard.classList.add('faceDown')", non_preview_code)
        self.assertIn("copycard.classList.remove('keyboard-selected')", non_preview_code)
        self.assertIn("copycard.removeAttribute('aria-selected')", non_preview_code)
        self.assertIn('delete copycard.dataset.keyboardSelected;', non_preview_code)
        self.assertIn("copycard.setAttribute('tabindex', '0')", non_preview_code)
        self.assertNotIn("copycard.removeAttribute('tabindex')", non_preview_code)
        self.assertNotIn('onFaceDownCardClick', non_preview_code)
        self.assertIn("copycard.removeAttribute('tabindex')", keyboard_preview_code)

        self.assertIn("hologram.dataset.stagedForCardId = selection.cardId", confirm_code)
        self.assertIn('this._mirrorStagedFocus(card, hologram)', confirm_code)
        mirror_helper_code = control_class[
            control_class.index('    _mirrorStagedFocus(card, hologram) {'):
            control_class.index('    onFocusIn(card)')
        ]
        self.assertIn("'focusin'", mirror_helper_code)
        self.assertIn("'focusout'", mirror_helper_code)
        self.assertIn("ghostCard.classList.add('keyboard-selected')", mirror_helper_code)
        self.assertIn("ghostCard.classList.remove('keyboard-selected')", mirror_helper_code)

    def test_touch_drag_contract_reuses_staging_and_guards(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.css')) as css_file:
            drag_css = css_file.read()

        self.assertIn(
            "card.addEventListener('dragstart', this.onCardDragStart.bind(this));",
            drag_js,
        )
        self.assertIn(
            "card.addEventListener('touchstart', this.onCardTouchStart.bind(this), { passive: true });",
            drag_js,
        )
        self.assertIn(
            "document.addEventListener('touchmove', this._touchMoveHandler, { passive: false });",
            drag_js,
        )

        touch_code = drag_js[
            drag_js.index('    onCardTouchStart(event)'):
            drag_js.index('    _stagePlay(')
        ]
        self.assertIn('remainingAllowances().plays <= 0', touch_code)
        self.assertIn('_keyboardTransitionActive()', touch_code)
        self.assertIn('_isPlayableKeyboardCard(card)', touch_code)
        self.assertIn('TOUCH_DRAG_SLOP_PX', touch_code)
        self.assertIn('Math.abs(dx) > Math.abs(dy)', touch_code)
        self.assertIn('this.cancelCardTouchDrag();', touch_code)
        self.assertIn('highlightAllDropZones(true)', touch_code)
        self.assertIn('highlightAllDropZones(false)', touch_code)
        self.assertIn("wrap.classList.add('playingCards', 'touch-drag-clone')", touch_code)
        self.assertIn("wrap.style.setProperty('--board-scale'", touch_code)
        self.assertIn('drag.clone = wrap', touch_code)
        self.assertIn('document.elementFromPoint', touch_code)
        self.assertIn('this._laneValueForCard(lane)', touch_code)
        self.assertIn('dropZones.has(laneValue)', touch_code)
        self.assertIn('this.onDropZoneDrop({', touch_code)
        self.assertIn('currentTarget: this.dropZones.get(laneValue).element', touch_code)
        self.assertIn('this.onHandZoneDrop({', touch_code)
        self.assertIn('button: 0', touch_code)
        self.assertIn('if (drag.lifted) this.lastDragEndedAt = Date.now();', touch_code)
        self.assertNotIn('createupdateCookie', touch_code)
        self.assertNotIn('_buildPlayHologram', touch_code)

        setup_code = drag_js[
            drag_js.index('    setupKeyboardSelection()'):
            drag_js.index('    _hasPlayerBoard()')
        ]
        self.assertIn('this.cancelCardTouchDrag();', setup_code)
        destroy_code = drag_js[
            drag_js.index('    destroy() {'):
            drag_js.index('document.addEventListener(\'DOMContentLoaded\'')
        ]
        self.assertIn('this.cancelCardTouchDrag();', destroy_code)

        self.assertIn(
            '.playerScreen .deckHand .hand-scroll ul.hand li.cardContainer {\n'
            '    touch-action: pan-x;',
            drag_css,
        )
        self.assertIn('-webkit-touch-callout: none', drag_css)
        self.assertIn('user-select: none', drag_css)
        clone_rule = drag_css[drag_css.index('.touch-drag-clone {'):]
        clone_rule = clone_rule[:clone_rule.index('}')]
        self.assertIn('position: fixed', clone_rule)
        self.assertIn('pointer-events: none', clone_rule)
        self.assertIn('touch-action: none', clone_rule)
        self.assertIn('font-size: calc(1rem * var(--board-scale, 1))', clone_rule)
        self.assertEqual(drag_css.count('touch-action:'), 2)
        clone_li_rule = drag_css[drag_css.index('.touch-drag-clone > li.cardContainer {'):]
        clone_li_rule = clone_li_rule[:clone_li_rule.index('}')]
        self.assertIn('display: block', clone_li_rule)
        self.assertIn('list-style: none', clone_li_rule)

    def test_touch_drag_stages_and_returns_cards_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = FAKE_ELEMENT_NAVIGATION_CORE + r"""
const documentListeners = {};
const windowListeners = {};
const holdTimers = [];
let nextTimerId = 1;
let nowMs = 1000;
Date.now = () => nowMs;

const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const matTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(matTable);
const playerBoard = new FakeElement('div', 'playerBoard');
matTable.appendChild(playerBoard);

const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const holoRows = [];
['Intelligence', 'Speed', 'Visciousness', 'Resolve'].forEach((laneName) => {
    const lane = new FakeElement('li', `lane ${laneName}`);
    lane.classList[1] = laneName;
    lanesEl.appendChild(lane);
    const holoRow = new FakeElement('ul', 'hologramRow');
    lane.appendChild(holoRow);
    holoRows.push(holoRow);
});

const deckHand = new FakeElement('div', 'deckHand handContainer');
matTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);

const makeHandCard = (cardId, cardLane, sourceOrdinal) => {
    const card = new FakeElement('li', 'cardContainer');
    card.setAttribute('tabindex', '0');
    card.setAttribute('draggable', 'true');
    card.dataset.cardLane = String(cardLane);
    card.dataset.sourceLane = '0';
    card.dataset.sourceOrdinal = String(sourceOrdinal);
    const cardFace = new FakeElement('div', 'card smallCard');
    card.appendChild(cardFace);
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', 'card_id');
    input.setAttribute('value', String(cardId));
    card.appendChild(input);
    handList.appendChild(card);
    return card;
};
const handA = makeHandCard(301, 1, 1);
const handB = makeHandCard(302, 3, 2);
const handC = makeHandCard(303, 2, 3);

const endTurnForm = new FakeElement('form', 'cardActionForm');
playerScreen.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);
const focusedHandCardInput = new FakeElement('input');
focusedHandCardInput.setAttribute('type', 'hidden');
focusedHandCardInput.setAttribute('name', 'focused_hand_card');
focusedHandCardInput.setAttribute('value', '1');
endTurnForm.appendChild(focusedHandCardInput);

const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
    drawBlockedTitle: 'draw blocked',
    playBlockedTitle: 'play blocked',
    flipBlockedTitle: 'flip blocked',
};

let pointElement = null;
const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) { return body.querySelector(selector); },
    querySelectorAll(selector) { return body.querySelectorAll(selector); },
    getElementById(id) {
        if (id === 'turnLimits') return turnLimits;
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) {
        (documentListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    elementFromPoint() { return pointElement; },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};

const cookieWrites = [];
Object.defineProperty(fakeDocument, 'cookie', {
    set(value) { cookieWrites.push(value); },
    get() { return cookieWrites.join('; '); },
});

for (const el of [body, playerScreen, playerBoard, endTurnForm, endTurnButton, handA, handB, handC, ...holoRows]) {
    el.focus = () => { fakeDocument.activeElement = el; };
    el.blur = () => { if (fakeDocument.activeElement === el) fakeDocument.activeElement = body; };
}

global.document = fakeDocument;
global.window = {
    addEventListener(event, handler) {
        (windowListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        windowListeners[event] = (windowListeners[event] ?? []).filter((h) => h !== handler);
    },
    cardDragDrop: null,
    location: { pathname: '/MMM/game/1/board/1/action/' },
    setTimeout(callback) {
        const id = nextTimerId++;
        holdTimers.push({ id, callback });
        return id;
    },
    clearTimeout(id) {
        const index = holdTimers.findIndex((task) => task.id === id);
        if (index !== -1) holdTimers.splice(index, 1);
    },
};
global.CSS = { escape: (value) => String(value) };
global.getComputedStyle = () => ({ getPropertyValue: () => '1' });
global.Element = function Element() {};
global.MutationObserver = function (handler) {
    this.observe = () => {};
    this.disconnect = () => {};
};

const dragCode = __DRAG_JS__;
eval(dragCode);
(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const zoneFor = (laneValue) => fakeDocument.getElementById(`drop-zone-${laneValue}`);
const cloneInBody = () => descendantsInOrder(body).find(
    (el) => el.classList.contains('touch-drag-clone')
);
const zoneHighlighted = () => [1, 2, 3, 4].every(
    (laneValue) => zoneFor(laneValue).classList.contains('drop-zone-highlight')
);
const stagedHologramFor = (cardId) => holoRows.flatMap((row) => row.children).find(
    (el) => el.dataset.stagedForCardId === String(cardId)
);

const touchEvent = (type, touch) => {
    let prevented = false;
    return {
        type,
        changedTouches: [touch],
        touches: type === 'touchend' || type === 'touchcancel' ? [] : [touch],
        preventDefault() { prevented = true; },
        get prevented() { return prevented; },
    };
};
const cardTouchStart = (card, touch) => {
    const event = touchEvent('touchstart', touch);
    event.currentTarget = card;
    (card.eventHandlers['touchstart'] ?? []).forEach((handler) => handler(event));
    return event;
};
const documentTouch = (type, touch) => {
    const event = touchEvent(type, touch);
    (documentListeners[type] ?? []).forEach((handler) => handler(event));
    return event;
};

const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};

pointElement = handList;

cardTouchStart(handA, { identifier: 7, clientX: 120, clientY: 400 });
assert('touching a playable hand card tracks the gesture',
    system.touchDrag !== null && (documentListeners['touchmove'] ?? []).length === 1);
const creep = documentTouch('touchmove', { identifier: 7, clientX: 123, clientY: 397 });
assert('a small finger wiggle below the slop neither lifts nor prevents panning',
    !creep.prevented && !system.touchDrag.lifted);
const lift = documentTouch('touchmove', { identifier: 7, clientX: 122, clientY: 330 });
assert('moving up lifts the card into a drag that suppresses touch panning',
    lift.prevented && system.touchDrag.lifted && handA.classList.contains('dragging') &&
    system.draggedCard === handA && zoneHighlighted());
const liftedCarrier = cloneInBody();
const liftedClone = liftedCarrier.querySelector('.cardContainer');
assert('the lifted card rides a playingCards carrier so the clone keeps the card styling',
    Boolean(liftedCarrier) && liftedCarrier.classList.contains('playingCards') &&
    Boolean(liftedClone));
assert('the lifted card shows a clone that follows the finger without the dimmed dragging state',
    liftedClone.classList.contains('cardContainer') &&
    !liftedClone.classList.contains('dragging'));
documentTouch('touchmove', { identifier: 7, clientX: 300, clientY: 200 });
pointElement = zoneFor(2);
const overLane = documentTouch('touchmove', { identifier: 7, clientX: 305, clientY: 205 });
assert('moving over a lane lights up that lane drop zone only',
    overLane.prevented && zoneFor(2).classList.contains('drop-zone-active') &&
    !zoneFor(1).classList.contains('drop-zone-active') &&
    cloneInBody().style.left === '185px');
const stageEnd = documentTouch('touchend', { identifier: 7, clientX: 305, clientY: 205 });
assert('releasing over a lane stages the play with the existing ghost and hologram state',
    stageEnd.prevented && handA.classList.contains('ghost') &&
    handA.getAttribute('draggable') === 'false' && handA.dataset.stagedLane === '2');
const stagedHologram = stagedHologramFor(301);
assert('the staged hologram lands face down in the target lane',
    Boolean(stagedHologram) && holoRows[1].children.includes(stagedHologram) &&
    stagedHologram.querySelector('.cardContainer').classList.contains('faceDown'));
assert('the staged play keeps the card-id keyed cookie shape',
    cookieWrites.length === 1 && cookieWrites[0].startsWith('301=') &&
    cookieWrites[0].endsWith(';path=/MMM/game/1/board/1/'));
const stagedPair = cookieWrites[0].split(';')[0];
const stagedPayload = JSON.parse(decodeURIComponent(stagedPair.split('=').slice(1).join('=')));
assert('the staged payload preserves lane, source and flip fields',
    stagedPayload.laneValue === '2' && stagedPayload.sourceLane === '0' &&
    stagedPayload.sourceOrdinal === '1' && stagedPayload.flipFaceUp === false);
assert('a finished drag clears every gesture trace',
    system.touchDrag === null && system.draggedCard === null &&
    !handA.classList.contains('dragging') && !cloneInBody() && !zoneHighlighted() &&
    !zoneFor(2).classList.contains('drop-zone-active') &&
    (documentListeners['touchmove'] ?? []).length === 0);
assert('staging consumed one play allowance',
    system.staged.plays === 1 && system.remainingAllowances().plays === 1);

nowMs += 1000;
pointElement = handList;
cardTouchStart(handB, { identifier: 8, clientX: 60, clientY: 380 });
documentTouch('touchmove', { identifier: 8, clientX: 62, clientY: 300 });
pointElement = handB;
const returnEnd = documentTouch('touchend', { identifier: 8, clientX: 61, clientY: 305 });
assert('dropping back on the hand zone suppresses the ghost click and stages nothing',
    returnEnd.prevented && cookieWrites.length === 1 && !handB.classList.contains('ghost'));
assert('dropping back on the hand follows the existing hand card selection interaction',
    system.keyboardSelection.selectedCard === handB &&
    system.keyboardSelection.mouseSelecting === true &&
    fakeDocument.getElementById('mousePreviewCursor') !== null &&
    (documentListeners['touchmove'] ?? []).length === 0);

nowMs += 1000;
system.turnAllowances.played = 2;
cardTouchStart(handC, { identifier: 9, clientX: 40, clientY: 380 });
documentTouch('touchmove', { identifier: 9, clientX: 40, clientY: 300 });
documentTouch('touchend', { identifier: 9, clientX: 40, clientY: 300 });
assert('an exhausted play allowance never starts a touch drag nor stages a play',
    system.touchDrag === null && (documentListeners['touchmove'] ?? []).length === 0 &&
    cookieWrites.length === 1 && !handC.classList.contains('ghost'));

nowMs += 1000;
system.turnAllowances.played = 0;
cardTouchStart(handC, { identifier: 10, clientX: 40, clientY: 380 });
documentTouch('touchmove', { identifier: 10, clientX: 42, clientY: 300 });
const turnPhaseEl = new FakeElement('div');
turnPhaseEl.setAttribute('id', 'turnPhase');
turnPhaseEl.setAttribute('data-phase', 'enemy');
turnPhaseEl.dataset.phase = 'enemy';
body.appendChild(turnPhaseEl);
pointElement = zoneFor(4);
const enemyEnd = documentTouch('touchend', { identifier: 10, clientX: 350, clientY: 150 });
assert('a lane drop during the enemy phase stages nothing and clears the gesture',
    enemyEnd.prevented && cookieWrites.length === 1 &&
    !handC.classList.contains('ghost') && !handC.classList.contains('dragging') &&
    system.touchDrag === null && !cloneInBody());
turnPhaseEl.remove();

nowMs += 1000;
cardTouchStart(handC, { identifier: 11, clientX: 40, clientY: 380 });
documentTouch('touchmove', { identifier: 11, clientX: 42, clientY: 300 });
documentTouch('touchcancel', { identifier: 11, clientX: 44, clientY: 290 });
assert('a cancelled gesture cleans up styling and listeners without staging',
    system.touchDrag === null && !handC.classList.contains('dragging') &&
    !cloneInBody() && !zoneHighlighted() &&
    (documentListeners['touchmove'] ?? []).length === 0 &&
    cookieWrites.length === 1);

nowMs += 1000;
cardTouchStart(handC, { identifier: 12, clientX: 40, clientY: 380 });
const swipe = documentTouch('touchmove', { identifier: 12, clientX: 140, clientY: 379 });
documentTouch('touchend', { identifier: 12, clientX: 150, clientY: 379 });
assert('a sideways swipe releases the card so the hand keeps its native scrolling',
    !swipe.prevented && system.touchDrag === null &&
    !handC.classList.contains('dragging') &&
    (documentListeners['touchmove'] ?? []).length === 0 &&
    cookieWrites.length === 1);

nowMs += 1000;
cardTouchStart(handC, { identifier: 13, clientX: 40, clientY: 380 });
const tapEnd = documentTouch('touchend', { identifier: 13, clientX: 40, clientY: 380 });
assert('a plain tap keeps the default click path so the existing selection flow still runs',
    !tapEnd.prevented && system.touchDrag === null);
const clickEvent = {
    button: 0,
    target: handC,
    clientX: 40,
    clientY: 380,
    preventDefault() {},
};
(documentListeners['click'] ?? []).forEach((handler) => handler(clickEvent));
assert('the tap-then-click interaction selects the hand card exactly as on desktop',
    system.keyboardSelection.selectedCard === handC &&
    system.keyboardSelection.mouseSelecting === true);

nowMs += 1000;
cardTouchStart(handC, { identifier: 14, clientX: 40, clientY: 380 });
documentTouch('touchmove', { identifier: 14, clientX: 42, clientY: 300 });
(windowListeners['pagehide'] ?? []).forEach((handler) => handler());
assert('hiding the page mid-drag clears the gesture completely',
    system.touchDrag === null && !handC.classList.contains('dragging') &&
    !cloneInBody() && !zoneHighlighted() && !zoneFor(4).classList.contains('drop-zone-active') &&
    (documentListeners['touchmove'] ?? []).length === 0 &&
    cookieWrites.length === 1);

console.log('touch drag staging ok');
""".replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping touch drag staging DOM test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping touch drag staging DOM test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'touch drag staging harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('touch drag staging ok', completed.stdout)

    def test_turn_affordances_block_hand_cards_out_of_tab_order_and_restore_idempotently(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]
        self.assertIn(
            '    _isPlayableKeyboardCard_Legacy(card) {',
            control_class,
        )

        parent_class = drag_js[control_class_end:]
        self.assertIn(
            '    _isPlayableKeyboardCard(card) {',
            parent_class,
        )
        parent_wrapper_index = parent_class.index(
            '    _isPlayableKeyboardCard(card) {',
        )
        wrapper_close_index = parent_class.index('}', parent_wrapper_index)
        wrapper_block = parent_class[parent_wrapper_index:wrapper_close_index + 1]
        self.assertIn(
            'this._keyboardSelectionControl._isPlayableKeyboardCard_Legacy(card)',
            wrapper_block,
        )

        affordances_code = drag_js[
            drag_js.index('    applyTurnAffordances() {'):
            drag_js.index('    createDropZones() {')
        ]

        blocked_branch_start = affordances_code.index('if (remaining.plays <= 0) {')
        restore_branch_start = affordances_code.index('} else {', blocked_branch_start)
        restore_branch_end = affordances_code.index(
            'if (remaining.flips <= 0)', restore_branch_start
        )
        blocked_branch = affordances_code[blocked_branch_start:restore_branch_start]
        self.assertIn("card.classList.add('blocked');", blocked_branch)
        self.assertIn("card.setAttribute('draggable', 'false');", blocked_branch)
        self.assertIn("card.removeAttribute('tabindex');", blocked_branch)
        self.assertIn("!card.classList.contains('ghost')", blocked_branch)

        restore_branch = affordances_code[restore_branch_start:restore_branch_end]
        self.assertIn("!card.hasAttribute('tabindex')", restore_branch)
        self.assertIn("card.setAttribute('tabindex', '0');", restore_branch)
        self.assertIn('this._isOrderableKeyboardCard(card)', restore_branch)
        self.assertNotIn('this._isPlayableKeyboardCard(card)', restore_branch)

        deck_branch_start = affordances_code.index('if (remaining.draws <= 0)', restore_branch_end)
        flips_branch = affordances_code[
            affordances_code.index('if (remaining.flips <= 0)'):deck_branch_start
        ]
        self.assertIn('.playerBoard .cardContainer.faceDown:not(.blocked), ', flips_branch)
        self.assertIn(".hologram .cardContainer.faceDown:not(.blocked)", flips_branch)
        self.assertIn("card.classList.add('blocked');", flips_branch)
        self.assertIn('card.title = this.tooltips.flip;', flips_branch)
        self.assertNotIn('tabindex', flips_branch)

        deck_branch = affordances_code[deck_branch_start:]
        self.assertIn("querySelector('button.draw')", deck_branch)
        self.assertIn("drawBtn.setAttribute('tabindex', '-1')", deck_branch)

    def test_card_hover_manager_contract_covers_css_and_script_wiring(self):
        """Cards react to hover ONLY via the JS-managed .card-hover class."""
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.css')) as css_file:
            drag_css = css_file.read()
        with open(os.path.join(static_dir, 'hoverCooldown.js')) as js_file:
            hover_js = js_file.read()

        self.assertNotIn(':hover', cards_css)
        self.assertNotIn(':hover', drag_css)
        self.assertNotIn(':hover', hover_js)
        self.assertNotIn('hover-managed', cards_css)
        self.assertNotIn('hover-managed', drag_css)
        self.assertNotIn('hover-managed', hover_js)

        target_selector_block = hover_js[
            hover_js.index('const CARD_HOVER_TARGET_SELECTOR'):
            hover_js.index("].join(', ');")
        ]
        self.assertIn('.playerScreen .deckHand .hand li.cardContainer', target_selector_block)
        self.assertIn('.playerBoard ul.cardRow[title="cards"] li.cardContainer', target_selector_block)
        self.assertNotIn('ul.cardRow[title="trustedCards"]', hover_js)
        self.assertIn('.playerBoard ul.hologramRow .hologram', target_selector_block)
        self.assertIn('.enemyBoard li.cardContainer', target_selector_block)
        self.assertIn(
            '.playerBoard .deck-stack .active-deck:not(.blocked) '
            'button.draw:not(.blocked):not(:disabled)',
            target_selector_block,
        )
        self.assertNotIn('OWN_SIDE_EXCLUSION_SELECTOR', hover_js)

        # Keyboard focus / mouse press lifts are independent of the manager.
        self.assertIn(
            '.playingCards li.cardContainer:active, .playingCards li.cardContainer:focus-within,',
            cards_css,
        )

        lift_block = cards_css[
            cards_css.index('.playingCards li.cardContainer.card-hover,'):
            cards_css.index('.playingCards li.cardContainer:focus-within:active')
        ]
        self.assertIn('.playingCards li.cardContainer.card-hover:focus-within:active', lift_block)
        self.assertIn('--card-hover-lift: -30px;', lift_block)
        self.assertIn('margin-top: 0;', lift_block)
        self.assertNotIn('margin-top: -30px', lift_block)
        self.assertNotIn(
            '.playingCards li.cardContainer.card-hover {\n    margin-top: -30px;',
            cards_css,
        )

        self.assertIn(
            'transform: translate(var(--hand-tx), calc(var(--hand-ty) + var(--card-hover-lift, 0px))) rotate(var(--hand-rot));',
            cards_css,
        )
        self.assertIn(
            'transform: translate(var(--hand-tx), calc(calc(var(--hand-ty) - 20px) * 1.2 + var(--card-hover-lift, 0px))) rotate(var(--hand-rot));',
            cards_css,
        )
        self.assertIn(
            '.playingCards.rotateHand .hand-scroll .hand-fan > li.cardContainer:not(.duplicate) {\n'
            '    transition: transform 0.15s ease-out;\n}',
            cards_css,
        )
        self.assertIn(
            'transform: translateY(var(--card-hover-lift, 0px)) rotate(var(--card-rotation, 0deg));',
            cards_css,
        )
        self.assertIn(
            '.playingCards ul.cardRow li.cardContainer:not(.duplicate) {\n'
            '    transition: transform 0.15s ease-out, filter 0.3s ease, box-shadow 0.3s ease;\n}',
            cards_css,
        )

        card_row_hover_block = cards_css[
            cards_css.index('.playingCards ul.cardRow li.cardContainer:not(.blocked).card-hover {'):
            cards_css.index('.playingCards ul.cardRow[title="cards"] li.cardContainer:not(.blocked):focus-within {')
        ]
        self.assertIn(
            'transform: translateY(calc(var(--card-hover-lift, 0px) - 1.5em)) rotate(var(--card-rotation, 0deg));',
            card_row_hover_block,
        )
        self.assertIn(
            'transition: transform 0.15s ease-out, filter 0.15s ease-out;',
            card_row_hover_block,
        )
        card_row_focus_block = cards_css[
            cards_css.index('.playingCards ul.cardRow[title="cards"] li.cardContainer:not(.blocked):focus-within {'):
            cards_css.index('.playingCards ul.cardRow li.cardContainer.ghost.card-hover')
        ]
        self.assertIn(
            'transform: translateY(calc(var(--card-hover-lift, 0px) - 1.5em)) rotate(var(--card-rotation, 0deg));',
            card_row_focus_block,
        )

        ghost_mirror_block = cards_css[
            cards_css.index('.playingCards ul.cardRow li.cardContainer.ghost.card-hover'):
        ]
        ghost_mirror_block = ghost_mirror_block[:ghost_mirror_block.index('}')]
        self.assertIn('z-index: 999;', ghost_mirror_block)
        self.assertIn('transform: none;', ghost_mirror_block)
        self.assertIn('filter: none;', ghost_mirror_block)
        active_mirror_block = cards_css[
            cards_css.index('li.cardContainer:not(.blocked).card-hover:active'):
        ]
        active_mirror_block = active_mirror_block[:active_mirror_block.index('}')]
        self.assertIn('box-shadow: unset;', active_mirror_block)
        self.assertIn('filter: none;', active_mirror_block)

        hand_hover_block = cards_css[
            cards_css.index('.playerScreen .deckHand .hand li.cardContainer:not(.blocked).card-hover{'):
            cards_css.index('.playerScreen .deckHand .hand li.cardContainer:not(.blocked):focus-within{')
        ]
        self.assertIn('opacity: 1 !important;', hand_hover_block)
        self.assertIn('z-index: 1000;', hand_hover_block)
        self.assertIn(
            'li.cardContainer.blocked.card-hover {\n        opacity: 0.55 !important;\n        z-index: 999;',
            cards_css,
        )
        self.assertIn(
            '.playerScreen .deckHand .hand:has(li.cardContainer.card-hover)',
            cards_css,
        )
        self.assertIn(
            '.playerScreen .deckHand .hand li.cardContainer:not(.blocked).card-hover',
            cards_css,
        )
        self.assertIn(
            'li.cardContainer:not(.blocked).card-hover {\n        z-index: 1000;',
            cards_css,
        )
        self.assertIn(
            'li.cardContainer:not(.blocked):not(.faceDown).card-hover > .smallCard',
            cards_css,
        )

        blocked_mirror_block = cards_css[
            cards_css.index('.playerScreen li.cardContainer.blocked.card-hover'):
        ]
        blocked_mirror_block = blocked_mirror_block[:blocked_mirror_block.index('}')]
        self.assertIn('z-index: 999;', blocked_mirror_block)
        self.assertIn('box-shadow: none;', blocked_mirror_block)
        self.assertIn(
            '.playerBoard .deck-stack .active-deck:not(.blocked) '
            'button.draw:not(.blocked):not(:disabled).card-hover',
            cards_css,
        )

        # Bug 6: the focus-within background highlight must exclude .faceDown cards.
        self.assertIn(
            'li.cardContainer:not(.blocked):not(.faceDown):focus-within',
            cards_css,
        )
        self.assertNotIn(
            'li.cardContainer:not(.blocked):focus-within {\n        & .smallCard{',
            cards_css,
        )

        hologram_rest_block = drag_css[
            drag_css.index('ul.hologramRow .hologram {'):
            drag_css.index('ul.hologramRow .hologram.card-hover {')
        ]
        self.assertIn(
            'transition: transform 0.15s ease-out, opacity 0.15s ease-out;',
            hologram_rest_block,
        )
        hologram_hover_block = drag_css[
            drag_css.index('ul.hologramRow .hologram.card-hover {'):
            drag_css.index('ul.hologramRow .hologram:focus-within {')
        ]
        self.assertIn(
            'transform: translateY(-1.5em) rotate(var(--card-rotation, 0deg));',
            hologram_hover_block,
        )
        self.assertIn(
            'transition: transform 0.15s ease-out, opacity 0.15s ease-out;',
            hologram_hover_block,
        )
        self.assertIn(
            'ul.hand li.cardContainer:not(.blocked).card-hover > .card.smallCard',
            drag_css,
        )


        self.assertIn('class CardHoverManager', hover_js)
        self.assertIn('HOVER_REMOVE_COOLDOWN_MS = 500', hover_js)
        self.assertNotIn('HOVER_REMOVE_DELAY_MS', hover_js)
        self.assertIn("addEventListener('mousemove'", hover_js)
        self.assertIn('{ passive: true }', hover_js)
        self.assertIn("addEventListener('mouseleave', this.onMouseLeave)", hover_js)
        self.assertNotIn('preventDefault', hover_js)
        self.assertNotIn('stopPropagation', hover_js)
        self.assertIn('window.cardHoverManager = new CardHoverManager(screen);', hover_js)

        self.assertNotIn('hoverFootprint', hover_js)
        self.assertNotIn('captureFootprint', hover_js)
        self.assertNotIn('isInsideHoverFootprint', hover_js)
        self.assertNotIn('footprint', hover_js)
        self.assertNotIn('footprint', hover_js.lower())
        self.assertNotIn('getBoundingClientRect', hover_js)
        self.assertNotIn('pageX', hover_js)
        self.assertNotIn('pageY', hover_js)

        self.assertNotIn('matchMedia', hover_js)
        self.assertNotIn('prefers-reduced-motion', cards_css)
        self.assertNotIn('prefers-reduced-motion', hover_js)
        self.assertNotIn('transition: none', cards_css)
        self.assertEqual(drag_css.count('@media (prefers-reduced-motion: reduce)'), 1)
        drag_motion_block = drag_css[
            drag_css.index('@media (prefers-reduced-motion: reduce)'):
            drag_css.index('ul.hologramRow {')
        ]
        self.assertIn('.shortcut-hold-loading', drag_motion_block)
        self.assertNotIn('hologram', drag_motion_block)
        self.assertNotIn('card-hover', drag_motion_block)
        self.assertNotIn('morphCard', drag_motion_block)

        # The hover manager is intentionally minimal: a single mousemove-driven
        # .card-hover toggle with a 500 ms cooldown. Earlier complexity
        # (episodes, swapHover, removeHoverNow, cancelAnimationFrame) was
        # reverted; the contract below only covers what the simplified file
        # actually exports.
        self.assertNotIn('HOVER_SWITCH_COOLDOWN_MS', hover_js)
        self.assertNotIn('schedulePendingSwitch', hover_js)
        self.assertNotIn('pendingTarget', hover_js)
        self.assertNotIn('lastSwitchAt', hover_js)
        self.assertNotIn('schedulePendingRemove', hover_js)
        self.assertNotIn('cancelPendingRemove', hover_js)
        self.assertNotIn('this.removeTimer', hover_js)
        self.assertNotIn('this.episodes', hover_js)
        self.assertNotIn('consumePendingEvent', hover_js)
        self.assertNotIn('resolveHoverTarget', hover_js)
        self.assertNotIn('swapHover', hover_js)
        self.assertNotIn('removeHoverNow', hover_js)
        self.assertNotIn('cancelScheduledRemove', hover_js)
        self.assertNotIn('frameHandle', hover_js)
        self.assertNotIn('pendingEvent', hover_js)
        self.assertNotIn('cancelAnimationFrame', hover_js)

        apply_block = hover_js[
            hover_js.index('applyHover(card) {'):
            hover_js.index('releaseHover() {')
        ]
        self.assertIn('this.hoveredCard = card;', apply_block)
        self.assertIn('card.classList.add(HOVER_CLASS);', apply_block)
        self.assertIn('this.startedAt = Date.now();', apply_block)

        release_block = hover_js[
            hover_js.index('releaseHover() {'):
            hover_js.index('clearAllHover() {')
        ]
        self.assertIn(
            'this.startedAt + HOVER_REMOVE_COOLDOWN_MS - Date.now()',
            release_block,
        )
        self.assertIn('if (remainingMs <= 0)', release_block)
        self.assertIn('window.setTimeout(() => this.clearAllHover(), remainingMs);', release_block)

        leave_block = hover_js[
            hover_js.index('handleMouseLeave() {'):
            hover_js.index('clearAllHover() {')
        ]
        self.assertIn('this.releaseHover();', leave_block)

        teardown_block = hover_js[
            hover_js.index('clearAllHover() {'):
            hover_js.index("document.addEventListener('DOMContentLoaded'")
        ]
        self.assertIn('this.hoveredCard = null;', teardown_block)
        self.assertIn('HOVER_CLASS', teardown_block)

        # the board page loads the new module next to the other scripts
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))
        self.assertContains(
            response,
            '<script type="module" src="/static/hoverCooldown.js"></script>',
        )

    def test_end_turn_hold_contract_reuses_guard_timer_and_indicator(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.css')) as css_file:
            drag_css = css_file.read()

        self.assertIn('class ShortcutHoldAction', drag_js)
        self.assertIn('this.duration = duration', drag_js)
        self.assertIn('this.completed = false', drag_js)
        self.assertIn('this.submitted = false', drag_js)
        self.assertIn('this.timer = null', drag_js)
        self.assertIn("event.key.toLowerCase() === 'e'", drag_js)
        self.assertIn("document.addEventListener('keyup'", drag_js)
        self.assertIn("window.addEventListener('blur'", drag_js)
        self.assertIn('document.hidden', drag_js)
        self.assertIn("#turnPhase[data-phase=\"enemy\"]", drag_js)
        self.assertIn('_isTextControlTarget', drag_js)
        self.assertIn("document.querySelector('.loading, [data-loading=\"true\"]')", drag_js)
        self.assertIn('cancelShortcutHolds', drag_js)
        self.assertIn('event.repeat', drag_js)
        self.assertIn('button.click()', drag_js)
        self.assertIn('requestSubmit', drag_js)
        self.assertIn('.shortcut-hold-loading', drag_css)
        self.assertIn('@keyframes shortcutHoldProgress', drag_css)
        self.assertIn('@media (prefers-reduced-motion: reduce)', drag_css)

    def test_end_turn_hold_keeps_existing_form_hook(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))

        self.assertContains(response, 'class="end-turn"')
        self.assertContains(response, 'name="action" value="end_turn"')
        self.assertContains(response, 'class="cardActionForm"')

    def test_focused_end_turn_button_keyboard_activation_routes_through_the_shortcut_hold(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.css')) as css_file:
            drag_css = css_file.read()

        keydown_code = drag_js[
            drag_js.index('    onKeyboardKeyDown(event)'):
            drag_js.index('    selectOrderedCard(')
        ]
        enter_start = keydown_code.index(
            "if (!activeSelection && (key === 'Enter' || key === ' ')) {"
        )
        end_turn_route_index = keydown_code.index(
            'this._isKeyboardEndTurnTarget(event)', enter_start
        )
        hand_route_index = keydown_code.index(
            'this._keyboardSelectableHandCard(event)', enter_start
        )
        self.assertLess(end_turn_route_index, hand_route_index)
        self.assertIn(
            'this.onEndTurnKeyDown(event)',
            keydown_code[end_turn_route_index:hand_route_index],
        )

        helper_code = drag_js[
            drag_js.index('    _isKeyboardEndTurnTarget(event) {'):
            drag_js.index('    _isPlayerActionPhase() {')
        ]
        self.assertIn("navigator.regionFor(candidate) === 'end-turn'", helper_code)
        self.assertIn('document.activeElement', helper_code)

        hold_code = drag_js[
            drag_js.index('    onEndTurnKeyDown(event)'):
            drag_js.index('    onKeyboardKeyUp(event)')
        ]
        self.assertIn("event.key === 'Enter' || event.key === ' '", hold_code)
        self.assertIn('if (activationEvent) {', hold_code)
        self.assertIn('event.preventDefault();', hold_code)
        self.assertIn('endTurnHold.start(control.target', hold_code)
        self.assertIn('_submitHeldEndTurn()', hold_code)
        self.assertNotIn('loadingAnimations', drag_js)
        self.assertNotIn('fetch(', drag_js)

        self.assertIn('.shortcut-hold-loading', drag_css)

    def test_focused_end_turn_button_activation_keeps_native_submit_button(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))

        self.assertContains(response, '<button type="submit" class="end-turn" title="End turn"')
        self.assertContains(response, 'autofocus')

    def test_enter_and_space_on_focused_end_turn_button_start_the_loading_hold_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = r"""
const matchPart = (el, part) => {
    if (!el || !el.tagName) return false;
    const tagMatch = part.match(/^[a-zA-Z][\w-]*/);
    if (tagMatch && el.tagName.toLowerCase() !== tagMatch[0].toLowerCase()) return false;
    const idMatch = part.match(/#([\w-]+)/);
    if (idMatch && (el.id || '') !== idMatch[1]) return false;
    for (const cls of part.match(/\.([\w-]+)/g) || []) {
        if (!el.classList || !el.classList.contains(cls.slice(1))) return false;
    }
    const attrRe = /\[([\w-]+)(?:="([^"]*)")?\]/g;
    let match;
    while ((match = attrRe.exec(part))) {
        const value = el.getAttribute ? el.getAttribute(match[1]) : null;
        if (match[2] === undefined) {
            if (value === null) return false;
        } else if (String(value) !== match[2]) return false;
    }
    const notRe = /:not\(\.([\w-]+)\)/g;
    while ((match = notRe.exec(part))) {
        if (el.classList && el.classList.contains(match[1])) return false;
    }
    if (part.replace(/:not\([^)]*\)/g, '').includes(':')) return false;
    return true;
};

const matchChainFrom = (el, tokens) => {
    const last = tokens[tokens.length - 1];
    if (!matchPart(el, last.part)) return false;
    if (tokens.length === 1) return true;
    const rest = tokens.slice(0, -1);
    if (last.combinator === '>') {
        return Boolean(el.parentNode) && matchChainFrom(el.parentNode, rest);
    }
    let node = el.parentNode;
    while (node) {
        if (matchChainFrom(node, rest)) return true;
        node = node.parentNode;
    }
    return false;
};

const tokenizeChain = (chain) => {
    const tokens = [];
    const re = /(\s*>\s*|\s+)?([^>\s]+)/g;
    let match;
    while ((match = re.exec(chain)) !== null) {
        let combinator = null;
        if (match[1] && match[1].includes('>')) combinator = '>';
        else if (match[1] && match[1].trim() !== '') combinator = ' ';
        tokens.push({ part: match[2], combinator });
    }
    if (tokens.length > 0 && tokens[0].part === ':scope') {
        const [head, ...rest] = tokens;
        rest[0].combinator = '>';
        return rest;
    }
    return tokens;
};

const descendantsInOrder = (root) => {
    const result = [];
    const stack = [...root.children];
    while (stack.length) {
        const node = stack.shift();
        result.push(node);
        stack.unshift(...node.children);
    }
    return result;
};

class FakeElement {
    constructor(tag, className = '') {
        this.tagName = String(tag).toUpperCase();
        this.classes = new Set(String(className).split(/\s+/).filter(Boolean));
        this.attributes = new Map();
        this.dataset = {};
        this.children = [];
        this.parentNode = null;
        this.removed = false;
        this.id = '';
        this.title = '';
        this.eventHandlers = {};
        this.classList = {
            add: (...names) => names.forEach((name) => this.classes.add(name)),
            remove: (...names) => names.forEach((name) => this.classes.delete(name)),
            contains: (name) => this.classes.has(name),
            toggle: (name) => {
                if (this.classes.has(name)) this.classes.delete(name);
                else this.classes.add(name);
            },
        };
        this.style = {
            setProperty: () => {},
            getPropertyValue: () => '',
            getPropertyPriority: () => '',
            removeProperty: () => {},
        };
        this.getBoundingClientRect = () => ({ left: 0, top: 0, width: 10, height: 10 });
    }

    matches(selector) {
        return String(selector).split(',').some((part) => part.trim() &&
            matchChainFrom(this, tokenizeChain(part.trim())));
    }

    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches(selector)) return node;
            node = node.parentNode;
        }
        return null;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] ?? null;
    }

    querySelectorAll(selector) {
        const alternatives = String(selector).split(',').map(
            (part) => tokenizeChain(part.trim()),
        );
        return descendantsInOrder(this).filter((candidate) =>
            alternatives.some((tokens) => matchChainFrom(candidate, tokens)));
    }

    appendChild(child) {
        this.children.push(child);
        child.parentNode = this;
        return child;
    }

    insertBefore(newNode, reference) {
        let index = reference ? this.children.indexOf(reference) : this.children.length;
        if (index === -1) index = this.children.length;
        this.children.splice(index, 0, newNode);
        newNode.parentNode = this;
        return newNode;
    }

    get firstChild() {
        return this.children[0] ?? null;
    }

    contains(other) {
        let node = other;
        while (node) {
            if (node === this) return true;
            node = node.parentNode;
        }
        return false;
    }

    remove() {
        if (this.parentNode) {
            const index = this.parentNode.children.indexOf(this);
            if (index !== -1) this.parentNode.children.splice(index, 1);
        }
        this.parentNode = null;
        this.removed = true;
    }

    cloneNode(deep) {
        const clone = new FakeElement(this.tagName, [...this.classes].join(' '));
        this.attributes.forEach((value, name) => clone.setAttribute(name, value));
        if (this.id) clone.id = this.id;
        Object.assign(clone.dataset, this.dataset);
        if (deep) this.children.forEach((child) => clone.appendChild(child.cloneNode(true)));
        return clone;
    }

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
        if (name === 'id') this.id = String(value);
        if (/^[a-zA-Z][\w-]*$/.test(name)) this[name] = String(value);
        if (name === 'hidden') this.hidden = true;
    }

    getAttribute(name) {
        return this.attributes.has(name) ? this.attributes.get(name) : null;
    }

    removeAttribute(name) {
        this.attributes.delete(name);
    }

    hasAttribute(name) {
        return this.attributes.has(name);
    }

    addEventListener(name, handler) {
        (this.eventHandlers[name] ??= []).push(handler);
    }

    removeEventListener(name, handler) {
        this.eventHandlers[name] = (this.eventHandlers[name] ?? []).filter((h) => h !== handler);
    }
}

const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const matTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(matTable);
const playerBoard = new FakeElement('div', 'playerBoard');
matTable.appendChild(playerBoard);

const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const holoRows = [];
 ['', '', '', ''].forEach((unused, laneIndex) => {
    const lane = new FakeElement('li', 'lane');
    lane.classList.add(['Intelligence', 'Speed', 'Visciousness', 'Resolve'][laneIndex]);
    lanesEl.appendChild(lane);
    const holoRow = new FakeElement('ul', 'hologramRow');
    lane.appendChild(holoRow);
    holoRows.push(holoRow);
});

const deckHand = new FakeElement('div', 'deckHand handContainer');
matTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);

const makeHandCard = (cardId, cardLane, sourceOrdinal) => {
    const card = new FakeElement('li', 'cardContainer');
    card.setAttribute('tabindex', '0');
    card.setAttribute('draggable', 'true');
    card.dataset.cardLane = String(cardLane);
    card.dataset.sourceLane = '0';
    card.dataset.sourceOrdinal = String(sourceOrdinal);
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', 'card_id');
    input.setAttribute('value', String(cardId));
    card.appendChild(input);
    handList.appendChild(card);
    return card;
};
const handA = makeHandCard(301, 1, 1);
const handB = makeHandCard(302, 3, 2);
const handC = makeHandCard(303, 2, 3);
const handCards = [handA, handB, handC];

const endTurnForm = new FakeElement('form', 'cardActionForm');
playerScreen.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);
const focusedHandCardInput = new FakeElement('input');
focusedHandCardInput.setAttribute('type', 'hidden');
focusedHandCardInput.setAttribute('name', 'focused_hand_card');
focusedHandCardInput.setAttribute('value', '1');
endTurnForm.appendChild(focusedHandCardInput);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) {
        return body.querySelector(selector);
    },
    querySelectorAll(selector) {
        return body.querySelectorAll(selector);
    },
    getElementById(id) {
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) {
        (documentListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};
const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
    drawBlockedTitle: 'draw blocked',
    playBlockedTitle: 'play blocked',
    flipBlockedTitle: 'flip blocked',
};
fakeDocument.getElementById = (id) => {
    if (id === 'turnLimits') return turnLimits;
    for (const el of descendantsInOrder(body)) {
        if (el.id === id) return el;
    }
    return null;
};

const cookieWrites = [];
Object.defineProperty(fakeDocument, 'cookie', {
    set(value) { cookieWrites.push(value); },
    get() { return cookieWrites.join('; '); },
});

for (const el of [body, playerScreen, playerBoard, endTurnForm, endTurnButton, ...handCards, ...holoRows]) {
    el.focus = () => { fakeDocument.activeElement = el; };
    el.blur = () => { if (fakeDocument.activeElement === el) fakeDocument.activeElement = body; };
}

global.document = fakeDocument;
const holdTimers = [];
let nextTimerId = 1;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/MMM/game/1/board/1/action/' },
    setTimeout(callback) {
        const id = nextTimerId++;
        holdTimers.push({ id, callback });
        return id;
    },
    clearTimeout(id) {
        const index = holdTimers.findIndex((task) => task.id === id);
        if (index !== -1) holdTimers.splice(index, 1);
    },
};
global.CSS = { escape: (value) => String(value) };
global.Element = function Element() {};
global.MutationObserver = function (handler) {
    this.observe = () => {};
    this.disconnect = () => {};
};

const endTurnSubmits = { count: 0 };
endTurnButton.click = () => { endTurnSubmits.count += 1; };

const dragCode = __DRAG_JS__;
eval(dragCode);

(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const keyupHandlers = documentListeners['keyup'] ?? [];

const pressKey = (key, options = {}) => {
    let prevented = false;
    const event = {
        key,
        repeat: options.repeat ?? false,
        target: options.target ?? fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const releaseKey = (key) => {
    let prevented = false;
    const event = {
        key,
        repeat: false,
        target: fakeDocument.activeElement,
        preventDefault() { prevented = true; },
    };
    keyupHandlers.forEach((entry) => entry(event));
    return prevented;
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};

const state = () => system.keyboardSelection;
const activeIs = (element) => fakeDocument.activeElement === element;
const holdLoading = () => endTurnButton.classList.contains('shortcut-hold-loading');
const submits = () => endTurnSubmits.count;
const queuedTimers = () => holdTimers.length;
const flushTimers = () => {
    for (const task of holdTimers.splice(0)) task.callback();
};

fakeDocument.activeElement = handA;

assert('Enter on the focused hand card keeps selecting the card',
    pressKey('Enter') && state().selectedCard === handA && activeIs(handA) &&
    submits() === 0 && !holdLoading());
pressKey('0');
assert('cancel clears that selection without touching the end turn hold',
    state().selectedCard === null && submits() === 0 && !holdLoading());

fakeDocument.activeElement = endTurnButton;

assert('Enter on the focused end turn button starts the loading hold instead of submitting',
    pressKey('Enter') && holdLoading() && endTurnButton.getAttribute('aria-busy') === 'true' &&
    submits() === 0);
assert('the held end turn keeps exactly one scheduled submit',
    queuedTimers() === 1);

assert('repeated Enter while the hold runs stays suppressed and schedules nothing more',
    pressKey('Enter', { repeat: true }) && submits() === 0 && queuedTimers() === 1);

flushTimers();
assert('the loading hold ends by submitting the end turn form exactly once',
    submits() === 1 && !holdLoading() && endTurnButton.getAttribute('aria-busy') === null);

assert('Enter after that submit is suppressed so the request stays single',
    pressKey('Enter') && submits() === 1 && queuedTimers() === 0);

assert('releasing the end turn key resets the protected hold',
    releaseKey('e') && holdLoading() === false && queuedTimers() === 0);

assert('Space on the focused end turn button starts the same loading hold',
    pressKey(' ') && holdLoading() && endTurnButton.getAttribute('aria-busy') === 'true' &&
    submits() === 1);
flushTimers();
assert('the Space hold also submits exactly once',
    submits() === 2 && !holdLoading());

assert('releasing the end turn key resets the protected hold', releaseKey('e'));

assert('the E end turn shortcut still starts its loading hold',
    pressKey('e') && holdLoading() && submits() === 2);
flushTimers();
assert('the E shortcut again submits exactly once',
    submits() === 3 && !holdLoading());
assert('releasing the end turn key resets the protected hold', releaseKey('e'));

const turnPhaseEl = new FakeElement('div');
turnPhaseEl.setAttribute('id', 'turnPhase');
turnPhaseEl.setAttribute('data-phase', 'enemy');
body.appendChild(turnPhaseEl);

assert('during running enemy animations Enter on the end turn button stays native',
    !pressKey('Enter') && !holdLoading() && submits() === 3);

console.log('focused end turn keyboard loading ok');
""".replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping focused end turn loading DOM test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping focused end turn loading DOM test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'focused end turn loading harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('focused end turn keyboard loading ok', completed.stdout)

    def test_space_draw_stages_and_restores_draw_button_focus_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()

        harness = FAKE_ELEMENT_NAVIGATION_CORE + r"""
const documentListeners = {};
const storage = new Map();
const rafCallbacks = [];
const holdTimers = [];

const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const matTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(matTable);
const playerBoard = new FakeElement('div', 'playerBoard');
matTable.appendChild(playerBoard);

const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const lane = new FakeElement('li', 'lane Intelligence');
lanesEl.appendChild(lane);
lane.appendChild(new FakeElement('ul', 'hologramRow'));

const deckHand = new FakeElement('div', 'deckHand handContainer');
matTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
deckHand.scrollIntoView = () => {};

const endTurnForm = new FakeElement('form', 'cardActionForm');
playerScreen.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);
endTurnButton.focus = () => { fakeDocument.activeElement = endTurnButton; };

const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
    drawBlockedTitle: 'draw blocked',
    playBlockedTitle: 'play blocked',
    flipBlockedTitle: 'flip blocked',
};

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) { return body.querySelector(selector); },
    querySelectorAll(selector) { return body.querySelectorAll(selector); },
    getElementsByClassName(className) {
        const names = String(className).split(/\s+/).filter(Boolean);
        return descendantsInOrder(body).filter((el) =>
            names.every((name) => el.classList && el.classList.contains(name)));
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) { (documentListeners[event] ??= []).push(handler); },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    readyState: 'complete',
    body,
    activeElement: null,
};
fakeDocument.getElementById = (id) => {
    if (id === 'turnLimits') return turnLimits;
    for (const el of descendantsInOrder(body)) {
        if (el.id === id) return el;
    }
    return null;
};

const cookieWrites = [];
Object.defineProperty(fakeDocument, 'cookie', {
    set(value) { cookieWrites.push(value); },
    get() { return cookieWrites.join('; '); },
});

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    loadingAnimations: null,
    location: { pathname: '/MMM/game/1/board/2/' },
    setTimeout(callback) {
        const id = 1000 + holdTimers.length;
        holdTimers.push({ id, callback });
        return id;
    },
    clearTimeout(id) {
        const index = holdTimers.findIndex((task) => task.id === id);
        if (index !== -1) holdTimers.splice(index, 1);
    },
};
global.CSS = { escape: (value) => String(value) };
global.Element = function Element() {};
global.MutationObserver = function () {
    this.observe = () => {};
    this.disconnect = () => {};
};
global.sessionStorage = {
    getItem: (key) => (storage.has(key) ? storage.get(key) : null),
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => { storage.delete(key); },
};
global.requestAnimationFrame = (callback) => {
    rafCallbacks.push(callback);
    return rafCallbacks.length;
};

const drawFocusStored = () => (sessionStorage.getItem(drawFocusKey) ?? null);

const dragCode = __DRAG_JS__;
const loadingCode = __LOADING_JS__;
eval(dragCode);
eval(loadingCode);
(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');
if (!global.window.loadingAnimations) throw new Error('loadingAnimations not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const pressKey = (key, options = {}) => {
    let prevented = false;
    const event = {
        key,
        repeat: options.repeat ?? false,
        target: options.target ?? fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};
const focusIs = (element) => fakeDocument.activeElement === element;

const buildDeckArea = (variant) => {
    const deckStack = new FakeElement('div', 'deck-stack own-deck-stack');
    playerBoard.appendChild(deckStack);
    const deck = new FakeElement('ul', 'deck active-deck');
    deckStack.appendChild(deck);
    if (variant === 'empty') {
        deck.appendChild(new FakeElement('div', 'card back emptyDeck'));
        return null;
    }
    const form = new FakeElement('form', 'cardActionForm');
    deck.appendChild(form);
    const drawButton = new FakeElement('button', 'card back draw');
    form.appendChild(drawButton);
    drawButton.focus = () => { fakeDocument.activeElement = drawButton; };
    if (variant === 'blocked') {
        deck.classList.add('blocked');
        drawButton.classList.add('blocked');
        drawButton.setAttribute('disabled', 'disabled');
    }
    return drawButton;
};
const resetActiveFocus = () => { fakeDocument.activeElement = null; rafCallbacks.length = 0; };
const clearBoardAreas = () => {
    deckHand.children = deckHand.children.filter((child) => child === handScroll);
    playerBoard.children = playerBoard.children.filter((child) => child === lanesEl);
};
const flushTick = () => {
    for (const callback of rafCallbacks.splice(0)) callback();
};

const boardPath = '/MMM/game/1/board/2/';
const drawFocusKey = 'mmmDrawFocusReturn';

resetActiveFocus();
flushTick();
assert('a plain board without a staged draw leaves focus untouched', focusIs(null) && drawFocusStored() === null);

const drawButton = buildDeckArea('open');
fakeDocument.activeElement = drawButton;

assert('Space on the focused draw button stays a native submit (no hold, no prevention)',
    !pressKey(' ') && holdTimers.length === 0 &&
    !drawButton.classList.contains('shortcut-hold-loading') &&
    system.keyboardSelection.selectedCard === null);
assert('the Space draw stages the focus return on this board path',
    drawFocusStored() === boardPath);

assert('repeating the draw key press re-stages the same focus return without holding',
    !pressKey('Enter') && drawFocusStored() === boardPath && holdTimers.length === 0);

const instantiateLoading = () => {
    window.loadingAnimations = new window.loadingAnimations.constructor();
};

clearBoardAreas();
resetActiveFocus();
window.location.pathname = '/MMM/game/1/board/2/action/';
const flightCard = new FakeElement('li', 'cardContainer loading');
flightCard.setAttribute('data-source-lane', '-2');
flightCard.setAttribute('data-source-ordinal', '0');
const actionDeckButton = buildDeckArea('open');
deckHand.appendChild(flightCard);
instantiateLoading();

assert('the draw animation page keeps the staged focus return while flights run',
    drawFocusStored() === boardPath);
assert('the draw animation page does not grab the draw button focus yet',
    !focusIs(actionDeckButton) && fakeDocument.activeElement === null);

const sweepFlightDuplicates = () => {
    for (const element of [...document.body.children]) {
        if (element.classList && element.classList.contains('duplicate')) element.remove();
    }
};
sweepFlightDuplicates();

clearBoardAreas();
resetActiveFocus();
window.location.pathname = boardPath;
const refreshedDrawButton = buildDeckArea('open');
instantiateLoading();
flushTick();
assert('the plain board after a Space draw gives focus back to the draw button',
    focusIs(refreshedDrawButton));
assert('the restore consumed the staged focus return',
    drawFocusStored() === null);

clearBoardAreas();
resetActiveFocus();
const exhaustedDrawButton = buildDeckArea('blocked');
sessionStorage.setItem(drawFocusKey, boardPath);
instantiateLoading();
flushTick();
assert('a spent draw button consumes the pending return without throwing',
    !focusIs(exhaustedDrawButton) && drawFocusStored() === null);

clearBoardAreas();
resetActiveFocus();
buildDeckArea('empty');
sessionStorage.setItem(drawFocusKey, boardPath);
instantiateLoading();
assert('a depleted deck consumes the pending return safely',
    !focusIs(fakeDocument.body) && drawFocusStored() === null);

clearBoardAreas();
resetActiveFocus();
window.location.pathname = '/MMM/game/7/board/3/';
const otherGameDrawButton = buildDeckArea('open');
sessionStorage.setItem(drawFocusKey, boardPath);
instantiateLoading();
flushTick();
assert('a focus return staged elsewhere never leaks into another game',
    !focusIs(otherGameDrawButton) && drawFocusStored() === null);

clearBoardAreas();
resetActiveFocus();
window.location.pathname = boardPath;
const mouseDrawButton = buildDeckArea('open');
instantiateLoading();
flushTick();
assert('a mouse draw (no keydown) leaves the end turn autofocus in place',
    !focusIs(mouseDrawButton) && !focusIs(endTurnButton));

console.log('space draw focus round trip ok');
""".replace('__DRAG_JS__', repr(drag_js)).replace('__LOADING_JS__', repr(loading_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping space draw focus DOM test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping space draw focus DOM test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'space draw focus harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('space draw focus round trip ok', completed.stdout)

    def test_draw_hold_contract_reuses_active_draw_form_and_shared_hold_state(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.css')) as css_file:
            drag_css = css_file.read()

        self.assertIn('this.drawHold = new ShortcutHoldAction();', drag_js)
        self.assertIn("event.key.toLowerCase() === 'd'", drag_js)
        self.assertIn("document.querySelector('.playerBoard .deck-stack .active-deck')", drag_js)
        self.assertIn("deck.querySelector('button.draw')", drag_js)
        self.assertIn("deck.querySelector('.emptyDeck')", drag_js)
        self.assertIn('this.remainingAllowances().draws <= 0', drag_js)
        self.assertIn('this.drawHold.start([control.deck, control.button]', drag_js)
        self.assertIn('this.drawHold.release()', drag_js)
        self.assertIn('this.drawHold.cancel()', drag_js)
        self.assertIn('this._submitHeldDraw()', drag_js)
        self.assertIn('control.button.click()', drag_js)
        self.assertNotIn('fetch(', drag_js)
        self.assertNotIn('XMLHttpRequest', drag_js)
        self.assertIn('.shortcut-hold-loading', drag_css)

    def test_draw_hold_keeps_existing_draw_form_hook(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))

        self.assertContains(response, 'class="card back draw"')
        self.assertContains(response, 'name="action" value="draw"')
        self.assertContains(response, 'class="cardActionForm"')

    def test_hologram_row_precedes_card_row(self):
        """Each player lane has hologramRow before the first cardRow."""
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.get(board_url)
        content = response.content.decode()

        player_board = re.search(
            r'<li class="playerBoard[^>]*>.*?(?=<div class="deckHand)',
            content, re.DOTALL
        )
        self.assertIsNotNone(player_board, "Could not find playerBoard section in rendered HTML")
        pb_html = player_board.group(0)

        for lane_name in ('Intelligence', 'Speed', 'Visciousness', 'Resolve'):
            pattern = re.escape(f'<li class="lane {lane_name}">')
            holo_before_card = re.search(
                pattern + r'\s*<ul class="hologramRow"></ul>\s*<ul class="cardRow"',
                pb_html
            )
            self.assertIsNotNone(
                holo_before_card,
                f"Lane {lane_name} missing hologramRow before cardRow"
            )

    def test_lane_overflow_splits_rows_without_merging_back(self):
        """Overflow rows stay separate; only marker rows merge, never trustedCards."""
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'laneStacking.js')) as js_file:
            stacking_js = js_file.read()
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()
            
        self.assertIn("'overflow-row'", stacking_js)
        self.assertIn('MAX_CARDS_PER_ROW = 25', stacking_js)
        ensure_code = stacking_js[
            stacking_js.index('    ensureSingleRow('):stacking_js.index('    splitIntoRows(')
        ]
        self.assertIn('OVERFLOW_ROW_CLASS', ensure_code)
        split_code = stacking_js[
            stacking_js.index('    splitIntoRows('):stacking_js.index('document.addEventListener')
        ]
        self.assertNotIn('ensureSingleRow', split_code)
        self.assertIn('OVERFLOW_ROW_CLASS', split_code)
        # NEW (Bug 7): overflow rows are inserted BEFORE the source row, not after.
        self.assertIn('insertBefore(rows[i], sourceRow)', split_code)
        self.assertNotIn('sourceRow.nextElementSibling', split_code)
        # The overflow rows carry a --overflow-row-index so CSS can stack them.
        self.assertIn('--overflow-row-index', split_code)

        # NEW (Bug 7): CSS positions overflow rows absolutely with the index,
        # and the lane <p> indicator is absolutely positioned so it does not
        # shift when rows are added.
        self.assertIn(
            'ul.lanes li.lane > ul.cardRow.overflow-row',
            cards_css,
        )
        self.assertIn('--overflow-row-index', cards_css)
        lane_indicator_match = re.search(
            r'ul\.lanes li\.lane\s*>\s*p[^{]*\{[^}]*\}',
            cards_css,
        )
        self.assertIsNotNone(lane_indicator_match)
        self.assertIn('position: absolute', lane_indicator_match.group(0))

        find_code = loading_js[
            loading_js.index('function findCardRowForOrdinal('):
            loading_js.index('const HAND_FAN_SIZE')
        ]
        self.assertIn('[title="cards"]', find_code)
        self.assertNotIn('[title="trustedCards"]', find_code)
        
        self.assertIn('li.cardContainer:nth-child(20)', cards_css)
        self.assertIn('ul.cardRow + ul.cardRow.overflow-row', cards_css)

        cap_match = re.search(r'MAX_CARDS_PER_ROW = (\d+)', stacking_js)
        defined_offsets = re.findall(
            r'ul\.cardRow li\.cardContainer:nth-child\((\d+)\)', cards_css
        )
        self.assertIsNotNone(cap_match, "MAX_CARDS_PER_ROW missing from laneStacking.js")
        self.assertTrue(defined_offsets, "No cardContainer nth-child offsets in cards.css")
        self.assertLessEqual(
            int(cap_match.group(1)),
            max(int(offset) for offset in defined_offsets),
            "MAX_CARDS_PER_ROW exceeds highest nth-child offset in cards.css"
        )

    def test_lane_heights_stretch_equal_across_board(self):
        """All four lanes render at equal height: flex stretch, not per-lane content sizing."""
        import os
        import re

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()

        lanes_rule = re.search(r'^ul\.lanes\s*\{[^}]*\}', cards_css, re.MULTILINE)
        self.assertIsNotNone(lanes_rule, "ul.lanes rule missing from cards.css")
        lanes_body = lanes_rule.group(0)
        self.assertIn('display: flex', lanes_body)
        self.assertIn('flex-direction: row', lanes_body)
        self.assertIn('align-items: stretch', lanes_body)
        self.assertIsNone(
            re.search(r'(^|[^-\w])height\s*:', lanes_body),
            "ul.lanes must not declare a fixed/percentage height; lanes equalize via stretch "
            "and the playerBoard must grow with its content"
        )

        lane_rule = re.search(r'ul\.lanes li\.lane\s*\{[^}]*\}', cards_css)
        self.assertIsNotNone(lane_rule, "ul.lanes li.lane rule missing from cards.css")
        self.assertIsNone(
            re.search(r'(^|[^-\w])height\s*:', lane_rule.group(0)),
            "li.lane must not declare a fixed/percentage height; lanes equalize via stretch"
        )

        player_screen_ul_rule = re.search(
            r'\.playerScreen\s*>\s*ul\s*\{[^}]*\}', cards_css
        )
        self.assertIsNotNone(
            player_screen_ul_rule,
            ".playerScreen > ul rule missing from cards.css"
        )
        self.assertIsNone(
            re.search(r'(^|[^-\w])height\s*:', player_screen_ul_rule.group(0)),
            ".playerScreen > ul must not cap the playerBoard-wrapping basic-mat at a "
            "fixed height; the playerBoard must grow with its lanes"
        )

        player_board_rule = re.search(
            r'\.playerScreen\s+\.playerBoard\s*\{[^}]*\}', cards_css
        )
        self.assertIsNotNone(
            player_board_rule,
            ".playerScreen .playerBoard rule missing from cards.css"
        )
        self.assertIsNone(
            re.search(r'(^|[^-\w])height\s*:', player_board_rule.group(0)),
            ".playerScreen .playerBoard must not declare a fixed height; it must "
            "stretch with the column"
        )

        basic_mat_rule = re.search(
            r'li\.playerBoard\s*>\s*ul\.basic-mat\s*\{[^}]*\}', cards_css
        )
        self.assertIsNotNone(
            basic_mat_rule,
            "li.playerBoard > ul.basic-mat rule missing from cards.css"
        )
        self.assertIsNone(
            re.search(r'(^|[^-\w])height\s*:', basic_mat_rule.group(0)),
            "li.playerBoard > ul.basic-mat must not cap the playerBoard child at a "
            "fixed height; the column must grow with its lanes"
        )

    def test_player_board_grows_with_lanes_deckhand_pinned(self):
        """Player board grows vertically with long lanes; deckHand stays pinned at the bottom."""
        import os
        import re

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()

        player_screen_rule = re.search(
            r'div\.playerScreen\s*\{[^}]*\}', cards_css
        )
        self.assertIsNotNone(player_screen_rule, "div.playerScreen rule missing from cards.css")
        player_screen_body = player_screen_rule.group(0)
        self.assertIn(
            'display: flex', player_screen_body,
            "div.playerScreen must be a flex column so the playerBoard can push "
            "the enemy board up while the deckHand stays pinned"
        )
        self.assertIn(
            'flex-direction: column', player_screen_body,
            "div.playerScreen must lay out children vertically"
        )

        player_table_rule = re.search(
            r'\.playerScreen\s*>\s*ul:not\(\.enemyBoards\)\s*\{[^}]*\}', cards_css
        )
        self.assertIsNotNone(
            player_table_rule,
            ".playerScreen > ul:not(.enemyBoards) rule missing from cards.css"
        )
        self.assertIn(
            'position: fixed', player_table_rule.group(0),
            "the player table holding the playerBoard and the deckHand must stay "
            "anchored to the bottom of the screen so the deckHand stays pinned "
            "regardless of how tall the playerBoard above grows"
        )
        self.assertIn(
            'bottom: 0', player_table_rule.group(0),
            "the player table must pin itself to the screen bottom"
        )

        deck_hand_children_rule = re.search(
            r'\.playerScreen\s+\.deckHand\s*>\s*\.hand,\s*'
            r'\.playerScreen\s+\.deckHand\s*>\s*\.hand-scroll,\s*'
            r'\.playerScreen\s+\.deckHand\s*>\s*\.hand-fan\s*\{[^}]*\}',
            cards_css,
        )
        self.assertIsNotNone(
            deck_hand_children_rule,
            ".playerScreen .deckHand child-row rule missing from cards.css"
        )
        self.assertIn(
            'height: var(--hand-row-height)', deck_hand_children_rule.group(0),
            "deckHand hand rows must keep a fixed height of var(--hand-row-height) "
            "so the hand fan / end-turn button stay the same visible size as the "
            "playerBoard grows above them"
        )
        self.assertIsNotNone(
            re.search(r'--hand-row-height\s*:', cards_css),
            "cards.css must declare --hand-row-height so deckHand rows keep a "
            "fixed visible size"
        )

    def test_board_fits_mobile_viewport_without_overflow(self):
        """The board fits phone screens with no overflow and no scroll fighting.

        User story: open the board on a 320×568 or 390×844 phone; the enemy
        board, the four lanes, the deck, the hand and the end-turn control all
        stay inside the viewport. Lanes may not force a 536px minimum row, the
        fixed player table may not park itself on top of the enemy board, and
        excess hand cards scroll inside the hand region instead of spilling
        over the document. A desktop window keeps the original 82vw layout,
        the fixed player table, and the unclipped hand row.

        The board shrinks on short narrow screens through a single
        --board-scale lever: the board font drives every em-based offset while
        the rem-sized card geometry multiplies by the same lever, so the
        stacked-card look survives at any scale.
        """
        import os
        import re

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.css')) as css_file:
            drag_css = css_file.read()
        with open(os.path.join(static_dir, 'demoNavigation.css')) as css_file:
            demo_nav_css = css_file.read()

        def css_block(source, opener):
            start = source.index(opener)
            depth = 0
            for offset in range(source.index('{', start), len(source)):
                depth += source[offset] == '{'
                depth -= source[offset] == '}'
                if depth == 0:
                    return source[start:offset + 1]
            raise AssertionError(f'unclosed css block for {opener}')

        player_screen_rule = re.search(r'div\.playerScreen\s*\{[^}]*\}', cards_css)
        self.assertIn('--board-scale: 1', player_screen_rule.group(0))
        self.assertIn(
            'font-size: calc(1rem * var(--board-scale))', player_screen_rule.group(0),
            "the board font is the em-side of the scale lever"
        )

        card_rule = re.search(r'\.playingCards \.card\s*\{[^}]*\}', cards_css)
        self.assertIn('width: calc(4.25rem * var(--board-scale, 1))', card_rule.group(0))
        self.assertIn('height: calc(6rem * var(--board-scale, 1))', card_rule.group(0))
        card_container_rule = re.search(r'\nli\.cardContainer\s*\{[^}]*\}', cards_css)
        self.assertIn(
            'calc((4.75rem + 6px) * var(--board-scale, 1))', card_container_rule.group(0)
        )
        card_row_rule = re.search(r'\nul\.cardRow\s*\{[^}]*\}', cards_css)
        self.assertIn(
            'min-height: calc(7.5rem * var(--board-scale, 1))', card_row_rule.group(0)
        )
        end_turn_rule = re.search(r'\nbutton\.end-turn\s*\{[^}]*\}', cards_css)
        self.assertIn(
            'width: calc(4.25rem * var(--board-scale, 1))', end_turn_rule.group(0)
        )
        hologram_row_rule = re.search(r'\nul\.hologramRow\s*\{[^}]*\}', drag_css)
        self.assertIn(
            'min-height: calc(7.5rem * var(--board-scale, 1))',
            hologram_row_rule.group(0),
            "the drop-preview row is an interaction overlay and must scale with "
            "the cards it previews"
        )

        mobile_block = css_block(cards_css, '@media (max-width: 41rem) {')
        self.assertIn('height: 100dvh', mobile_block)
        self.assertIn('position: static', mobile_block)
        self.assertIn('flex: 1 1 0', mobile_block)
        self.assertIn('min-height: 0', mobile_block)
        self.assertIn('overflow-y: auto', mobile_block)
        self.assertIn('width: 100%', mobile_block)
        self.assertIn('min-width: 0', mobile_block)
        self.assertIn('overflow-x: auto', mobile_block)
        self.assertIn(
            'padding-top: 1.25em', mobile_block,
            "rotated hand-fan cards must lift into the scroll box's padding "
            "instead of being clipped by it"
        )
        tier_block = css_block(
            cards_css, '@media (max-width: 41rem) and (max-height: 49.375rem) {'
        )
        self.assertIn('--board-scale: .7', tier_block)
        short_tier_block = css_block(
            cards_css, '@media (max-width: 41rem) and (max-height: 34rem) {'
        )
        self.assertIn('--board-scale: .58', short_tier_block)

        deck_hand_rule = re.search(r'\.playerScreen \.deckHand\s*\{[^}]*\}', cards_css)
        self.assertIn('--hand-row-height: 8em', deck_hand_rule.group(0))
        self.assertNotIn('position: absolute', deck_hand_rule.group(0))
        self.assertNotIn('.playerScreen > .deckHand', cards_css)
        self.assertNotIn('height: 25%', cards_css)
        board_hand_scroll_rule = re.search(
            r'\.playerScreen \.deckHand > \.hand-scroll\s*\{[^}]*\}', cards_css
        )
        self.assertIn('overflow: visible', board_hand_scroll_rule.group(0))

        lanes_rule = re.search(r'^ul\.lanes\s*\{[^}]*\}', cards_css, re.MULTILINE)
        self.assertIn('width: 82vw', lanes_rule.group(0))
        player_table_rule = re.search(
            r'\.playerScreen\s*>\s*ul:not\(\.enemyBoards\)\s*\{[^}]*\}', cards_css
        )
        self.assertIn('position: fixed', player_table_rule.group(0))
        self.assertIn('bottom: 0', player_table_rule.group(0))

        demo_nav_block = css_block(demo_nav_css, '@media (max-width: 41rem) {')
        self.assertIn('max-width: 40%', demo_nav_block)
        self.assertIn('.demoNav .playerInfo', demo_nav_block)
        self.assertIn('text-overflow: ellipsis', demo_nav_block)

        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)
        self._replace_deck_with_count(self.human_participant, 64)
        self._replace_deck_with_count(self.bot_participant, 64)
        content = self.client.get(board_url).content.decode()
        self.assertIsNotNone(
            re.search(r'--deck-indicator-offset: -\d+(\.\d+)?em;"', content),
            "deck indicator offsets must follow the board font (em) so the "
            "fanned indicator piles track the scaled deck on phones"
        )

    def test_card_art_fits_face_without_cropping_or_overflow(self):
        """Card artwork stays whole and inside every card face.

        User story: a card with portrait, landscape or square art —
        downloaded art or the no-art fallback picture — shows the complete
        image on the board lanes, in the hand, in collections and on the
        card details page. The art is never cropped to a fixed square,
        never stretched, and never painted past the card border: card
        faces give the picture a width/height box of their own content
        minus the title/type footer, compact small-card boxes contain it
        in their square, and the full-art spotlight contains it in its
        14rem showcase box. Decorative full-page backgrounds still fill
        their viewport, and the CSS playing-card faces keep their
        rank/suit look untouched.
        """
        import os
        import re
        from mysite.jinja2 import (
            playing_card_rank_class,
            playing_card_rank_display,
            playing_card_suit_class,
            playing_card_suit_display,
        )

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()
        with open(os.path.join(static_dir, 'demoNavigation.css')) as css_file:
            demo_nav_css = css_file.read()
        with open(os.path.join(static_dir, 'title.css')) as css_file:
            title_css = css_file.read()
        with open(os.path.join(static_dir, 'style.css')) as css_file:
            style_css = css_file.read()

        def css_block(source, opener):
            start = source.index(opener)
            depth = 0
            for offset in range(source.index('{', start), len(source)):
                depth += source[offset] == '{'
                depth -= source[offset] == '}'
                if depth == 0:
                    return source[start:offset + 1]
            raise AssertionError(f'unclosed css block for {opener}')

        base_picture_rule = css_block(cards_css, '.fit-picture{')
        self.assertIn(
            'object-fit: contain', base_picture_rule,
            "every fit-picture defaults to contain so no image is ever "
            "stretched by the leftover fill default"
        )
        self.assertNotIn('cover', base_picture_rule)

        board_face_rule = re.search(
            r'\.playingCards \.card\.smallCard > \.fit-picture\s*\{[^}]*\}', cards_css
        )
        self.assertIsNotNone(
            board_face_rule,
            "card faces need their own fit-picture rule to give art a "
            "box-aware area inside the face"
        )
        self.assertIn('object-fit: contain', board_face_rule.group(0))
        self.assertIn(
            'width: 100%', board_face_rule.group(0),
            "art spans the card content width instead of a fixed square"
        )
        self.assertIn(
            'height: calc(100% - 2.5rem)', board_face_rule.group(0),
            "art yields the bottom strip of the face to the title/type "
            "footer so neither the art nor the footer leaves the card"
        )

        option_picture_rule = re.search(r'\n\.smallCard \.fit-picture\s*\{[^}]*\}', cards_css)
        self.assertIsNotNone(
            option_picture_rule,
            "compact small-card boxes (deck/player pickers) keep a "
            "bounded square art area"
        )
        self.assertIn(
            'width: calc(4rem * var(--board-scale, 1))', option_picture_rule.group(0)
        )
        self.assertIn(
            'height: calc(4rem * var(--board-scale, 1))', option_picture_rule.group(0)
        )

        spotlight_rule = re.search(r'\n\.spotlight\{[^}]*\}', style_css)
        self.assertIsNotNone(spotlight_rule, "spotlight art box rule missing from style.css")
        self.assertIn('width: 14rem', spotlight_rule.group(0))
        self.assertIn('height: 14rem', spotlight_rule.group(0))

        for opener, source, name in (
            ('.fullpage-background{', demo_nav_css, 'demo page backdrop'),
            ('.title-background{', title_css, 'title page backdrop'),
        ):
            self.assertIn(
                'object-fit: cover', css_block(source, opener),
                f"the {name} must keep cover now that the fit-picture base "
                "rule no longer crops decorative backgrounds"
            )

        self.assertIn(
            '.playingCards .card.smallCard[class*="rank-"] .smallCardInfo', cards_css,
            "the static playing-card footer anchoring must stay as is"
        )
        self.assertIn(
            '.playingCards .card.staticCard .smallCardInfo .cardType', cards_css
        )
        self.assertIn('margin-bottom: -1px', cards_css)
        self.assertIn('margin-bottom: -2.75rem', cards_css)
        self.assertIn('font-size: 7px', cards_css)

        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)

        static_card = Card.objects.create(
            title="Board static card", artSource="static", cardType=1
        )
        static_game_card = GameCard.create(static_card.id, self.game.id, self.human_participant.id)
        static_game_card.save()
        static_game_card.state.draw()
        static_game_card.state.updateOrdinal(50)
        static_game_card.state.save()

        content = self.client.get(board_url).content.decode()
        self.assertIsNotNone(
            re.search(
                r'<div class="card smallCard">\s*'
                r'<img draggable="false" class="fit-picture" '
                r'src="/static/MMM/1flubeltje\.jpg"',
                content,
            ),
            "art cards must render their picture inside the card face div"
        )
        self.assertIsNotNone(
            re.search(
                r'class="card smallCard staticCard '
                + re.escape(playing_card_rank_class(static_card))
                + r'\s+'
                + re.escape(playing_card_suit_class(static_card)),
                content,
            ),
            "static playing-card faces must keep their rank/suit classes on "
            "the board"
        )
        self.assertIn(
            f'<span class="rank">{playing_card_rank_display(static_card)}</span>', content
        )
        self.assertIn(
            f'<span class="suit">{playing_card_suit_display(static_card)}</span>', content
        )

        card_page = self.client.get(reverse("MMM:viewCard", args=[self.human_cards[0].id]))
        self.assertContains(
            card_page, '<img class="fit-picture spotlight" '
            'src="/static/MMM/1flubeltje.jpg"'
        )

    def test_deck_flight_clone_overlays_the_pile_inside_the_cards_scope(self):
        """Deck flights keep the pile intact and render like real board cards.

        The flight clone is positioned fixed over the deck instead of being
        inserted into the pile, and it is appended inside the board's
        .playingCards root: the pile's stacking is never shifted, and a bot's
        deck->lane play carries the landed card's face markup under the same
        CSS scope as a player's face-up lane play, so its rank and suit render
        exactly like every other card on the board instead of collapsing into
        unscoped body text.
        """
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()

        duplicate_card = _extract_js_brace_block(loading_js, 'function duplicateCard(')
        deck_branch = _extract_js_brace_block(duplicate_card, 'if (sourceLane < 0)')

        self.assertNotIn('insertBefore', deck_branch)
        self.assertNotIn('laneElement.appendChild', deck_branch)
        self.assertEqual(deck_branch.count('appendChild'), 1)
        self.assertIn("closest('.playingCards')", deck_branch)
        self.assertIn('document.body', deck_branch)
        self.assertNotIn('document.body.appendChild', deck_branch)
        self.assertIn("'li:last-of-type'", deck_branch)
        self.assertIn('getBoundingClientRect', deck_branch)
        self.assertIn("position = 'fixed'", deck_branch)
        self.assertIn('--move-x', deck_branch)
        
        self.assertIn("classList.add('duplicate-deck-flight')", deck_branch)
        self.assertIn("topStackCard?.querySelector('.card')", deck_branch)
        self.assertIn(
            '.playingCards .card.back,\n.duplicate-deck-flight .card.back',
            cards_css,
        )
        self.assertIn('.duplicate-deck-flight > .card.back', cards_css)

    def test_enemy_deck_play_flight_clone_keeps_the_landed_card_face(self):
        """The bot's deck->lane flight clone renders like the landed card.

        User story: end the turn, the bot plays a card, and the card flying
        from the enemy deck to the enemy lane must show the same styled face
        as the landed card. duplicateCard must append the enemy play clone
        inside the .playingCards board (never on the body, where every
        .playingCards card rule is out of scope and the rank and suit collapse
        into one unstyled inline line), must keep the clone's static face
        markup intact, and must leave the enemy deck pile untouched. The
        player's own deck->hand draw keeps hiding its face instead.
        """
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()

        harness = FAKE_ELEMENT_NAVIGATION_CORE + r"""
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen playingCards rotateHand');
body.appendChild(playerScreen);
const enemyBoards = new FakeElement('ul', 'enemyBoards basic-mat table');
playerScreen.appendChild(enemyBoards);
const enemyBoard = new FakeElement('li', 'enemyBoard');
enemyBoards.appendChild(enemyBoard);
const enemyDeckHand = new FakeElement('div', 'enemyDeckHand');
enemyBoard.appendChild(enemyDeckHand);
const enemyDeckStack = new FakeElement('div', 'deck-stack enemy-deck-stack');
enemyDeckHand.appendChild(enemyDeckStack);
const enemyDeck = new FakeElement('ul', 'deck enemyDeck active-deck');
enemyDeckStack.appendChild(enemyDeck);
const enemyDeckTop = new FakeElement('li', 'cardContainer faceDown');
enemyDeck.appendChild(enemyDeckTop);
enemyDeckTop.appendChild(new FakeElement('div', 'card back smallCard'));

const enemyLanes = new FakeElement('ul', 'lanes');
enemyBoard.appendChild(enemyLanes);
const enemyLane = new FakeElement('li', 'lane Visciousness');
enemyLanes.appendChild(enemyLane);
const enemyCardRow = new FakeElement('ul', 'cardRow');
enemyLane.appendChild(enemyCardRow);
const playedCard = new FakeElement('li', 'cardContainer loading');
playedCard.setAttribute('data-source-lane', '-1');
playedCard.setAttribute('data-source-ordinal', '0');
playedCard.setAttribute('data-card-id', '5');
enemyCardRow.appendChild(playedCard);
const playedFace = new FakeElement('div', 'card smallCard staticCard rank-9 clubs');
playedCard.appendChild(playedFace);
playedFace.appendChild(new FakeElement('span', 'rank'));
playedFace.appendChild(new FakeElement('span', 'suit'));
playedFace.appendChild(new FakeElement('div', 'smallCardInfo'));

const playerBoard = new FakeElement('li', 'playerBoard');
playerScreen.appendChild(playerBoard);
const playerDeckStack = new FakeElement('div', 'deck-stack own-deck-stack');
playerBoard.appendChild(playerDeckStack);
const playerDeck = new FakeElement('ul', 'deck active-deck');
playerDeckStack.appendChild(playerDeck);
const playerDeckTop = new FakeElement('li', 'cardContainer faceDown');
playerDeck.appendChild(playerDeckTop);
playerDeckTop.appendChild(new FakeElement('div', 'card back smallCard'));
const deckHand = new FakeElement('div', 'deckHand handContainer');
playerScreen.appendChild(deckHand);
const handFan = new FakeElement('ul', 'hand hand-fan');
deckHand.appendChild(handFan);
const drawnHandCard = new FakeElement('li', 'cardContainer loading');
drawnHandCard.setAttribute('data-source-lane', '-2');
drawnHandCard.setAttribute('data-source-ordinal', '0');
handFan.appendChild(drawnHandCard);
const drawnFace = new FakeElement('div', 'card smallCard staticCard rank-3 diams');
drawnHandCard.appendChild(drawnFace);
drawnFace.appendChild(new FakeElement('span', 'rank'));
drawnFace.appendChild(new FakeElement('span', 'suit'));

const fakeDocument = {
    querySelector(selector) { return body.querySelector(selector); },
    querySelectorAll(selector) { return body.querySelectorAll(selector); },
    addEventListener() {},
    readyState: 'complete',
    body,
};
global.document = fakeDocument;

eval(__LOADING_JS__);

const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};

const playedClone = duplicateCard(playedCard, -1, 0);
assert('the enemy play produces a flight clone', playedClone !== null);
assert('the enemy play clone is appended inside the .playingCards board',
    playedClone.closest('.playingCards') === playerScreen &&
    !body.children.includes(playedClone));
assert('the enemy play clone overlays the pile with fixed positioning',
    playedClone.style.position === 'fixed');
assert('the enemy deck pile keeps exactly its own top card',
    enemyDeck.children.length === 1 && enemyDeckTop.parentNode === enemyDeck);
assert('the enemy play clone keeps the landed card face markup',
    playedClone.querySelector('.card.staticCard.rank-9.clubs') !== null &&
    playedClone.querySelector('.rank') !== null &&
    playedClone.querySelector('.suit') !== null &&
    playedClone.querySelector('.smallCardInfo') !== null);
assert('the enemy play clone shows its face instead of a hidden back',
    !playedClone.classList.contains('faceDown') &&
    playedClone.querySelector('.card').classList.contains('back') === false);

const drawnClone = duplicateCard(drawnHandCard, -2, 0);
assert('the player draw produces a flight clone', drawnClone !== null);
assert('the player draw clone is appended inside the .playingCards board',
    drawnClone.closest('.playingCards') === playerScreen);
assert('the player draw clone hides its face as a plain card back',
    drawnClone.classList.contains('faceDown') &&
    drawnClone.querySelector('.card').classList.contains('back') &&
    drawnClone.querySelector('.card').children.length === 0);

console.log('enemy deck play flight face ok');
""".replace('__LOADING_JS__', repr(loading_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping enemy deck play flight face DOM test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping enemy deck play flight face DOM test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'enemy deck play flight face harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('enemy deck play flight face ok', completed.stdout)

    def test_draw_flight_reload_window_waits_for_flight_completion(self):
        """The no-phase branch must wait out the full card flight.

        moveDuration (up to 1.2s) exceeds the stagger window (delay/2), so the
        reload used to fire mid-flight and cut the deck->hand animation short.
        The reload window must include the flight finish time.
        """
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()

        self.assertIn('const playerFinished', loading_js)
        self.assertIn('moveDuration * 1000 + 150', loading_js)
        self.assertIn('playerFinished,', loading_js)
        self.assertIn('schedule(reloadToBoard, reloadWindow)', loading_js)

    def test_draw_flights_start_after_scroll_settles(self):
        """Deck->hand flights must be measured after the browser restores the scroll position.

        The browser restores the previous page's scroll offset shortly after
        DOMContentLoaded. Measuring the flight at DOMContentLoaded time (scroll
        still at the top) leaves the whole animation out of view below the
        fold. The flight start must be deferred until the scroll settles (load
        event with a bounded fallback) and the deck scrolled into view first.
        """
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()

        start_flights = _extract_js_brace_block(loading_js, 'const startFlights = (run) =>')
        # Wait for the load event (scroll restoration target) with a bounded
        # fallback so a hanging subresource can't stall the sequence.
        self.assertIn("document.readyState === 'complete'", start_flights)
        self.assertIn("addEventListener('load', begin, { once: true })", start_flights)
        self.assertIn('schedule(begin, 150)', start_flights)
        # The deck/hand must be on screen before the flight is measured.
        self.assertIn(".playerScreen .deckHand", start_flights)
        self.assertIn("scrollIntoView({ block: 'end' })", start_flights)

        # Both player-flight branches defer through startFlights; the
        # no-player-element paths keep their immediate scheduling.
        player_moves = _extract_js_brace_block(loading_js, "if (phase === 'playerMoves')")
        self.assertIn('startFlights(runPlayerMoves)', player_moves)
        self.assertIn('startFlights(runFlights)', loading_js)

    def test_animation_skip_and_pause_controls(self):
        """Enemy-turn/timeline sequences can be skipped and paused from the keyboard."""
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()

        self.assertIn('class PausableTimeout', loading_js)
        self.assertIn('class AnimationControls', loading_js)
        self.assertIn('skipAnimations()', loading_js)
        self.assertIn('togglePause()', loading_js)
        self.assertIn("key === 'e' || key === 'E' || key === 'Enter' || key === 'Escape'", loading_js)
        self.assertIn(
            "key === 'w' || key === 'W' || key === ' ' || key === 'Space' || key === 'Spacebar'",
            loading_js,
        )
        self.assertIn('this._scheduler.cancelAll()', loading_js)
        self.assertIn("addEventListener('keydown'", loading_js)

        # The enemy phase must run through the pausable scheduler so pause
        # and skip can actually stop it.
        enemy_block = _extract_js_brace_block(loading_js, "if (phase === 'enemy')")
        self.assertIn('schedule(reloadToBoard, reloadWindow)', enemy_block)
        self.assertIn('turnMarker(', enemy_block)

        self.assertIn('.pauseIndicator', cards_css)
        self.assertIn('.pauseIndicator.visible', cards_css)

    def test_ghost_card_numbering_and_flip_contract(self):
        """Staged ghosts keep their hand slot number and can be flipped face up."""
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        self.assertIn('orderableKeyboardCards', drag_js)
        self.assertIn('_isGhostFlipCandidate', drag_js)
        self.assertIn('_stagedLaneForGhost', drag_js)
        self.assertIn('_selectGhostFlipCard', drag_js)
        self.assertIn('_confirmGhostFlipSelection', drag_js)
        self.assertIn('ghostFlip: true', drag_js)
        self.assertIn('ghostFlip: false', drag_js)
        self.assertIn('card.dataset.stagedLane = String(laneValue);', drag_js)
        self.assertIn('hologram.dataset.stagedForCardId = String(cardId);', drag_js)
        self.assertIn('card.dataset.stagedFlipped', drag_js)

        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]
        self.assertIn('    _isStagedGhost_Legacy(card) {', control_class)
        self.assertIn('    _isOrderableKeyboardCard_Legacy(card) {', control_class)
        self.assertIn('    _isGhostFlipCandidate_Legacy(card) {', control_class)
        self.assertIn('    _stagedLaneForGhost_Legacy(card) {', control_class)
        self.assertIn('    _selectGhostFlipCard(card, digitBuffer) {', control_class)
        self.assertIn('    _confirmGhostFlipSelection(event = null) {', control_class)

        # The control forwards each predicate to the arrow passed in from init().
        is_staged_ghost_legacy = control_class[
            control_class.index('    _isStagedGhost_Legacy(card) {'):
            control_class.index('    _isOrderableKeyboardCard_Legacy(card)')
        ]
        self.assertIn('this._predicates.isStagedGhost(card)', is_staged_ghost_legacy)
        is_orderable_legacy = control_class[
            control_class.index('    _isOrderableKeyboardCard_Legacy(card) {'):
            control_class.index('    _isGhostFlipCandidate_Legacy(card)')
        ]
        self.assertIn('this._predicates.isOrderableKeyboardCard(card)', is_orderable_legacy)
        is_ghost_flip_legacy = control_class[
            control_class.index('    _isGhostFlipCandidate_Legacy(card) {'):
            control_class.index('    _stagedLaneForGhost_Legacy(card)')
        ]
        self.assertIn('this._predicates.isGhostFlipCandidate(card)', is_ghost_flip_legacy)

        # Ghost flips rewrite the staged play cookie with flipFaceUp=true.
        confirm_ghost_flip = control_class[
            control_class.index('    _confirmGhostFlipSelection(event = null) {'):
            control_class.index('    selectKeyboardCard(card')
        ]
        self.assertIn(
            'this.parent.createupdateCookie(cardId, laneValue, true, selection.sourceLane, selection.sourceOrdinal);',
            confirm_ghost_flip,
        )
        # card.dataset.stagedFlipped is set on the staged hologram AND on the
        # hand ghost in the same method.
        self.assertIn("card.dataset.stagedFlipped = 'true';", confirm_ghost_flip)

        # The same flag is set on lane-card face-down clicks (line ~1504 in the original).
        on_face_down = drag_js[
            drag_js.index('    onFaceDownCardClick(e, laneValue) {'):
            drag_js.index('    createupdateCookie(cardId, laneValue, flipFaceUp')
        ]
        self.assertIn("card.dataset.stagedFlipped = 'true';", on_face_down)

        # The predicate arrows live in init() and keep the split semantics:
        # staged ghosts are countable, flipped ghosts are not re-flippable.
        is_staged_ghost_arrow = drag_js[
            drag_js.index('        const isStagedGhost = (card) => {'):
            drag_js.index('        const isOrderableKeyboardCard = (card) => {')
        ]
        self.assertNotIn('stagedFlipped', is_staged_ghost_arrow)
        self.assertIn("classList.contains('ghost')", is_staged_ghost_arrow)
        is_ghost_flip_arrow = drag_js[
            drag_js.index('        const isGhostFlipCandidate = (card) => {'):
            drag_js.index('        const handCards')
        ]
        self.assertIn("stagedFlipped === 'true'", is_ghost_flip_arrow)
        is_orderable_arrow = drag_js[
            drag_js.index('        const isOrderableKeyboardCard = (card) => {'):
            drag_js.index('        const stagedLaneForGhost')
        ]
        self.assertIn('isPlayableKeyboardCard(card)', is_orderable_arrow)
        self.assertIn('isStagedGhost(card)', is_orderable_arrow)
        self.assertNotIn('isGhostFlipCandidate(card)', is_orderable_arrow)

        # Number selection is position-based over the full hand (ghosts
        # included): the ghost in slot 1 no longer shifts later cards.
        keydown_code = drag_js[
            drag_js.index('    onKeyboardKeyDown(event)'):
            drag_js.index('    selectOrderedCard(')
        ]
        self.assertIn('orderableCards[ordinal - 1]', keydown_code)
        self.assertIn('orderableCards[lastDigitOrdinal - 1]', keydown_code)
        self.assertIn('selectOrderedCard(', keydown_code)

        # Staging must never write the flip cookie inside selectKeyboardCard;
        # the ghost-flip helpers live outside the selection slice.
        selection_code = control_class[
            control_class.index('    selectKeyboardCard(card'):
            control_class.index('    moveKeyboardSelection(laneValue)')
        ]
        self.assertNotIn('createupdateCookie', selection_code)
        self.assertIn(
            'return this._selectGhostFlipCard(card, digitBuffer);',
            selection_code,
        )

        # Ghosts are no longer blocked when the play budget is exhausted, so
        # they stay selectable for their face-up flip.
        affordances_code = drag_js[
            drag_js.index('    applyTurnAffordances() {'):
            drag_js.index('    createDropZones() {')
        ]
        self.assertIn("!card.classList.contains('ghost')", affordances_code)

        # Parent-side: the wrappers delegate straight to the control's Legacy
        # implementations; back-compat probes still work against them.
        parent_class = drag_js[control_class_end:]
        self.assertIn(
            'this._keyboardSelectionControl._isOrderableKeyboardCard_Legacy(card)',
            parent_class,
        )
        self.assertIn(
            'this._keyboardSelectionControl._isGhostFlipCandidate_Legacy(card)',
            parent_class,
        )
        self.assertIn(
            'this._keyboardSelectionControl._handCardForId_Legacy(cardId)',
            parent_class,
        )

        select_ordered_start = drag_js.index('    selectOrderedCard(card')
        select_ordered_end = drag_js.index(
            '    flipKeyboardFocusedCard(event) {',
            select_ordered_start,
        )
        select_ordered = drag_js[select_ordered_start:select_ordered_end]
        self.assertIn("stagedFlipped === 'true'", select_ordered)

    def test_trusted_cards_have_no_focus_or_hover_styling(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()
        with open(os.path.join(static_dir, 'hoverCooldown.js')) as js_file:
            hover_js = js_file.read()

        self.assertNotIn(
            'ul.cardRow[title="trustedCards"] li.cardContainer:focus-within',
            cards_css,
        )
        self.assertNotIn(
            'ul.cardRow[title="trustedCards"] li.cardContainer:not(.blocked):focus-within',
            cards_css,
        )
        self.assertNotIn('ul.cardRow[title="trustedCards"]', hover_js)
        self.assertNotIn(
            '.playerScreen ul.cardRow[title="trustedCards"] li.cardContainer',
            hover_js,
        )

        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)
        response = self.client.get(board_url)
        content = response.content.decode()
        own_board = re.search(
            r'<li class="playerBoard.*?(?=<div class="deckHand)',
            content, re.DOTALL,
        )
        self.assertIsNotNone(own_board)
        own_board_markup = own_board.group(0)
        trusted_tags = re.findall(
            r'<ul class="cardRow" title="trustedCards">(.*?)</ul>',
            own_board_markup, re.DOTALL,
        )
        self.assertTrue(trusted_tags)
        for tag in trusted_tags:
            for li_tag in re.findall(r'<li class="cardContainer[^>]*>', tag):
                self.assertNotIn('faceDown', li_tag)
                self.assertNotIn('tabindex', li_tag)
                self.assertNotIn('draggable="true"', li_tag)

    def test_ghost_card_numbering_keeps_flipped_face_up_ghosts_countable(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        self.assertIn('orderableKeyboardCards()', drag_js)
        self.assertIn('_isOrderableKeyboardCard', drag_js)

        is_staged_ghost_arrow = drag_js[
            drag_js.index('        const isStagedGhost = (card) => {'):
            drag_js.index('        const isOrderableKeyboardCard = (card) => {')
        ]
        self.assertNotIn('stagedFlipped', is_staged_ghost_arrow)
        self.assertIn("classList.contains('ghost')", is_staged_ghost_arrow)

        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]
        staged_wrapper = control_class[
            control_class.index('    _isStagedGhost_Legacy(card) {'):
            control_class.index('    _isOrderableKeyboardCard_Legacy(card)')
        ]
        self.assertIn('this._predicates.isStagedGhost(card)', staged_wrapper)

        parent_class = drag_js[control_class_end:]
        self.assertIn(
            'this._keyboardSelectionControl._isOrderableKeyboardCard_Legacy(card)',
            parent_class,
        )

    def test_add_hover_arrow_binds_focus_and_mouse_events(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        arrow_helper = drag_js[
            drag_js.index('    _addHoverArrow(sourceEl, targetEl) {'):
            drag_js.index('    _createCurvedArrow')
        ]
        self.assertIn("addEventListener('mouseenter'", arrow_helper)
        self.assertIn("addEventListener('mouseleave'", arrow_helper)
        self.assertNotIn("addEventListener('focusin'", arrow_helper)
        self.assertNotIn("addEventListener('focusout'", arrow_helper)

    def test_lane_face_down_card_hover_arrow_binds_to_focus(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        on_face_down = drag_js[
            drag_js.index('    onFaceDownCardClick(e, laneValue) {'):
            drag_js.index('    createupdateCookie(cardId, laneValue, flipFaceUp')
        ]
        self.assertIn('_addHoverArrow(card, flipHologram)', on_face_down)
        self.assertIn("flipHologram.classList.add('hologram')", on_face_down)
        self.assertIn("card.dataset.stagedFlipped = 'true';", on_face_down)
        self.assertLess(
            on_face_down.index("card.classList.add('ghost');"),
            on_face_down.index("card.dataset.stagedFlipped = 'true';"),
        )
        arrow_helper = drag_js[
            drag_js.index('    _addHoverArrow(sourceEl, targetEl) {'):
            drag_js.index('    _createCurvedArrow')
        ]
        self.assertNotIn("'focusin'", arrow_helper)

        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)
        response = self.client.get(board_url)
        content = response.content.decode()
        own_board = re.search(
            r'<li class="playerBoard.*?(?=<div class="deckHand)',
            content, re.DOTALL,
        )
        self.assertIsNotNone(own_board)
        own_board_markup = own_board.group(0)
        flippable_tags = re.findall(
            r'<ul class="cardRow" title="cards">(.*?)</ul>',
            own_board_markup, re.DOTALL,
        )
        self.assertTrue(flippable_tags)
        for row in flippable_tags:
            for li_tag in re.findall(r'<li class="cardContainer[^>]*>', row):
                if 'faceDown' in li_tag:
                    self.assertIn('tabindex="0"', li_tag)

    def test_create_focus_arrow_wraps_curved_arrow_and_binds_no_listeners(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        helper_start = drag_js.index('    _createFocusArrow(sourceEl, targetEl) {')
        helper_end = drag_js.index('    _focusArrowTarget(card) {')
        focus_arrow_helper = drag_js[helper_start:helper_end]
        self.assertIn('this._createCurvedArrow(sourceEl, targetEl)', focus_arrow_helper)
        self.assertIn('document.body.appendChild(arrow)', focus_arrow_helper)
        self.assertIn("sourceEl.classList.add('hover')", focus_arrow_helper)
        self.assertIn("targetEl.classList.add('hover')", focus_arrow_helper)
        self.assertIn('return arrow;', focus_arrow_helper)
        self.assertNotIn('addEventListener', focus_arrow_helper)

    def test_focus_arrow_target_resolves_hand_and_flipped_lane_targets(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        helper_start = drag_js.index('    _focusArrowTarget(card) {')
        parent_class_end = drag_js.index('    onFaceDownCardClick(e, laneValue) {')
        focus_target_helper = drag_js[helper_start:parent_class_end]
        self.assertIn(".playerScreen .deckHand", focus_target_helper)
        self.assertIn(
            '.hologram[data-staged-for-card-id="${CSS.escape(cardId)}"]',
            focus_target_helper,
        )
        self.assertIn('.playerScreen .playerBoard ul.cardRow', focus_target_helper)
        self.assertIn("dataset.stagedFlipped === 'true'", focus_target_helper)
        self.assertIn('data-flip-for-card-id="${CSS.escape(cardId)}"', focus_target_helper)
        self.assertIn('this._cardIdInput(card)?.value', focus_target_helper)
        self.assertIn('if (!cardId) return null;', focus_target_helper)
        self.assertIn(":scope > .hologramRow > .hologram", focus_target_helper)

    def test_focus_arrow_target_returns_null_for_unfocusable_card(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        helper_start = drag_js.index('    _focusArrowTarget(card) {')
        parent_class_end = drag_js.index('    onFaceDownCardClick(e, laneValue) {')
        focus_target_helper = drag_js[helper_start:parent_class_end]
        self.assertIn('if (!card || typeof card.closest !== \'function\') return null;', focus_target_helper)
        self.assertIn('return null;', focus_target_helper)

    def test_focus_arrow_target_resolves_keyboard_preview_hologram(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        helper_start = drag_js.index('    _focusArrowTarget(card) {')
        parent_class_end = drag_js.index('    onFaceDownCardClick(e, laneValue) {')
        focus_target_helper = drag_js[helper_start:parent_class_end]
        self.assertIn('.hologram.keyboard-preview', focus_target_helper)
        self.assertIn('data-source-card-id', focus_target_helper)
        self.assertIn('data-keyboard-preview="true"', focus_target_helper)

    def test_focus_arrow_flight_routes_played_clone_origin_to_hand_card(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        flight_start = drag_js.index('    _focusArrowFlight(card) {')
        flight_end = drag_js.index('    onFaceDownCardClick(e, laneValue) {', flight_start)
        flight_helper = drag_js[flight_start:flight_end]
        self.assertIn('if (!card || typeof card.closest !== \'function\') return null;', flight_helper)
        self.assertIn(
            '.playerScreen .hologram[data-staged-for-card-id]',
            flight_helper,
        )
        self.assertIn("if (!card.classList.contains('faceDown')) return null;", flight_helper)
        self.assertIn('this._handCardForId(stagedHologram.dataset.stagedForCardId)', flight_helper)
        self.assertIn('if (!handCard) return null;', flight_helper)
        self.assertIn('{ origin: handCard, target: card }', flight_helper)
        self.assertIn('this._focusArrowTarget(card)', flight_helper)
        self.assertIn('{ origin: card, target }', flight_helper)
        self.assertNotIn('addEventListener', flight_helper)
        self.assertNotIn('createElementNS', flight_helper)

    def test_focus_arrow_targets_own_flipped_clone_in_mixed_hologram_lane_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = FAKE_ELEMENT_DATASET_CORE + r'''
const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);

const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};

const makeHiddenIdInput = (cardId) => {
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', 'card_id');
    input.setAttribute('value', String(cardId));
    return input;
};

const playerTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(playerTable);
const playerBoard = new FakeElement('div', 'playerBoard');
playerTable.appendChild(playerBoard);
const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const lane = new FakeElement('li', 'lane Speed');
lanesEl.appendChild(lane);
const hologramRow = new FakeElement('ul', 'hologramRow');
lane.appendChild(hologramRow);
const cardRow = new FakeElement('ul', 'cardRow');
cardRow.setAttribute('title', 'cards');
lane.appendChild(cardRow);

const makeFaceDownFieldCard = (cardId) => {
    const card = new FakeElement('li', 'cardContainer faceDown');
    card.setAttribute('tabindex', '0');
    card.dataset.sourceLane = '2';
    card.dataset.sourceOrdinal = '1';
    card.appendChild(makeHiddenIdInput(cardId));
    card.appendChild(new FakeElement('div', 'card back smallCard'));
    cardRow.appendChild(card);
    return card;
};

const makeStagedPlayGhost = (stagedCardId) => {
    const hologram = new FakeElement('div', 'hologram keyboard-staged');
    hologram.dataset.stagedForCardId = String(stagedCardId);
    const clone = new FakeElement('li', 'cardContainer faceDown');
    clone.appendChild(makeHiddenIdInput(stagedCardId));
    clone.appendChild(new FakeElement('div', 'card back smallCard'));
    hologram.appendChild(clone);
    hologramRow.appendChild(hologram);
    return clone;
};

const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '1', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
    drawBlockedTitle: 'draw blocked',
    playBlockedTitle: 'play blocked',
    flipBlockedTitle: 'flip blocked',
};
body.appendChild(turnLimits);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) { return body.querySelector(selector); },
    querySelectorAll(selector) { return body.querySelectorAll(selector); },
    getElementById(id) {
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) { (documentListeners[event] ??= []).push(handler); },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/MMM/game/1/action/' },
};
global.CSS = { escape: (value) => String(value) };
global.Element = function Element() {};
global.MutationObserver = function () {
    this.observe = () => {};
    this.disconnect = () => {};
};

const deckHand = new FakeElement('div', 'deckHand handContainer');
playerTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);

const dragCode = __DRAG_JS__;
eval(dragCode);
(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const flipCardFirst = makeFaceDownFieldCard(561);
const flipCardSecond = makeFaceDownFieldCard(563);
const flipCardUnflipped = makeFaceDownFieldCard(565);
const stagedPlayClone = makeStagedPlayGhost(700);

const handGhost = new FakeElement('li', 'cardContainer ghost');
handGhost.dataset.stagedLane = '2';
handGhost.appendChild(makeHiddenIdInput(700));
handList.appendChild(handGhost);

const flipFaceDownLaneCard = (card, laneValue) => {
    system.onFaceDownCardClick({ currentTarget: card, target: card }, laneValue);
};

flipFaceDownLaneCard(flipCardFirst, 2);
const firstFlipHologram = hologramRow.children.find(
    (el) => el.getAttribute('data-flip-for-card-id') === '561',
);
assert('lane flip tags its ghost hologram with the flipped card id', Boolean(firstFlipHologram));
const firstFlipClone = firstFlipHologram.querySelector('.cardContainer');

flipFaceDownLaneCard(flipCardSecond, 2);
const secondFlipHologram = hologramRow.children.find(
    (el) => el.getAttribute('data-flip-for-card-id') === '563',
);
assert('a second flip gets its own marked hologram', Boolean(secondFlipHologram));
const secondFlipClone = secondFlipHologram.querySelector('.cardContainer');
assert('the lane row now holds three ghosts', hologramRow.children.length === 3);

assert('focus resolves the first flipped card to its own clone',
    system._focusArrowTarget(flipCardFirst) === firstFlipClone);
assert('focus never lands on the earlier staged play ghost of the same lane',
    system._focusArrowTarget(flipCardFirst) !== stagedPlayClone);
assert('focus never lands on the other flipped clone',
    system._focusArrowTarget(flipCardFirst) !== secondFlipClone);
assert('focus resolves the second flipped card to its own clone',
    system._focusArrowTarget(flipCardSecond) === secondFlipClone);
assert('an unflipped face-down card draws no focus arrow target',
    system._focusArrowTarget(flipCardUnflipped) === null);
assert('hand ghosts still pair with their staged play ghost',
    system._focusArrowTarget(handGhost) === stagedPlayClone);

const arrowCalls = [];
system._createCurvedArrow = (source, target) => {
    arrowCalls.push({ source, target });
    return new FakeElement('svg');
};
const dispatchScreenFocus = (type, card) => {
    (playerScreen.eventHandlers[type] ?? []).forEach(
        (handler) => handler({ target: card, type }),
    );
};

dispatchScreenFocus('focusin', flipCardFirst);
let liveArrow = system._keyboardSelectionControl._focusArrow;
assert('the focus arrow originates from the focused field card', liveArrow?.source === flipCardFirst);
assert('the focus arrow ends at that card own flipped ghost', liveArrow?.target === firstFlipClone);
assert('the arrow svg is attached to the document body', body.children.includes(liveArrow.arrow));

dispatchScreenFocus('focusout', flipCardFirst);
assert('focus loss clears the arrow', system._keyboardSelectionControl._focusArrow === null);

dispatchScreenFocus('focusin', flipCardSecond);
liveArrow = system._keyboardSelectionControl._focusArrow;
assert('refocusing the second card repoints the arrow at its own clone',
    liveArrow?.source === flipCardSecond && liveArrow?.target === secondFlipClone);

dispatchScreenFocus('focusout', flipCardSecond);
dispatchScreenFocus('focusin', flipCardUnflipped);
assert('unflipped field focus leaves no arrow',
    system._keyboardSelectionControl._focusArrow === null && arrowCalls.length === 2);

console.log('flipped-clone focus arrow ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping flipped-clone focus arrow test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping flipped-clone focus arrow test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'flipped-clone focus arrow harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('flipped-clone focus arrow ok', completed.stdout)

    def test_focus_on_played_face_down_clone_arrows_from_original_hand_card(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = FAKE_ELEMENT_DATASET_CORE + r'''
const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);

const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};

const makeHiddenIdInput = (cardId) => {
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', 'card_id');
    input.setAttribute('value', String(cardId));
    return input;
};

const playerTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(playerTable);
const playerBoard = new FakeElement('div', 'playerBoard');
playerTable.appendChild(playerBoard);
const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const lane = new FakeElement('li', 'lane Speed');
lanesEl.appendChild(lane);
const hologramRow = new FakeElement('ul', 'hologramRow');
lane.appendChild(hologramRow);
const cardRow = new FakeElement('ul', 'cardRow');
cardRow.setAttribute('title', 'cards');
lane.appendChild(cardRow);

const unrelatedFaceDownCard = new FakeElement('li', 'cardContainer faceDown');
unrelatedFaceDownCard.setAttribute('tabindex', '0');
unrelatedFaceDownCard.dataset.sourceLane = '2';
unrelatedFaceDownCard.dataset.sourceOrdinal = '1';
unrelatedFaceDownCard.appendChild(makeHiddenIdInput(565));
unrelatedFaceDownCard.appendChild(new FakeElement('div', 'card back smallCard'));
cardRow.appendChild(unrelatedFaceDownCard);

const deckHand = new FakeElement('div', 'deckHand handContainer');
playerTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);
const handCard = new FakeElement('li', 'cardContainer');
handCard.setAttribute('draggable', 'true');
handCard.setAttribute('tabindex', '0');
handCard.dataset.sourceLane = '0';
handCard.dataset.sourceOrdinal = '0';
handCard.appendChild(makeHiddenIdInput(700));
handCard.appendChild(new FakeElement('div', 'card smallCard back'));
handList.appendChild(handCard);

const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '1', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
    drawBlockedTitle: 'draw blocked',
    playBlockedTitle: 'play blocked',
    flipBlockedTitle: 'flip blocked',
};
body.appendChild(turnLimits);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) { return body.querySelector(selector); },
    querySelectorAll(selector) { return body.querySelectorAll(selector); },
    getElementById(id) {
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) { (documentListeners[event] ??= []).push(handler); },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/MMM/game/1/action/' },
};
global.CSS = { escape: (value) => String(value) };
global.Element = function Element() {};
global.MutationObserver = function () {
    this.observe = () => {};
    this.disconnect = () => {};
};

const dragCode = __DRAG_JS__;
eval(dragCode);
(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const stagedHologram = system._buildPlayHologram(handCard, 2);
hologramRow.appendChild(stagedHologram);
if (!system._stagePlay(handCard, 2, stagedHologram)) {
    throw new Error('staging the hand card play failed');
}
const stagedClone = stagedHologram.querySelector('.cardContainer');

assert('staging tags the lane clone with the played card id',
    stagedHologram.getAttribute('data-staged-for-card-id') === '700');
assert('staging keeps the lane clone face down and focusable',
    stagedClone.classList.contains('faceDown') && stagedClone.getAttribute('tabindex') === '0');
assert('staging marks the hand card as the played ghost',
    handCard.classList.contains('ghost') && handCard.dataset.stagedLane === '2');

const arrowCalls = [];
system._createCurvedArrow = (source, target) => {
    arrowCalls.push({ source, target });
    return new FakeElement('svg', 'hologram-arrow');
};
const bodyArrows = () => body.children.filter(
    (child) => child.classes && child.classes.has('hologram-arrow'),
);
const dispatchScreenFocus = (type, card) => {
    (playerScreen.eventHandlers[type] ?? []).forEach(
        (handler) => handler({ target: card, type }),
    );
};

dispatchScreenFocus('focusin', stagedClone);
let liveArrow = system._keyboardSelectionControl._focusArrow;
assert('focusing the played clone ties the arrow to the focused clone',
    liveArrow?.source === stagedClone);
assert('focusing the played clone records the original hand card as counterpart',
    liveArrow?.target === handCard);
assert('the played clone arrow is drawn from the original hand card',
    arrowCalls.length === 1 &&
    arrowCalls[0].source === handCard &&
    arrowCalls[0].target === stagedClone);
assert('the played clone arrow svg is attached to the body',
    bodyArrows().length === 1 && bodyArrows()[0] === liveArrow.arrow);
assert('the original card and the clone both highlight for the focus arrow',
    handCard.classes.has('hover') && stagedClone.classes.has('hover'));

dispatchScreenFocus('focusin', stagedClone);
assert('refocusing the same played clone keeps exactly one arrow svg',
    arrowCalls.length === 1 && bodyArrows().length === 1);

dispatchScreenFocus('focusout', stagedClone);
assert('losing focus on the played clone clears the arrow svg',
    system._keyboardSelectionControl._focusArrow === null && bodyArrows().length === 0);

dispatchScreenFocus('focusin', stagedClone);
assert('refocusing the played clone after blur redraws the flight from the hand card',
    arrowCalls.length === 2 &&
    arrowCalls[1].source === handCard &&
    arrowCalls[1].target === stagedClone &&
    system._keyboardSelectionControl._focusArrow.source === stagedClone &&
    system._keyboardSelectionControl._focusArrow.target === handCard);

dispatchScreenFocus('focusout', stagedClone);
dispatchScreenFocus('focusin', handCard);
liveArrow = system._keyboardSelectionControl._focusArrow;
assert('focusing the played hand ghost still ends at its staged clone',
    liveArrow?.source === handCard && liveArrow?.target === stagedClone &&
    arrowCalls[2].source === handCard && arrowCalls[2].target === stagedClone);

dispatchScreenFocus('focusout', handCard);
dispatchScreenFocus('focusin', unrelatedFaceDownCard);
assert('focusing an unrelated face-down field card draws no arrow',
    system._keyboardSelectionControl._focusArrow === null && arrowCalls.length === 3);

system.onFaceDownCardClick({ currentTarget: stagedClone, target: stagedClone }, 2);
assert('flipping the played clone turns it face up without another arrow',
    stagedClone.classList.contains('faceDown') === false && arrowCalls.length === 3);

dispatchScreenFocus('focusin', stagedClone);
assert('focusing the face-up played clone draws no origin arrow',
    system._keyboardSelectionControl._focusArrow === null && arrowCalls.length === 3);

system.onFaceDownCardClick({ currentTarget: unrelatedFaceDownCard, target: unrelatedFaceDownCard }, 2);
dispatchScreenFocus('focusin', unrelatedFaceDownCard);
liveArrow = system._keyboardSelectionControl._focusArrow;
const unrelatedFlipClone = lane.querySelector(
    '[data-flip-for-card-id="565"]'
).querySelector('.cardContainer');
assert('focusing a flipped field ghost still flies to its own clone',
    liveArrow?.source === unrelatedFaceDownCard && liveArrow?.target === unrelatedFlipClone &&
    arrowCalls[3].source === unrelatedFaceDownCard && arrowCalls[3].target === unrelatedFlipClone);

console.log('played-clone focus arrow ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping played-clone focus arrow test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping played-clone focus arrow test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'played-clone focus arrow harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('played-clone focus arrow ok', completed.stdout)

    def test_build_play_hologram_tags_keyboard_preview_with_source_card_id(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        helper_start = drag_js.index('    _buildPlayHologram(sourceCard, laneValue, keyboardPreview = false, rotation = null) {')
        helper_end = drag_js.index('    _removePreviewControls(card) {')
        build_helper = drag_js[helper_start:helper_end]
        self.assertIn("hologram.dataset.keyboardPreview = 'true'", build_helper)
        self.assertIn('hologram.dataset.sourceCardId', build_helper)
        self.assertIn('this._cardIdInput(sourceCard)?.value', build_helper)

    def test_keyboard_selection_state_includes_lane_preview_flag(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]
        empty_state_block = control_class[
            control_class.index('    _emptyKeyboardSelection() {'):
            control_class.index('    _isPlayableKeyboardCard_Legacy')
        ]
        self.assertIn('lanePreviewActive: false', empty_state_block)

    def test_escape_handler_cancels_selection_without_lane_preview_reset(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        self.assertNotIn('resetLaneSelection', drag_js)
        keydown_code = drag_js[
            drag_js.index('    onKeyboardKeyDown(event)'):
            drag_js.index('    selectOrderedCard(')
        ]
        escape_start = keydown_code.index("if (key === 'Escape') {")
        end_of_branch = keydown_code.index('if (!activeSelection && (key === \'Enter\' || key === \' \'))', escape_start)
        escape_branch = keydown_code[escape_start:end_of_branch]
        self.assertIn('if (!activeSelection) return;', escape_branch)
        self.assertIn('this._cancelKeyboardSelectionFromEvent(event)', escape_branch)
        self.assertNotIn('lanePreviewActive', escape_branch)

    def test_keyboard_cancellation_restores_selectable_hand_card_focus(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        method_start = drag_js.index('    cancelKeyboardSelection() {')
        method_end = drag_js.index('    onHandCardClick(event) {', method_start)
        cancel_method = drag_js[method_start:method_end]
        self.assertIn('this.clearKeyboardSelection();', cancel_method)
        restore_index = cancel_method.index('card.focus({ preventScroll: true })')
        self.assertIn('orderableKeyboardCards().includes(card)', cancel_method)
        self.assertLess(cancel_method.index('selectedCard'), restore_index)

        cancel_from_event = drag_js[
            drag_js.index('    _cancelKeyboardSelectionFromEvent(event) {'):
            drag_js.index('    _keyboardSelectableHandCard(event) {')
        ]
        self.assertIn('event.preventDefault()', cancel_from_event)
        self.assertIn('this.cancelKeyboardSelection()', cancel_from_event)

    def test_enter_without_selection_selects_the_focused_hand_card(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        keydown_code = drag_js[
            drag_js.index('    onKeyboardKeyDown(event)'):
            drag_js.index('    selectOrderedCard(')
        ]
        enter_start = keydown_code.index(
            "if (!activeSelection && (key === 'Enter' || key === ' ')) {"
        )
        confirm_route_index = keydown_code.index(
            'this.confirmKeyboardSelection()) event.preventDefault();'
        )
        enter_branch = keydown_code[
            enter_start:keydown_code.index(
                "if (\n            this.keyboardSelection.selectedCard &&",
                enter_start,
            )
        ]
        self.assertIn('this._keyboardSelectableHandCard(event)', enter_branch)
        self.assertIn('this.selectOrderedCard(', enter_branch)
        self.assertIn('this.orderableKeyboardCards().indexOf(selectableHandCard) + 1', enter_branch)
        flip_fallback_index = enter_branch.index('this.flipKeyboardFocusedCard(event)')
        self.assertLess(flip_fallback_index, enter_branch.index('if (event.repeat) return;'))
        self.assertLess(enter_start, confirm_route_index)

        helper_code = drag_js[
            drag_js.index('    _keyboardSelectableHandCard(event) {'):
            drag_js.index('    _isDisabledControlTarget(target) {')
        ]
        self.assertIn('orderableKeyboardCards()', helper_code)
        self.assertIn('playerHandCards().find(', helper_code)
        self.assertIn('item.contains(candidate)', helper_code)

    def test_arrow_keys_cycle_hand_cards_when_no_lane_preview(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        keydown_code = drag_js[
            drag_js.index('    onKeyboardKeyDown(event)'):
            drag_js.index('    selectOrderedCard(')
        ]
        self.assertIn('!this.keyboardSelection.lanePreviewActive', keydown_code)
        self.assertIn("key === 'ArrowLeft' || key === 'ArrowRight'", keydown_code)
        self.assertIn('playableKeyboardCards()', keydown_code)

    def test_select_hand_card_by_mouse_skips_immediate_clone(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        click_code = drag_js[
            drag_js.index('    onHandCardClick(event)'):
            drag_js.index('    onCardDragStart(e)')
        ]
        self.assertIn('selectHandCardByMouse(card, String(index + 1), event)', click_code)
        self.assertNotIn('selectHandCardByMouse', drag_js[:drag_js.index('class KeyboardSelectionControl {')])
        method_start = drag_js.index('    selectHandCardByMouse(card, digitBuffer')
        method_end = drag_js.index('\n    _updateMousePreviewCursor(', method_start)
        method_body = drag_js[method_start:method_end]
        self.assertIn('mouseSelecting: true', method_body)
        self.assertIn('hologram: null', method_body)
        self.assertIn('lanePreviewActive: false', method_body)

    def test_hand_click_lane_click_cookie_ordinal_contract(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        click_code = drag_js[
            drag_js.index('    onHandCardClick(event)'):
            drag_js.index('    onCardDragStart(e)')
        ]
        self.assertIn('this.selectHandCardByMouse(card, String(index + 1), event)', click_code)

        method_start = drag_js.index('    selectHandCardByMouse(card, digitBuffer')
        method_end = drag_js.index('\n    _updateMousePreviewCursor(', method_start)
        method_body = drag_js[method_start:method_end]
        self.assertIn('sourceOrdinal: String(this.playerHandCards().indexOf(card))', method_body)
        self.assertNotIn('card.dataset.sourceOrdinal', method_body)

        staging_code = drag_js[
            drag_js.index('    _stagePlay('):
            drag_js.index('    _buildPlayHologram(')
        ]
        self.assertIn(
            "const sourceOrdinal = sourceState?.sourceOrdinal ?? card.dataset.sourceOrdinal ?? '0';",
            staging_code,
        )
        self.assertIn(
            'this.createupdateCookie(cardId, laneValue, false, sourceLane, sourceOrdinal);',
            staging_code,
        )

        control_class = drag_js[
            drag_js.index('class KeyboardSelectionControl {'):
            drag_js.index('class CardDragDropSystem {')
        ]
        keyboard_select_start = control_class.index('    selectKeyboardCard(card, digitBuffer')
        keyboard_select_end = control_class.index('    moveKeyboardSelection(laneValue) {', keyboard_select_start)
        keyboard_select_body = control_class[keyboard_select_start:keyboard_select_end]
        self.assertIn("sourceOrdinal: card.dataset.sourceOrdinal || '0',", keyboard_select_body)

    def test_hand_click_then_lane_click_stages_zero_based_ordinal_cookie_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = r'''
const matchPart = (el, part) => {
    if (!el || !el.tagName) return false;
    const tagMatch = part.match(/^[a-zA-Z][\w-]*/);
    if (tagMatch && el.tagName.toLowerCase() !== tagMatch[0].toLowerCase()) return false;
    const idMatch = part.match(/#([\w-]+)/);
    if (idMatch && (el.id || '') !== idMatch[1]) return false;
    for (const cls of part.match(/\.([\w-]+)/g) || []) {
        if (!el.classList || !el.classList.contains(cls.slice(1))) return false;
    }
    const attrRe = /\[([\w-]+)(?:="([^"]*)")?\]/g;
    let match;
    while ((match = attrRe.exec(part))) {
        const value = el.getAttribute ? el.getAttribute(match[1]) : null;
        if (match[2] === undefined) {
            if (value === null) return false;
        } else if (String(value) !== match[2]) return false;
    }
    const notRe = /:not\(\.([\w-]+)\)/g;
    while ((match = notRe.exec(part))) {
        if (el.classList && el.classList.contains(match[1])) return false;
    }
    if (part.replace(/:not\([^)]*\)/g, '').includes(':')) return false;
    return true;
};

const matchChainFrom = (el, tokens) => {
    const last = tokens[tokens.length - 1];
    if (!matchPart(el, last.part)) return false;
    if (tokens.length === 1) return true;
    const rest = tokens.slice(0, -1);
    if (last.combinator === '>') {
        return Boolean(el.parentNode) && matchChainFrom(el.parentNode, rest);
    }
    let node = el.parentNode;
    while (node) {
        if (matchChainFrom(node, rest)) return true;
        node = node.parentNode;
    }
    return false;
};

const tokenizeChain = (chain) => {
    const tokens = [];
    const re = /(\s*>\s*|\s+)?([^>\s]+)/g;
    let match;
    while ((match = re.exec(chain)) !== null) {
        let combinator = null;
        if (match[1] && match[1].includes('>')) combinator = '>';
        else if (match[1] && match[1].trim() !== '') combinator = ' ';
        tokens.push({ part: match[2], combinator });
    }
    if (tokens.length > 0 && tokens[0].part === ':scope') {
        const [head, ...rest] = tokens;
        rest[0].combinator = '>';
        return rest;
    }
    return tokens;
};

const descendantsInOrder = (root) => {
    const result = [];
    const stack = [...root.children];
    while (stack.length) {
        const node = stack.shift();
        result.push(node);
        stack.unshift(...node.children);
    }
    return result;
};

class FakeElement {
    constructor(tag, className = '') {
        this.tagName = String(tag).toUpperCase();
        this.classes = new Set(String(className).split(/\s+/).filter(Boolean));
        this.attributes = new Map();
        this.dataset = {};
        this.children = [];
        this.parentNode = null;
        this.removed = false;
        this.id = '';
        this.title = '';
        this.eventHandlers = {};
        this.classList = {
            add: (...names) => names.forEach((name) => this.classes.add(name)),
            remove: (...names) => names.forEach((name) => this.classes.delete(name)),
            contains: (name) => this.classes.has(name),
            toggle: (name) => {
                if (this.classes.has(name)) this.classes.delete(name);
                else this.classes.add(name);
            },
        };
        this.style = {
            setProperty: () => {},
            getPropertyValue: () => '',
            getPropertyPriority: () => '',
            removeProperty: () => {},
        };
        this.getBoundingClientRect = () => ({ left: 0, top: 0, width: 10, height: 10 });
    }

    matches(selector) {
        return String(selector).split(',').some((part) => part.trim() &&
            matchChainFrom(this, tokenizeChain(part.trim())));
    }

    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches(selector)) return node;
            node = node.parentNode;
        }
        return null;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] ?? null;
    }

    querySelectorAll(selector) {
        const alternatives = String(selector).split(',').map(
            (part) => tokenizeChain(part.trim()),
        );
        return descendantsInOrder(this).filter((candidate) =>
            alternatives.some((tokens) => matchChainFrom(candidate, tokens)));
    }

    appendChild(child) {
        this.children.push(child);
        child.parentNode = this;
        return child;
    }

    insertBefore(newNode, reference) {
        let index = reference ? this.children.indexOf(reference) : this.children.length;
        if (index === -1) index = this.children.length;
        this.children.splice(index, 0, newNode);
        newNode.parentNode = this;
        return newNode;
    }

    get firstChild() {
        return this.children[0] ?? null;
    }

    contains(other) {
        let node = other;
        while (node) {
            if (node === this) return true;
            node = node.parentNode;
        }
        return false;
    }

    remove() {
        if (this.parentNode) {
            const index = this.parentNode.children.indexOf(this);
            if (index !== -1) this.parentNode.children.splice(index, 1);
        }
        this.parentNode = null;
        this.removed = true;
    }

    cloneNode(deep) {
        const clone = new FakeElement(this.tagName, [...this.classes].join(' '));
        this.attributes.forEach((value, name) => clone.setAttribute(name, value));
        if (this.id) clone.id = this.id;
        Object.assign(clone.dataset, this.dataset);
        if (deep) this.children.forEach((child) => clone.appendChild(child.cloneNode(true)));
        return clone;
    }

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
        if (name === 'id') this.id = String(value);
        if (/^[a-zA-Z][\w-]*$/.test(name)) this[name] = String(value);
        if (name === 'hidden') this.hidden = true;
    }

    getAttribute(name) {
        return this.attributes.has(name) ? this.attributes.get(name) : null;
    }

    removeAttribute(name) {
        this.attributes.delete(name);
    }

    hasAttribute(name) {
        return this.attributes.has(name);
    }

    addEventListener(name, handler) {
        (this.eventHandlers[name] ??= []).push(handler);
    }

    removeEventListener(name, handler) {
        this.eventHandlers[name] = (this.eventHandlers[name] ?? []).filter((h) => h !== handler);
    }
}

const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const matTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(matTable);
const playerBoard = new FakeElement('div', 'playerBoard');
matTable.appendChild(playerBoard);

const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const holoRows = [];
 ['', '', '', ''].forEach((unused, laneIndex) => {
    const lane = new FakeElement('li', 'lane');
    lane.classList.add(['Intelligence', 'Speed', 'Visciousness', 'Resolve'][laneIndex]);
    lanesEl.appendChild(lane);
    const holoRow = new FakeElement('ul', 'hologramRow');
    lane.appendChild(holoRow);
    holoRows.push(holoRow);
});

const deckHand = new FakeElement('div', 'deckHand handContainer');
matTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);

const makeHandCard = (cardId, cardLane, sourceOrdinal) => {
    const card = new FakeElement('li', 'cardContainer');
    card.setAttribute('tabindex', '0');
    card.setAttribute('draggable', 'true');
    card.dataset.cardLane = String(cardLane);
    card.dataset.sourceLane = '0';
    card.dataset.sourceOrdinal = String(sourceOrdinal);
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', 'card_id');
    input.setAttribute('value', String(cardId));
    card.appendChild(input);
    handList.appendChild(card);
    return card;
};
const handA = makeHandCard(301, 1, 1);
const handB = makeHandCard(302, 3, 2);
const handC = makeHandCard(303, 2, 3);
const handCards = [handA, handB, handC];

const endTurnForm = new FakeElement('form', 'cardActionForm end-turn');
playerScreen.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);
const focusedHandCardInput = new FakeElement('input');
focusedHandCardInput.setAttribute('type', 'hidden');
focusedHandCardInput.setAttribute('name', 'focused_hand_card');
focusedHandCardInput.setAttribute('value', '1');
endTurnForm.appendChild(focusedHandCardInput);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) {
        return body.querySelector(selector);
    },
    querySelectorAll(selector) {
        return body.querySelectorAll(selector);
    },
    getElementById(id) {
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) {
        (documentListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};
const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
    drawBlockedTitle: 'draw blocked',
    playBlockedTitle: 'play blocked',
    flipBlockedTitle: 'flip blocked',
};
fakeDocument.getElementById = (id) => {
    if (id === 'turnLimits') return turnLimits;
    for (const el of descendantsInOrder(body)) {
        if (el.id === id) return el;
    }
    return null;
};

const cookieWrites = [];
Object.defineProperty(fakeDocument, 'cookie', {
    set(value) { cookieWrites.push(value); },
    get() { return cookieWrites.join('; '); },
});

for (const el of [body, playerScreen, playerBoard, endTurnForm, endTurnButton, ...handCards, ...holoRows]) {
    el.focus = () => { fakeDocument.activeElement = el; };
    el.blur = () => { if (fakeDocument.activeElement === el) fakeDocument.activeElement = body; };
}

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/MMM/game/1/board/1/action/' },
};
global.CSS = { escape: (value) => String(value) };
global.MutationObserver = function (handler) {
    this.observe = () => {};
    this.disconnect = () => {};
};

const dragCode = __DRAG_JS__;
eval(dragCode);

(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const clickHandlers = documentListeners['click'] ?? [];

const pressKey = (key, options = {}) => {
    let prevented = false;
    const event = {
        key,
        repeat: options.repeat ?? false,
        target: options.target ?? fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const clickCard = (card) => {
    clickHandlers.forEach((entry) => entry({
        type: 'click', button: 0, target: card, clientX: 5, clientY: 5,
    }));
};
const clickDropZone = (laneValue) => {
    const zone = system.dropZones.get(laneValue)?.element;
    (zone?.eventHandlers['click'] ?? []).forEach((handler) => handler({
        type: 'click', button: 0, target: zone, currentTarget: zone,
        clientX: 5, clientY: 5,
        ctrlKey: false, altKey: false, metaKey: false, shiftKey: false,
        preventDefault() {}, stopPropagation() {},
    }));
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};

const state = () => system.keyboardSelection;
const activeIs = (element) => fakeDocument.activeElement === element;
const parsePlayPayload = (write) => {
    const nameValue = write.split(';', 1)[0];
    const equalsAt = nameValue.indexOf('=');
    return JSON.parse(decodeURIComponent(nameValue.slice(equalsAt + 1)));
};
const playCookieCardId = (write) => write.split(';', 1)[0].split('=')[0];

fakeDocument.activeElement = body;

assert('typing 1 selects the first hand card with a lane preview',
    pressKey('1') && state().selectedCard === handA && state().lanePreviewActive === true && activeIs(handA));
assert('Enter stages the typed selection in its default lane',
    pressKey('Enter') && handA.classList.contains('ghost') && system.staged.plays === 1 && cookieWrites.length === 1);
const typedPayload = parsePlayPayload(cookieWrites[0]);
assert('typed play keeps the 1-based dataset hand ordinal in the cookie',
    playCookieCardId(cookieWrites[0]) === '301' && typedPayload.laneValue === '1' &&
    typedPayload.sourceLane === '0' && typedPayload.sourceOrdinal === '1' &&
    typedPayload.flipFaceUp === false);
assert('the staged play cookie is scoped to the prefixed board path',
    cookieWrites[0].includes(';path=/MMM/game/1/board/1/'));
assert('typed staging kept the 1-based focused input', focusedHandCardInput.value === '1');

fakeDocument.activeElement = body;
clickCard(handC);
assert('mouse click selects the third hand card',
    state().selectedCard === handC && state().mouseSelecting === true && activeIs(handC));
assert('mouse selection hands the focused input the 1-based clicked ordinal',
    focusedHandCardInput.value === '3' && state().digitBuffer === '3');
assert('mouse selection stores the zero-based hand ordinal',
    state().sourceOrdinal === '2' && state().sourceLane === '0');
assert('the hand click alone stages nothing', cookieWrites.length === 1 && handC.classList.contains('ghost') === false);

clickDropZone(1);
assert('lane click stages the mouse play',
    handC.classList.contains('ghost') && handC.dataset.stagedLane === '1' &&
    system.staged.plays === 2 && cookieWrites.length === 2);
const mousePayload = parsePlayPayload(cookieWrites[1]);
assert('lane click after a hand click writes the zero-based hand ordinal',
    playCookieCardId(cookieWrites[1]) === '303' && mousePayload.laneValue === '1' &&
    mousePayload.sourceLane === '0' && mousePayload.sourceOrdinal === '2' &&
    mousePayload.flipFaceUp === false);
assert('staged mouse play clears the selection', state().selectedCard === null);

console.log('hand click then lane click ordinal flow ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping hand click lane click DOM test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping hand click lane click DOM test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'hand click then lane click ordinal harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('hand click then lane click ordinal flow ok', completed.stdout)

    def test_mouse_selection_creates_cursor_marker_and_tracks_mouse(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        self.assertIn('mousePreviewCursor', drag_js)
        self.assertIn('_updateMousePreviewCursor', drag_js)
        self.assertIn("addEventListener('mousemove'", drag_js)
        self.assertIn('_installMouseSelectionListeners', drag_js)
        self.assertIn('_teardownMouseSelectionListeners', drag_js)

    def test_dropzone_mouse_hover_creates_clone_for_mouse_selection(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        self.assertIn('onDropZoneMouseEnter(event, laneValue)', drag_js)
        self.assertIn('onDropZoneMouseLeave(event, laneValue)', drag_js)
        self.assertIn("addEventListener('mouseenter'", drag_js)
        self.assertIn("addEventListener('mouseleave'", drag_js)

        enter_start = drag_js.index('    onDropZoneMouseEnter(event, laneValue) {')
        enter_end = drag_js.index('    onDropZoneMouseLeave(event, laneValue) {')
        enter_body = drag_js[enter_start:enter_end]
        self.assertIn('state?.mouseSelecting', enter_body)
        self.assertIn('_buildPlayHologram', enter_body)
        self.assertIn('holoRow.appendChild(hologram)', enter_body)
        self.assertIn('lanePreviewActive = true', enter_body)

        leave_body = drag_js[enter_end:drag_js.index('    setupKeyboardSelection() {', enter_end)]
        self.assertIn('state?.mouseSelecting', leave_body)
        self.assertIn('state.hologram?.parentNode', leave_body)
        self.assertIn('lanePreviewActive = false', leave_body)

    def test_focus_arrow_target_returns_mouse_cursor_when_mouse_selecting(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        helper_start = drag_js.index('    _focusArrowTarget(card) {')
        parent_class_end = drag_js.index('    onFaceDownCardClick(e, laneValue) {')
        focus_target_helper = drag_js[helper_start:parent_class_end]
        self.assertIn('this.parent._mouseFocusTarget', focus_target_helper)
        self.assertIn('mousePreviewCursor', focus_target_helper)
        self.assertIn('this.state.mouseSelecting', focus_target_helper)

    def test_clear_keyboard_selection_removes_mouse_preview_cursor(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        helper_start = drag_js.index('    clearKeyboardSelection(opts) {')
        helper_end = drag_js.index('    cancelKeyboardSelection() {', helper_start)
        clear_helper = drag_js[helper_start:helper_end]
        self.assertIn('_teardownMouseSelectionListeners()', clear_helper)
        self.assertIn("getElementById('mousePreviewCursor')", clear_helper)

    def test_mouse_preview_cursor_css_uses_fixed_positioning(self):
        import os
        cards_css_path = os.path.join(
            os.path.dirname(__file__), '..', 'var', 'www', 'static', 'cards.css'
        )
        with open(cards_css_path) as css_file:
            cards_css = css_file.read()
        rule = re.search(r'\.mouse-preview-cursor\s*\{[^}]*\}', cards_css)
        self.assertIsNotNone(rule, "No .mouse-preview-cursor CSS rule found")
        body = rule.group(0)
        self.assertIn('position: fixed', body)
        self.assertIn('pointer-events: none', body)

    def test_focus_delegation_registers_capture_phase_on_player_screen(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        setup_keyboard = drag_js[
            drag_js.index('    setupKeyboardSelection() {'):
            drag_js.index('    _hasPlayerBoard() {')
        ]
        self.assertIn("document.querySelector('.playerScreen')", setup_keyboard)
        self.assertIn('this.focusDelegateHandler = (event) => {', setup_keyboard)
        self.assertIn(
            "const card = event.target.closest('.cardContainer');",
            setup_keyboard,
        )
        self.assertIn(
            "if (card.closest('.playerScreen ul.cardRow[title=\"trustedCards\"]')) return;",
            setup_keyboard,
        )
        self.assertIn(
            "this._keyboardSelectionControl.onFocusIn(card);",
            setup_keyboard,
        )
        self.assertIn(
            "this._keyboardSelectionControl.onFocusOut(card, event.relatedTarget);",
            setup_keyboard,
        )
        self.assertIn(
            "playerScreen.addEventListener('focusin', this.focusDelegateHandler, true);",
            setup_keyboard,
        )
        self.assertIn(
            "playerScreen.addEventListener('focusout', this.focusDelegateHandler, true);",
            setup_keyboard,
        )

    def test_focus_delegation_destruction_removes_capture_phase_listeners(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        destroy_block = drag_js[
            drag_js.index('    destroy() {'):
            drag_js.index('document.addEventListener(\'DOMContentLoaded\'')
        ]
        self.assertIn(
            "playerScreen.removeEventListener('focusin', this.focusDelegateHandler, true);",
            destroy_block,
        )
        self.assertIn(
            "playerScreen.removeEventListener('focusout', this.focusDelegateHandler, true);",
            destroy_block,
        )
        self.assertIn('this.focusDelegateHandler = null;', destroy_block)

    def test_keyboard_selection_control_focus_arrow_field_initialized_to_null(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]
        constructor_block = control_class[
            control_class.index('constructor({'):control_class.index('    _emptyKeyboardSelection() {')
        ]
        self.assertIn('this._focusArrow = null;', constructor_block)

    def test_keyboard_selection_control_on_focus_in_creates_arrow_through_parent(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]
        on_focus_in = control_class[
            control_class.index('    onFocusIn(card) {'):
            control_class.index('    onFocusOut(card, relatedTarget) {')
        ]
        self.assertIn('this.parent._focusArrowFlight(card)', on_focus_in)
        self.assertIn(
            'const target = flight.origin === card ? flight.target : flight.origin;',
            on_focus_in,
        )
        self.assertIn('this._focusArrow.source === card', on_focus_in)
        self.assertIn('this._focusArrow.target === target', on_focus_in)
        self.assertIn('this._focusArrow.arrow.remove()', on_focus_in)
        self.assertIn('this.parent._createFocusArrow(flight.origin, flight.target)', on_focus_in)
        self.assertIn('source: card', on_focus_in)
        self.assertIn('target,', on_focus_in)
        self.assertIn('arrow:', on_focus_in)

    def test_keyboard_selection_control_clears_focus_arrow_only_for_source(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]
        on_focus_out = control_class[
            control_class.index('    onFocusOut(card, relatedTarget) {'):
            control_class.index('    _clearFocusArrow(card) {')
        ]
        self.assertIn('this._clearFocusArrow(card);', on_focus_out)
        self.assertIn('if (relatedTarget === undefined) return;', on_focus_out)
        self.assertIn('this._clearSelectionStylingAfterFocusLoss(card, relatedTarget);', on_focus_out)

        clear_focus_arrow = control_class[
            control_class.index('    _clearFocusArrow(card) {'):
            control_class.index('    _restoreSelectionStylingOnFocus(card) {')
        ]
        self.assertIn('if (!this._focusArrow) return;', clear_focus_arrow)
        self.assertIn('if (this._focusArrow.source !== card) return;', clear_focus_arrow)
        self.assertIn('this._focusArrow.arrow.remove();', clear_focus_arrow)
        self.assertIn('this._focusArrow = null;', clear_focus_arrow)

    def test_focus_loss_clears_selection_styling_unless_staged_play(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]

        cleanup = control_class[
            control_class.index('    _clearSelectionStylingAfterFocusLoss(card, relatedTarget) {'):
            control_class.index('    _isWithinSelectionFocusRegion(selectedCard, element) {')
        ]
        self.assertIn('const selectedCard = this.state.selectedCard;', cleanup)
        self.assertIn('if (!selectedCard) return;', cleanup)
        self.assertIn('if (!this._isWithinSelectionFocusRegion(selectedCard, card)) return;', cleanup)
        self.assertIn('if (this._isWithinSelectionFocusRegion(selectedCard, relatedTarget)) return;', cleanup)
        self.assertIn('if (this._isPlayedToLane(selectedCard)) return;', cleanup)
        self.assertIn('this._clearSelectionStyling(selectedCard);', cleanup)

        region = control_class[
            control_class.index('    _isWithinSelectionFocusRegion(selectedCard, element) {'):
            control_class.index('    _isPlayedToLane(card) {')
        ]
        self.assertIn('if (!element) return false;', region)
        self.assertIn('if (element === selectedCard) return true;', region)
        self.assertIn('selectedCard.contains(element)', region)
        self.assertIn('this.parent._focusArrowTarget(selectedCard)', region)

        played = control_class[
            control_class.index('    _isPlayedToLane(card) {'):
            control_class.index('}\n', control_class.index('    _isPlayedToLane(card) {'))
        ]
        self.assertIn('this._stagedLaneForGhost_Legacy(card)', played)
        self.assertIn(
            '`.hologram[data-staged-for-card-id="${CSS.escape(cardId)}"]`',
            played,
        )

        restore = control_class[
            control_class.index('    _restoreSelectionStylingOnFocus(card) {'):
            control_class.index('    _clearSelectionStylingAfterFocusLoss(card, relatedTarget) {')
        ]
        self.assertIn('this.state.selectedCard !== card', restore)
        self.assertIn("card.setAttribute('aria-selected', 'true');", restore)

        on_focus_in = control_class[
            control_class.index('    onFocusIn(card) {'):
            control_class.index('    onFocusOut(card, relatedTarget) {')
        ]
        self.assertIn('this._restoreSelectionStylingOnFocus(card);', on_focus_in)

        clear_block = control_class[
            control_class.index('    clearKeyboardSelection({removePreview'):
            control_class.index('    navigate(direction, fromElement) {')
        ]
        self.assertIn('this._clearSelectionStyling(card);', clear_block)
        self.assertIn('card.contains(activeElement)', clear_block)

    def test_clear_keyboard_selection_resets_focus_arrow_before_state(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]
        clear_block = control_class[
            control_class.index('    clearKeyboardSelection({removePreview'):
            control_class.index('    navigate(direction, fromElement) {')
        ]
        self.assertIn('this._focusArrow.arrow.remove()', clear_block)
        self.assertIn('this._focusArrow = null', clear_block)
        focus_arrow_reset_index = clear_block.rindex('this._focusArrow = null')
        state_reset_index = clear_block.index('this.state = this._emptyKeyboardSelection()')
        self.assertLess(focus_arrow_reset_index, state_reset_index)

    def test_add_hover_arrow_keeps_mouseenter_mouseleave_and_drops_focus_listeners(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        arrow_helper = drag_js[
            drag_js.index('    _addHoverArrow(sourceEl, targetEl) {'):
            drag_js.index('    _createCurvedArrow')
        ]
        self.assertIn("addEventListener('mouseenter'", arrow_helper)
        self.assertIn("addEventListener('mouseleave'", arrow_helper)
        self.assertNotIn("addEventListener('focusin'", arrow_helper)
        self.assertNotIn("addEventListener('focusout'", arrow_helper)

    def test_focus_arrow_lifecycle_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness_parts = [
            'const makeElement = (tag) => ({',
            '    tagName: tag,',
            '    classList: { add() {}, remove() {}, contains() { return false; } },',
            '    children: [],',
            '    parentNode: null,',
            '    setAttribute() {},',
            '    removeAttribute() {},',
            '    appendChild(child) { this.children.push(child); child.parentNode = this; return child; },',
            '    remove() { this.removed = true; },',
            '    querySelector() { return null; },',
            '    querySelectorAll() { return []; },',
            '    addEventListener() {},',
            '    removeEventListener() {},',
            '    focus() {},',
            '    getBoundingClientRect() { return { left: 0, top: 0, width: 10, height: 10 }; },',
            '    contains() { return true; },',
            '});',
            '',
            'const fakePlayerBoard = makeElement("div");',
            'fakePlayerBoard.querySelectorAll = () => [];',
            'fakePlayerBoard.querySelector = () => null;',
            '',
            'const fakePlayerScreen = makeElement("div");',
            'const listeners = {};',
            'fakePlayerScreen.addEventListener = (event, handler, capture) => {',
            '    if (!listeners[event]) listeners[event] = [];',
            '    listeners[event].push({ handler, capture: !!capture });',
            '};',
            'fakePlayerScreen.removeEventListener = (event, handler, capture) => {',
            '    if (!listeners[event]) return;',
            '    listeners[event] = listeners[event].filter(',
            '        (entry) => entry.handler !== handler || entry.capture !== !!capture',
            '    );',
            '};',
            '',
            'const documentListeners = {};',
            'const fakeDocument = {',
            '    listeners: documentListeners,',
            '    documentElement: { contains: () => true },',
            '    querySelector(selector) {',
            "        if (selector === '.playerBoard') return fakePlayerBoard;",
            "        if (selector === '.playerScreen') return fakePlayerScreen;",
            "        if (selector === '.basic-mat.table > .deckHand.handContainer .hand-scroll') return makeElement(\"div\");",
            '        return null;',
            '    },',
            '    querySelectorAll() { return []; },',
            '    getElementById() { return null; },',
            '    createElement: (tag) => makeElement(tag),',
            '    createElementNS: () => makeElement("svg"),',
            '    addEventListener(event, handler, capture) {',
            '        if (!documentListeners[event]) documentListeners[event] = [];',
            '        documentListeners[event].push({ handler, capture: !!capture });',
            '    },',
            '    removeEventListener(event, handler, capture) {',
            '        if (!documentListeners[event]) return;',
            '        documentListeners[event] = documentListeners[event].filter(',
            '            (entry) => entry.handler !== handler || entry.capture !== !!capture',
            '        );',
            '    },',
            '    hidden: false,',
            '    visibilityState: "visible",',
            '    body: makeElement("body"),',
            '    activeElement: null,',
            '};',
            '',
            'const fakeWindow = { addEventListener() {}, removeEventListener() {}, cardDragDrop: null };',
            '',
            'global.document = fakeDocument;',
            'global.window = fakeWindow;',
            'global.MutationObserver = function(handler) { this.observe = () => {}; this.disconnect = () => {}; };',
            '',
            'const dragCode = ' + repr(drag_js) + ';',
            'eval(dragCode);',
            '',
            'const domReadyHandlers = documentListeners["DOMContentLoaded"] || [];',
            'if (domReadyHandlers.length === 0) throw new Error("DOMContentLoaded handler missing");',
            'domReadyHandlers.forEach((entry) => entry.handler());',
            '',
            'const system = global.window.cardDragDrop;',
            'if (!system) throw new Error("cardDragDrop not instantiated");',
            '',
            'const arrowCreated = [];',
            'system._createCurvedArrow = function(source, target) {',
            '    arrowCreated.push({ source, target });',
            '    return makeElement("svg");',
            '};',
            'system._createFocusArrow = function(source, target) {',
            '    const arrow = system._createCurvedArrow(source, target);',
            '    fakeDocument.body.appendChild(arrow);',
            '    source.classList.add("hover");',
            '    target.classList.add("hover");',
            '    return arrow;',
            '};',
            '',
            'const fakeTarget = makeElement("div");',
            'system._focusArrowTarget = () => fakeTarget;',
            '',
            'const fakeCard = makeElement("li");',
            'fakeCard.closest = (selector) => {',
            "    if (selector === '.cardContainer') return fakeCard;",
            "    if (selector === '.playerScreen') return fakePlayerScreen;",
            "    if (selector === '.playerScreen ul.cardRow[title=\"trustedCards\"]') return null;",
            '    return null;',
            '};',
            '',
            'const focusinEntries = listeners["focusin"] || [];',
            'const focusoutEntries = listeners["focusout"] || [];',
            'if (focusinEntries.length === 0) throw new Error("focus delegation not registered");',
            'if (focusinEntries.some((entry) => entry.capture !== true)) throw new Error("focus delegation missing capture phase");',
            '',
            'focusinEntries.forEach((entry) => entry.handler({ type: "focusin", target: fakeCard }));',
            'focusinEntries.forEach((entry) => entry.handler({ type: "focusin", target: fakeCard }));',
            'if (arrowCreated.length !== 1) throw new Error("expected exactly one arrow after duplicate focus, got " + arrowCreated.length);',
            '',
            'focusoutEntries.forEach((entry) => entry.handler({ type: "focusout", target: fakeCard }));',
            'if (system._keyboardSelectionControl._focusArrow !== null) throw new Error("focus arrow should be cleared on focusout");',
            '',
            'focusinEntries.forEach((entry) => entry.handler({ type: "focusin", target: fakeCard }));',
            'if (arrowCreated.length !== 2) throw new Error("expected second arrow after fresh focus, got " + arrowCreated.length);',
            '',
            'focusoutEntries.forEach((entry) => entry.handler({ type: "focusout", target: { closest: () => null } }));',
            'if (arrowCreated.length !== 2) throw new Error("focusout on non-matching source should not affect arrow count");',
            '',
            'system.destroy();',
            'if (listeners["focusin"] && listeners["focusin"].length > 0) throw new Error("destroy did not remove focusin listener");',
            'if (listeners["focusout"] && listeners["focusout"].length > 0) throw new Error("destroy did not remove focusout listener");',
            '',
            'console.log("focus-arrow lifecycle ok");',
            '',
        ]
        harness = '\n'.join(harness_parts)

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping focus-arrow lifecycle test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping focus-arrow lifecycle test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'focus arrow lifecycle harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('focus-arrow lifecycle ok', completed.stdout)

    def test_move_keyboard_selection_refreshes_focus_arrow(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        control_class_start = drag_js.index('class KeyboardSelectionControl {')
        control_class_end = drag_js.index('class CardDragDropSystem {')
        control_class = drag_js[control_class_start:control_class_end]

        move_start = control_class.index('    moveKeyboardSelection(laneValue) {')
        helper_start = control_class.index('    _refreshFocusArrowAfterLaneMove(card) {')
        move_body = control_class[move_start:helper_start]
        self.assertIn('this._refreshFocusArrowAfterLaneMove(selection.selectedCard);', move_body)
        self.assertLess(
            move_body.index('selection.currentLane = parsedLane;'),
            move_body.index('this._refreshFocusArrowAfterLaneMove(selection.selectedCard);'),
        )
        self.assertIn('selection.hologram.remove()', move_body)
        self.assertNotIn('onFocusIn(', move_body)
        self.assertNotIn('onFocusOut(', move_body)

        helper_end = control_class.index('    confirmKeyboardSelection(laneValue = null) {')
        helper_body = control_class[helper_start:helper_end]
        self.assertIn('if (!this._focusArrow || this._focusArrow.source !== card) return;', helper_body)
        self.assertIn('this.onFocusOut(card);', helper_body)
        self.assertIn('this.onFocusIn(card);', helper_body)

    def test_move_keyboard_selection_refreshes_focus_arrow_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = r'''
const makeElement = (tag) => {
    const classes = new Set();
    const attributes = new Map();
    const element = {
        tagName: tag,
        classes,
        attributes,
        children: [],
        parentNode: null,
        dataset: {},
        removed: false,
        style: {
            setProperty() {},
            getPropertyValue() { return ''; },
            removeProperty() {},
        },
        classList: {
            add: (...names) => names.forEach((name) => classes.add(name)),
            remove: (...names) => names.forEach((name) => classes.delete(name)),
            contains: (name) => classes.has(name),
        },
        setAttribute(name, value) { attributes.set(name, String(value)); },
        getAttribute(name) { return attributes.has(name) ? attributes.get(name) : null; },
        removeAttribute(name) { attributes.delete(name); },
        hasAttribute(name) { return attributes.has(name); },
        appendChild(child) { element.children.push(child); child.parentNode = element; return child; },
        remove() {
            if (element.parentNode) {
                const index = element.parentNode.children.indexOf(element);
                if (index !== -1) element.parentNode.children.splice(index, 1);
            }
            element.parentNode = null;
            element.removed = true;
        },
        closest(selector) {
            const tagMatch = selector.match(/^[a-zA-Z]+/);
            const wantedClasses = (selector.match(/\.([a-zA-Z-]+)/g) || []).map((cls) => cls.slice(1));
            let node = element;
            while (node) {
                const tagOk = !tagMatch || node.tagName.toLowerCase() === tagMatch[0].toLowerCase();
                const classesOk = wantedClasses.every(
                    (name) => node.classList && node.classList.contains(name)
                );
                if (tagOk && classesOk) return node;
                node = node.parentNode;
            }
            return null;
        },
        querySelector(selector) {
            if (!selector.startsWith('.')) return null;
            const wanted = selector.slice(1).trim();
            const stack = [...element.children];
            while (stack.length) {
                const node = stack.shift();
                if (node.classList && node.classList.contains(wanted)) return node;
                stack.push(...node.children);
            }
            return null;
        },
        querySelectorAll(selector) {
            const wanted = selector.split(',').map((part) => part.trim().split('[')[0]);
            const results = [];
            const stack = [...element.children];
            while (stack.length) {
                const node = stack.shift();
                if (wanted.some((w) => w === node.tagName ||
                    (w.startsWith('.') && node.classList.contains(w.slice(1))))) results.push(node);
                stack.push(...node.children);
            }
            return results;
        },
        addEventListener() {},
        removeEventListener() {},
        focus() {},
        getBoundingClientRect() { return { left: 0, top: 0, width: 10, height: 10 }; },
        contains() { return true; },
        cloneNode(deep) {
            const clone = makeElement(element.tagName);
            classes.forEach((name) => clone.classList.add(name));
            attributes.forEach((value, name) => clone.setAttribute(name, value));
            Object.assign(clone.dataset, element.dataset);
            if (deep) element.children.forEach((child) => clone.appendChild(child.cloneNode(true)));
            return clone;
        },
    };
    return element;
};

const fakePlayerBoard = makeElement('div');
const fakePlayerScreen = makeElement('div');
const listeners = {};
fakePlayerScreen.addEventListener = (event, handler, capture) => {
    if (!listeners[event]) listeners[event] = [];
    listeners[event].push({ handler, capture: !!capture });
};
fakePlayerScreen.removeEventListener = (event, handler, capture) => {
    if (!listeners[event]) return;
    listeners[event] = listeners[event].filter(
        (entry) => entry.handler !== handler || entry.capture !== !!capture
    );
};

const lanes = [1, 2, 3, 4].map(() => {
    const lane = makeElement('li');
    lane.classList.add('lane');
    return lane;
});
const holoRows = lanes.map((lane) => {
    const row = makeElement('ul');
    row.classList.add('hologramRow');
    lane.appendChild(row);
    return row;
});
fakePlayerBoard.querySelectorAll = (selector) => {
    if (selector === ':scope > ul.lanes > li.lane') return lanes;
    return [];
};

const handCard = makeElement('li');
handCard.classList.add('cardContainer');
handCard.setAttribute('draggable', 'true');
handCard.dataset.cardLane = '1';
const cardIdInput = makeElement('input');
cardIdInput.type = 'hidden';
cardIdInput.value = '101';
handCard.appendChild(cardIdInput);
handCard.closest = (selector) => {
    if (selector === '.cardContainer') return handCard;
    if (selector === '.playerScreen .deckHand') return makeElement('div');
    return null;
};
handCard.matches = (selector) => selector === 'li.cardContainer';

const documentListeners = {};
const fakeDocument = {
    listeners: documentListeners,
    documentElement: { contains: () => true },
    querySelector(selector) {
        if (selector === '.playerBoard') return fakePlayerBoard;
        if (selector === '.playerScreen') return fakePlayerScreen;
        if (selector === '.basic-mat.table > .deckHand.handContainer .hand-scroll') return makeElement('div');
        const sourceMatch = selector.match(/data-source-card-id="([^"]+)"/);
        if (sourceMatch) {
            const holograms = holoRows.flatMap((row) => row.children);
            return holograms.find((holo) =>
                holo.classList.contains('keyboard-preview') &&
                holo.dataset.keyboardPreview === 'true' &&
                holo.dataset.sourceCardId === sourceMatch[1]
            ) || null;
        }
        return null;
    },
    querySelectorAll(selector) {
        if (selector.includes('li.cardContainer')) return [handCard];
        return [];
    },
    getElementById() { return null; },
    createElement: (tag) => makeElement(tag),
    createElementNS: () => makeElement('svg'),
    addEventListener(event, handler, capture) {
        if (!documentListeners[event]) documentListeners[event] = [];
        documentListeners[event].push({ handler, capture: !!capture });
    },
    removeEventListener(event, handler, capture) {
        if (!documentListeners[event]) return;
        documentListeners[event] = documentListeners[event].filter(
            (entry) => entry.handler !== handler || entry.capture !== !!capture
        );
    },
    hidden: false,
    visibilityState: 'visible',
    body: makeElement('body'),
    activeElement: null,
};

const fakeWindow = { addEventListener() {}, removeEventListener() {}, cardDragDrop: null };

global.document = fakeDocument;
global.window = fakeWindow;
global.CSS = { escape: (value) => String(value).replace(/"/g, '\\"') };
global.MutationObserver = function (handler) { this.observe = () => {}; this.disconnect = () => {}; };

const dragCode = __DRAG_JS__;
eval(dragCode);

const domReadyHandlers = documentListeners['DOMContentLoaded'] || [];
if (domReadyHandlers.length === 0) throw new Error('DOMContentLoaded handler missing');
domReadyHandlers.forEach((entry) => entry.handler());

const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const arrowTargets = [];
const realCreateCurvedArrow = system._createCurvedArrow.bind(system);
system._createCurvedArrow = (source, target) => {
    arrowTargets.push(target);
    return realCreateCurvedArrow(source, target);
};

const bodyArrows = () => fakeDocument.body.children.filter(
    (child) => child.classList && child.classList.contains('hologram-arrow')
);

const pressKey = (key) => {
    let prevented = false;
    const event = { key, repeat: false, target: handCard, preventDefault() { prevented = true; } };
    (documentListeners['keydown'] || []).forEach((entry) => entry.handler(event));
    return prevented;
};

const fireFocusIn = () => {
    (listeners['focusin'] || []).forEach((entry) => entry.handler({ type: 'focusin', target: handCard }));
};

if (!pressKey('1')) throw new Error('digit selection did not preventDefault');
const selection = system.keyboardSelection;
if (!selection.selectedCard) throw new Error('digit did not select hand card');
if (selection.currentLane !== 1) throw new Error('typed selection landed in lane ' + selection.currentLane);
const oldHologram = selection.hologram;
if (oldHologram.parentNode !== holoRows[0]) throw new Error('hologram not appended to lane 1 row');

fireFocusIn();
if (arrowTargets.length !== 1) throw new Error('expected 1 arrow after focus, got ' + arrowTargets.length);
const initialClone = oldHologram.querySelector('.cardContainer');
if (arrowTargets[0] !== initialClone) throw new Error('initial arrow does not target the clone');
if (bodyArrows().length !== 1) throw new Error('expected exactly 1 arrow svg after focus');
if (!initialClone.classList.contains('hover')) throw new Error('clone missing hover class');

if (!pressKey('ArrowRight')) throw new Error('arrow lane move did not preventDefault');
if (system.keyboardSelection.currentLane !== 2) {
    throw new Error('expected lane 2 after ArrowRight, got ' + system.keyboardSelection.currentLane);
}
let newHologram = system.keyboardSelection.hologram;
if (newHologram === oldHologram) throw new Error('lane move did not rebuild the hologram');
if (newHologram.parentNode !== holoRows[1]) throw new Error('new hologram not in lane 2 row');
if (oldHologram.parentNode !== null || !oldHologram.removed) throw new Error('old hologram still attached');

if (arrowTargets.length !== 2) throw new Error('expected 2 arrows after lane move, got ' + arrowTargets.length);
let newClone = newHologram.querySelector('.cardContainer');
if (arrowTargets[1] !== newClone) throw new Error('refreshed arrow does not target the new clone');
if (system._keyboardSelectionControl._focusArrow.target !== newClone) {
    throw new Error('stored arrow target is not the current clone');
}
if (system._keyboardSelectionControl._focusArrow.source !== handCard) {
    throw new Error('stored arrow source is not the selected hand card');
}
if (bodyArrows().length !== 1) {
    throw new Error('expected exactly 1 arrow svg after lane move, got ' + bodyArrows().length);
}
if (!newClone.classList.contains('hover')) throw new Error('new clone missing hover class');

if (!pressKey('ArrowDown')) throw new Error('second lane move did not preventDefault');
if (system.keyboardSelection.currentLane !== 3) {
    throw new Error('expected lane 3 after ArrowDown, got ' + system.keyboardSelection.currentLane);
}
newHologram = system.keyboardSelection.hologram;
if (newHologram.parentNode !== holoRows[2]) throw new Error('second hologram not in lane 3 row');
if (arrowTargets.length !== 3) throw new Error('expected 3 arrows after second move, got ' + arrowTargets.length);
newClone = newHologram.querySelector('.cardContainer');
if (system._keyboardSelectionControl._focusArrow.target !== newClone) {
    throw new Error('stored arrow target did not follow the second lane move');
}
if (bodyArrows().length !== 1) {
    throw new Error('expected exactly 1 arrow svg after second lane move, got ' + bodyArrows().length);
}

system.destroy();
if (bodyArrows().length !== 0) throw new Error('destroy left an arrow svg in the body');

console.log('move-keyboard-selection arrow refresh ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping keyboard lane-move arrow test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping keyboard lane-move arrow test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'keyboard lane-move arrow harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('move-keyboard-selection arrow refresh ok', completed.stdout)

    def test_keyboard_flow_after_escape_cancellation_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = r'''
const matchPart = (el, part) => {
    if (!el || !el.tagName) return false;
    const tagMatch = part.match(/^[a-zA-Z][\w-]*/);
    if (tagMatch && el.tagName.toLowerCase() !== tagMatch[0].toLowerCase()) return false;
    const idMatch = part.match(/#([\w-]+)/);
    if (idMatch && (el.id || '') !== idMatch[1]) return false;
    for (const cls of part.match(/\.([\w-]+)/g) || []) {
        if (!el.classList || !el.classList.contains(cls.slice(1))) return false;
    }
    const attrRe = /\[([\w-]+)(?:="([^"]*)")?\]/g;
    let match;
    while ((match = attrRe.exec(part))) {
        const value = el.getAttribute ? el.getAttribute(match[1]) : null;
        if (match[2] === undefined) {
            if (value === null) return false;
        } else if (String(value) !== match[2]) return false;
    }
    const notRe = /:not\(\.([\w-]+)\)/g;
    while ((match = notRe.exec(part))) {
        if (el.classList && el.classList.contains(match[1])) return false;
    }
    if (part.replace(/:not\([^)]*\)/g, '').includes(':')) return false;
    return true;
};

const matchChainFrom = (el, tokens) => {
    const last = tokens[tokens.length - 1];
    if (!matchPart(el, last.part)) return false;
    if (tokens.length === 1) return true;
    const rest = tokens.slice(0, -1);
    if (last.combinator === '>') {
        return Boolean(el.parentNode) && matchChainFrom(el.parentNode, rest);
    }
    let node = el.parentNode;
    while (node) {
        if (matchChainFrom(node, rest)) return true;
        node = node.parentNode;
    }
    return false;
};

const tokenizeChain = (chain) => {
    const tokens = [];
    const re = /(\s*>\s*|\s+)?([^>\s]+)/g;
    let match;
    while ((match = re.exec(chain)) !== null) {
        let combinator = null;
        if (match[1] && match[1].includes('>')) combinator = '>';
        else if (match[1] && match[1].trim() !== '') combinator = ' ';
        tokens.push({ part: match[2], combinator });
    }
    if (tokens.length > 0 && tokens[0].part === ':scope') {
        const [head, ...rest] = tokens;
        rest[0].combinator = '>';
        return rest;
    }
    return tokens;
};

const descendantsInOrder = (root) => {
    const result = [];
    const stack = [...root.children];
    while (stack.length) {
        const node = stack.shift();
        result.push(node);
        stack.unshift(...node.children);
    }
    return result;
};

class FakeElement {
    constructor(tag, className = '') {
        this.tagName = String(tag).toUpperCase();
        this.classes = new Set(String(className).split(/\s+/).filter(Boolean));
        this.attributes = new Map();
        this.dataset = {};
        this.children = [];
        this.parentNode = null;
        this.removed = false;
        this.id = '';
        this.title = '';
        this.eventHandlers = {};
        this.classList = {
            add: (...names) => names.forEach((name) => this.classes.add(name)),
            remove: (...names) => names.forEach((name) => this.classes.delete(name)),
            contains: (name) => this.classes.has(name),
            toggle: (name) => {
                if (this.classes.has(name)) this.classes.delete(name);
                else this.classes.add(name);
            },
        };
        this.style = {
            setProperty: () => {},
            getPropertyValue: () => '',
            getPropertyPriority: () => '',
            removeProperty: () => {},
        };
        this.getBoundingClientRect = () => ({ left: 0, top: 0, width: 10, height: 10 });
    }

    matches(selector) {
        return String(selector).split(',').some((part) => part.trim() &&
            matchChainFrom(this, tokenizeChain(part.trim())));
    }

    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches(selector)) return node;
            node = node.parentNode;
        }
        return null;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] ?? null;
    }

    querySelectorAll(selector) {
        const alternatives = String(selector).split(',').map(
            (part) => tokenizeChain(part.trim()),
        );
        return descendantsInOrder(this).filter((candidate) =>
            alternatives.some((tokens) => matchChainFrom(candidate, tokens)));
    }

    appendChild(child) {
        this.children.push(child);
        child.parentNode = this;
        return child;
    }

    insertBefore(newNode, reference) {
        let index = reference ? this.children.indexOf(reference) : this.children.length;
        if (index === -1) index = this.children.length;
        this.children.splice(index, 0, newNode);
        newNode.parentNode = this;
        return newNode;
    }

    get firstChild() {
        return this.children[0] ?? null;
    }

    contains(other) {
        let node = other;
        while (node) {
            if (node === this) return true;
            node = node.parentNode;
        }
        return false;
    }

    remove() {
        if (this.parentNode) {
            const index = this.parentNode.children.indexOf(this);
            if (index !== -1) this.parentNode.children.splice(index, 1);
        }
        this.parentNode = null;
        this.removed = true;
    }

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
        if (name === 'id') this.id = String(value);
        if (/^[a-zA-Z][\w-]*$/.test(name)) this[name] = String(value);
        if (name === 'hidden') this.hidden = true;
    }

    getAttribute(name) {
        return this.attributes.has(name) ? this.attributes.get(name) : null;
    }

    removeAttribute(name) {
        this.attributes.delete(name);
    }

    hasAttribute(name) {
        return this.attributes.has(name);
    }

    addEventListener(name, handler) {
        (this.eventHandlers[name] ??= []).push(handler);
    }

    removeEventListener(name, handler) {
        this.eventHandlers[name] = (this.eventHandlers[name] ?? []).filter((h) => h !== handler);
    }

    cloneNode(deep) {
        const clone = new FakeElement(this.tagName, [...this.classes].join(' '));
        this.attributes.forEach((value, name) => clone.setAttribute(name, value));
        if (this.id) clone.id = this.id;
        Object.assign(clone.dataset, this.dataset);
        if (deep) this.children.forEach((child) => clone.appendChild(child.cloneNode(true)));
        return clone;
    }
}

const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const matTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(matTable);
const playerBoard = new FakeElement('div', 'playerBoard');
matTable.appendChild(playerBoard);

const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const holoRows = [];
const fieldCards = [];
 ['', '', '', ''].forEach((unused, laneIndex) => {
    const lane = new FakeElement('li', 'lane');
    lane.classList.add(['Intelligence', 'Speed', 'Visciousness', 'Resolve'][laneIndex]);
    lanesEl.appendChild(lane);
    const fieldCard = new FakeElement('li', 'cardContainer');
    fieldCard.setAttribute('tabindex', '0');
    fieldCard.dataset.cardLane = String(laneIndex + 1);
    const fieldId = new FakeElement('input');
    fieldId.setAttribute('type', 'hidden');
    fieldId.setAttribute('name', 'card_id');
    fieldId.setAttribute('value', `500${laneIndex + 1}`);
    fieldCard.appendChild(fieldId);
    lane.appendChild(fieldCard);
    fieldCards.push(fieldCard);
    const holoRow = new FakeElement('ul', 'hologramRow');
    lane.appendChild(holoRow);
    holoRows.push(holoRow);
});

const deckHand = new FakeElement('div', 'deckHand handContainer');
matTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);

const makeHandCard = (cardId, lane) => {
    const card = new FakeElement('li', 'cardContainer');
    card.setAttribute('tabindex', '0');
    card.setAttribute('draggable', 'true');
    card.dataset.cardLane = String(lane);
    card.dataset.sourceLane = '0';
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', 'card_id');
    input.setAttribute('value', String(cardId));
    card.appendChild(input);
    handList.appendChild(card);
    return card;
};
const handA = makeHandCard(201, 2);
const handB = makeHandCard(202, 3);
const handC = makeHandCard(203, 1);
const handCards = [handA, handB, handC];

const endTurnForm = new FakeElement('form', 'cardActionForm end-turn');
playerScreen.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);
const focusedHandCardInput = new FakeElement('input');
focusedHandCardInput.setAttribute('type', 'hidden');
focusedHandCardInput.setAttribute('name', 'focused_hand_card');
focusedHandCardInput.setAttribute('value', '1');
endTurnForm.appendChild(focusedHandCardInput);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) {
        return body.querySelector(selector);
    },
    querySelectorAll(selector) {
        return body.querySelectorAll(selector);
    },
    getElementById(id) {
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) {
        (documentListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};
const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
};
fakeDocument.getElementById = (id) => {
    if (id === 'turnLimits') return turnLimits;
    for (const el of descendantsInOrder(body)) {
        if (el.id === id) return el;
    }
    return null;
};

for (const el of [body, playerScreen, playerBoard, endTurnForm, endTurnButton, ...handCards, ...fieldCards, ...holoRows]) {
    el.focus = () => { fakeDocument.activeElement = el; };
    el.blur = () => { if (fakeDocument.activeElement === el) fakeDocument.activeElement = body; };
}

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/x/action' },
    setTimeout() { return 0; },
    clearTimeout() {},
};
global.CSS = { escape: (value) => String(value) };
global.MutationObserver = function (handler) {
    this.observe = () => {};
    this.disconnect = () => {};
};

const dragCode = __DRAG_JS__;
eval(dragCode);

(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const clickHandlers = documentListeners['click'] ?? [];

const pressKey = (key, options = {}) => {
    let prevented = false;
    const event = {
        key,
        repeat: options.repeat ?? false,
        target: options.target ?? fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const clickCard = (card) => {
    clickHandlers.forEach((entry) => entry({
        type: 'click', button: 0, target: card, clientX: 5, clientY: 5,
    }));
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};

const state = () => system.keyboardSelection;
const stagedClones = () => holoRows.flatMap((row) => row.children);
const activeIs = (element) => fakeDocument.activeElement === element;

fakeDocument.activeElement = body;

assert('typing digit 1 selects card A', pressKey('1') && state().selectedCard === handA && activeIs(handA));
assert('hand selection writes clone into lane 2 row', stagedClones().length === 1 && stagedClones()[0].parentNode === holoRows[1]);
assert('selection ordinal lands in hidden input', focusedHandCardInput.value === '1');
pressKey('0');
assert('cancel keeps focus but clears selection', state().selectedCard === null && activeIs(handA));
assert('ArrowUp focuses first field card', pressKey('ArrowUp') && activeIs(fieldCards[0]) && state().selectedCard === null);
assert('ArrowDown from field re-selects persisted hand slot', pressKey('ArrowDown') && state().selectedCard === handA && activeIs(handA));
assert('Escape clears selection and restores focus', pressKey('Escape') && state().selectedCard === null && state().digitBuffer === '' && activeIs(handA));
assert('clone removed after Escape', stagedClones().length === 0);
assert('Enter re-selects the focused hand card', pressKey('Enter') && state().selectedCard === handA);
assert('each selection keeps exactly one clone', stagedClones().length === 1);
assert('Escape again keeps focus', pressKey('Escape') && activeIs(handA));
assert('Space re-selects the focused hand card', pressKey(' ') && state().selectedCard === handA);
pressKey('Escape');
assert('ArrowRight cycles to the next hand card', pressKey('ArrowRight') && state().selectedCard === handB && activeIs(handB));
assert('cycling writes the playable ordinal to the hidden input', focusedHandCardInput.value === '2');
pressKey('Escape');
assert('ArrowLeft cycles back to the previous hand card', pressKey('ArrowLeft') && state().selectedCard === handA && activeIs(handA));
pressKey('Escape');
fakeDocument.activeElement = handC;
assert('ArrowRight from the last hand card focuses the end turn button', pressKey('ArrowRight') && activeIs(endTurnButton) && state().selectedCard === null);
fakeDocument.activeElement = handA;
pressKey('ArrowLeft');
assert('ArrowLeft from the first hand card selects no card without a draw button',
    state().selectedCard === null && activeIs(handA));
assert('ArrowUp from the hand focuses field cards again', pressKey('ArrowUp') && activeIs(fieldCards[0]) && state().selectedCard === null);
fakeDocument.activeElement = handA;
assert('ArrowDown from the hand focuses the end turn button', pressKey('ArrowDown') && activeIs(endTurnButton) && state().selectedCard === null);

clickCard(handA);
assert('mouse click selects card A', state().selectedCard === handA && activeIs(handA));
assert('Escape cancels the mouse selection and keeps focus',
    pressKey('Escape') && state().selectedCard === null && state().mouseSelecting === false && activeIs(handA));
assert('mouse preview cursor removed after Escape',
    fakeDocument.body.querySelectorAll('#mousePreviewCursor').length === 0);
assert('Enter re-selects after mouse Escape', pressKey('Enter') && state().selectedCard === handA);
pressKey('Escape');
assert('ArrowRight resumes the same cycle from the focused card',
    pressKey('ArrowRight') && state().selectedCard === handB);
pressKey('Escape');
fakeDocument.activeElement = endTurnButton;
pressKey('Enter');
assert('focus on the end turn button does not re-select a hand card via Enter', state().selectedCard === null);

console.log('keyboard flow after escape cancellation ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping keyboard flow DOM test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping keyboard flow DOM test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'keyboard flow after escape harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('keyboard flow after escape cancellation ok', completed.stdout)

    def test_reselection_after_escape_recreates_focus_arrow_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = r'''
const matchPart = (el, part) => {
    if (!el || !el.tagName) return false;
    const tagMatch = part.match(/^[a-zA-Z][\w-]*/);
    if (tagMatch && el.tagName.toLowerCase() !== tagMatch[0].toLowerCase()) return false;
    const idMatch = part.match(/#([\w-]+)/);
    if (idMatch && (el.id || '') !== idMatch[1]) return false;
    for (const cls of part.match(/\.([\w-]+)/g) || []) {
        if (!el.classList || !el.classList.contains(cls.slice(1))) return false;
    }
    const attrRe = /\[([\w-]+)(?:="([^"]*)")?\]/g;
    let match;
    while ((match = attrRe.exec(part))) {
        const value = el.getAttribute ? el.getAttribute(match[1]) : null;
        if (match[2] === undefined) {
            if (value === null) return false;
        } else if (String(value) !== match[2]) return false;
    }
    if (part.replace(/:not\([^)]*\)/g, '').includes(':')) return false;
    return true;
};

const matchChainFrom = (el, tokens) => {
    const last = tokens[tokens.length - 1];
    if (!matchPart(el, last.part)) return false;
    if (tokens.length === 1) return true;
    const rest = tokens.slice(0, -1);
    if (last.combinator === '>') {
        return Boolean(el.parentNode) && matchChainFrom(el.parentNode, rest);
    }
    let node = el.parentNode;
    while (node) {
        if (matchChainFrom(node, rest)) return true;
        node = node.parentNode;
    }
    return false;
};

const tokenizeChain = (chain) => {
    const tokens = [];
    const re = /(\s*>\s*|\s+)?([^>\s]+)/g;
    let match;
    while ((match = re.exec(chain)) !== null) {
        let combinator = null;
        if (match[1] && match[1].includes('>')) combinator = '>';
        else if (match[1] && match[1].trim() !== '') combinator = ' ';
        tokens.push({ part: match[2], combinator });
    }
    if (tokens.length > 0 && tokens[0].part === ':scope') {
        const [head, ...rest] = tokens;
        rest[0].combinator = '>';
        return rest;
    }
    return tokens;
};

const descendantsInOrder = (root) => {
    const result = [];
    const stack = [...root.children];
    while (stack.length) {
        const node = stack.shift();
        result.push(node);
        stack.unshift(...node.children);
    }
    return result;
};

const kebab = (prop) => String(prop).replace(/[A-Z]/g, (char) => '-' + char.toLowerCase());

class FakeElement {
    constructor(tag, className = '') {
        this.tagName = String(tag).toUpperCase();
        this.classes = new Set(String(className).split(/\s+/).filter(Boolean));
        this.attributes = new Map();
        this.children = [];
        this.parentNode = null;
        this.removed = false;
        this.id = '';
        this.title = '';
        this.eventHandlers = {};
        this.classList = {
            add: (...names) => names.forEach((name) => this.classes.add(name)),
            remove: (...names) => names.forEach((name) => this.classes.delete(name)),
            contains: (name) => this.classes.has(name),
            toggle: (name) => {
                if (this.classes.has(name)) this.classes.delete(name);
                else this.classes.add(name);
            },
        };
        this.style = {
            setProperty: () => {},
            getPropertyValue: () => '',
            getPropertyPriority: () => '',
            removeProperty: () => {},
        };
        this.getBoundingClientRect = () => ({ left: 0, top: 0, width: 10, height: 10 });
        const element = this;
        this.dataset = new Proxy({}, {
            set(target, prop, value) {
                element.setAttribute('data-' + kebab(prop), String(value));
                return true;
            },
            get(target, prop) {
                const value = element.getAttribute('data-' + kebab(prop));
                return value === null ? undefined : value;
            },
            has(target, prop) {
                return element.getAttribute('data-' + kebab(prop)) !== null;
            },
            deleteProperty(target, prop) {
                element.removeAttribute('data-' + kebab(prop));
                return true;
            },
        });
    }

    matches(selector) {
        return String(selector).split(',').some((part) => part.trim() &&
            matchChainFrom(this, tokenizeChain(part.trim())));
    }

    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches(selector)) return node;
            node = node.parentNode;
        }
        return null;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] ?? null;
    }

    querySelectorAll(selector) {
        const alternatives = String(selector).split(',').map(
            (part) => tokenizeChain(part.trim()),
        );
        return descendantsInOrder(this).filter((candidate) =>
            alternatives.some((tokens) => matchChainFrom(candidate, tokens)));
    }

    appendChild(child) {
        this.children.push(child);
        child.parentNode = this;
        return child;
    }

    get firstChild() {
        return this.children[0] ?? null;
    }

    contains(other) {
        let node = other;
        while (node) {
            if (node === this) return true;
            node = node.parentNode;
        }
        return false;
    }

    remove() {
        if (this.parentNode) {
            const index = this.parentNode.children.indexOf(this);
            if (index !== -1) this.parentNode.children.splice(index, 1);
        }
        this.parentNode = null;
        this.removed = true;
    }

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
        if (name === 'id') this.id = String(value);
        if (name === 'title') this.title = String(value);
        if (/^[a-zA-Z][\w-]*$/.test(name)) this[name] = String(value);
        if (name === 'hidden') this.hidden = true;
    }

    getAttribute(name) {
        return this.attributes.has(name) ? this.attributes.get(name) : null;
    }

    removeAttribute(name) {
        this.attributes.delete(name);
    }

    hasAttribute(name) {
        return this.attributes.has(name);
    }

    addEventListener(name, handler) {
        (this.eventHandlers[name] ??= []).push(handler);
    }

    removeEventListener(name, handler) {
        this.eventHandlers[name] = (this.eventHandlers[name] ?? []).filter((h) => h !== handler);
    }

    cloneNode(deep) {
        const clone = new FakeElement(this.tagName, [...this.classes].join(' '));
        this.attributes.forEach((value, name) => clone.setAttribute(name, value));
        if (this.id) clone.id = this.id;
        if (deep) this.children.forEach((child) => clone.appendChild(child.cloneNode(true)));
        return clone;
    }
}

class FakeSvgElement extends FakeElement {
    constructor() {
        super('svg');
        this.classList.add('hologram-arrow');
        this.children = [];
    }
}

const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const matTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(matTable);
const playerBoard = new FakeElement('div', 'playerBoard');
matTable.appendChild(playerBoard);

const screenFocusListeners = { focusin: [], focusout: [] };
playerScreen.addEventListener = (name, handler, capture) => {
    if (name === 'focusin' || name === 'focusout') {
        screenFocusListeners[name].push({ handler, capture: !!capture });
        return;
    }
    (playerScreen.eventHandlers[name] ??= []).push(handler);
};
playerScreen.removeEventListener = (name, handler, capture) => {
    if (name === 'focusin' || name === 'focusout') {
        screenFocusListeners[name] = screenFocusListeners[name].filter(
            (entry) => entry.handler !== handler || entry.capture !== !!capture);
        return;
    }
    playerScreen.eventHandlers[name] = (playerScreen.eventHandlers[name] ?? [])
        .filter((h) => h !== handler);
};

const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const holoRows = [];
 ['', '', '', ''].forEach((unused, laneIndex) => {
    const lane = new FakeElement('li', 'lane');
    lane.classList.add(['Intelligence', 'Speed', 'Visciousness', 'Resolve'][laneIndex]);
    lanesEl.appendChild(lane);
    const holoRow = new FakeElement('ul', 'hologramRow');
    lane.appendChild(holoRow);
    holoRows.push(holoRow);
});

const deckHand = new FakeElement('div', 'deckHand handContainer');
matTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);

const makeHandCard = (cardId, lane) => {
    const card = new FakeElement('li', 'cardContainer');
    card.setAttribute('tabindex', '0');
    card.setAttribute('draggable', 'true');
    card.dataset.cardLane = String(lane);
    card.dataset.sourceLane = '0';
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', 'card_id');
    input.setAttribute('value', String(cardId));
    card.appendChild(input);
    handList.appendChild(card);
    return card;
};
const handA = makeHandCard(201, 2);
const handB = makeHandCard(202, 3);
const handCards = [handA, handB];

const endTurnForm = new FakeElement('form', 'cardActionForm end-turn');
playerScreen.appendChild(endTurnForm);
const focusedHandCardInput = new FakeElement('input');
focusedHandCardInput.setAttribute('type', 'hidden');
focusedHandCardInput.setAttribute('name', 'focused_hand_card');
focusedHandCardInput.setAttribute('value', '1');
endTurnForm.appendChild(focusedHandCardInput);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) {
        return body.querySelector(selector);
    },
    querySelectorAll(selector) {
        return body.querySelectorAll(selector);
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeSvgElement(),
    addEventListener(event, handler) {
        (documentListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};
const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
};
fakeDocument.getElementById = (id) => {
    if (id === 'turnLimits') return turnLimits;
    for (const el of descendantsInOrder(body)) {
        if (el.id === id) return el;
    }
    return null;
};

const fireFocusEvent = (type, target, relatedTarget = null) => {
    const event = { type, target, relatedTarget };
    [...screenFocusListeners[type]].forEach((entry) => entry.handler(event));
};

const wireFocus = (el) => {
    el.focus = () => {
        const previous = fakeDocument.activeElement;
        if (previous === el) return;
        if (previous && typeof previous.blur === 'function') previous.blur();
        fakeDocument.activeElement = el;
        fireFocusEvent('focusin', el, previous);
    };
    el.blur = () => {
        if (fakeDocument.activeElement !== el) return;
        fireFocusEvent('focusout', el, null);
        fakeDocument.activeElement = body;
    };
};

for (const el of [body, playerScreen, playerBoard, endTurnForm, ...handCards]) {
    wireFocus(el);
}

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/x/action' },
    setTimeout() { return 0; },
    clearTimeout() {},
};
global.CSS = { escape: (value) => String(value) };
global.MutationObserver = function () {
    this.observe = () => {};
    this.disconnect = () => {};
};

const dragCode = __DRAG_JS__;
eval(dragCode);

(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const pressKey = (key) => {
    let prevented = false;
    keyboardHandlers.forEach((entry) => entry({
        key, repeat: false, target: fakeDocument.activeElement,
        ctrlKey: false, altKey: false, metaKey: false, shiftKey: false,
        preventDefault() { prevented = true; },
    }));
    return prevented;
};

const assert = (label, condition, extra = '') => {
    if (!condition) throw new Error('FAILED: ' + label + ' | ' + extra);
    console.log('ok: ' + label);
};

const state = () => system.keyboardSelection;
const arrows = () => fakeDocument.body.children.filter(
    (child) => child.classList && child.classList.contains('hologram-arrow'));
const activeIs = (element) => fakeDocument.activeElement === element;
const previewCloneFor = (card) => {
    const row = holoRows[Number(card.dataset.cardLane) - 1];
    return row.querySelector('.hologram')?.querySelector('.cardContainer') ?? null;
};
const currentFocusArrow = () => system._keyboardSelectionControl._focusArrow;

fakeDocument.activeElement = body;

pressKey('1');
assert('typing digit 1 selects card A', state().selectedCard === handA);
const firstClone = previewCloneFor(handA);
assert('first selection marks the hand card selected',
    handA.classes.has('keyboard-selected') && handA.dataset.keyboardSelected === 'true');
assert('first selection leaves exactly one arrow on the lane clone',
    arrows().length === 1 && currentFocusArrow() !== null &&
    currentFocusArrow().source === handA &&
    currentFocusArrow().target === firstClone &&
    currentFocusArrow().target.parentNode !== null,
    `arrows=${arrows().length}`);

pressKey('Escape');
assert('Escape cancels selection and keeps focus on the hand card',
    state().selectedCard === null && state().digitBuffer === '' && activeIs(handA));
assert('Escape removes the preview clone', previewCloneFor(handA) === null);
assert('Escape removes the arrow svg', arrows().length === 0, `arrows=${arrows().length}`);

pressKey('1');
assert('typing digit 1 again reselects card A', state().selectedCard === handA && activeIs(handA));
assert('selection styling is reapplied on reselect',
    handA.classes.has('keyboard-selected') && handA.dataset.keyboardSelected === 'true');
const secondClone = previewCloneFor(handA);
assert('reselect rebuilt a fresh clone after Escape', secondClone !== null && secondClone !== firstClone);
assert('reselect after Escape leaves exactly one arrow svg',
    arrows().length === 1, `arrows=${arrows().length}`);
assert('reselect arrow targets the current lane clone',
    currentFocusArrow() !== null && currentFocusArrow().source === handA &&
    currentFocusArrow().target === secondClone &&
    system._focusArrowTarget(handA) === secondClone &&
    secondClone.parentNode !== null &&
    secondClone.parentNode.parentNode !== null,
    'arrow missing or targeting a detached clone');
const isConnectedToBody = (element) => {
    let node = element;
    while (node) {
        if (node === fakeDocument.body) return true;
        node = node.parentNode;
    }
    return false;
};
assert('detached first clone never holds the arrow',
    currentFocusArrow().target !== firstClone && !isConnectedToBody(firstClone));

pressKey('0');
assert('zero cancel also keeps focus on the hand card',
    state().selectedCard === null && activeIs(handA));
pressKey('1');
assert('reselect after zero cancel refreshed the arrow against the new clone',
    state().selectedCard === handA && arrows().length === 1 &&
    currentFocusArrow().target === previewCloneFor(handA) &&
    currentFocusArrow().target !== secondClone,
    `arrows=${arrows().length}`);

pressKey('Escape');
pressKey('2');
assert('reselecting a different card after Escape keeps exactly one arrow on its clone',
    state().selectedCard === handB && activeIs(handB) && arrows().length === 1 &&
    currentFocusArrow().source === handB &&
    currentFocusArrow().target === previewCloneFor(handB),
    `arrows=${arrows().length}`);

console.log('reselection focus arrow after escape ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping reselection arrow DOM test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping reselection arrow DOM test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'reselection focus arrow harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('reselection focus arrow after escape ok', completed.stdout)

    def test_hand_arrow_boundaries_focus_draw_and_end_turn_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = r'''
const matchPart = (el, part) => {
    if (!el || !el.tagName) return false;
    const tagMatch = part.match(/^[a-zA-Z][\w-]*/);
    if (tagMatch && el.tagName.toLowerCase() !== tagMatch[0].toLowerCase()) return false;
    const idMatch = part.match(/#([\w-]+)/);
    if (idMatch && (el.id || '') !== idMatch[1]) return false;
    for (const cls of part.match(/\.([\w-]+)/g) || []) {
        if (!el.classList || !el.classList.contains(cls.slice(1))) return false;
    }
    const attrRe = /\[([\w-]+)(?:="([^"]*)")?\]/g;
    let match;
    while ((match = attrRe.exec(part))) {
        const value = el.getAttribute ? el.getAttribute(match[1]) : null;
        if (match[2] === undefined) {
            if (value === null) return false;
        } else if (String(value) !== match[2]) return false;
    }
    const notRe = /:not\(\.([\w-]+)\)/g;
    while ((match = notRe.exec(part))) {
        if (el.classList && el.classList.contains(match[1])) return false;
    }
    if (part.replace(/:not\([^)]*\)/g, '').includes(':')) return false;
    return true;
};

const matchChainFrom = (el, tokens) => {
    const last = tokens[tokens.length - 1];
    if (!matchPart(el, last.part)) return false;
    if (tokens.length === 1) return true;
    const rest = tokens.slice(0, -1);
    if (last.combinator === '>') {
        return Boolean(el.parentNode) && matchChainFrom(el.parentNode, rest);
    }
    let node = el.parentNode;
    while (node) {
        if (matchChainFrom(node, rest)) return true;
        node = node.parentNode;
    }
    return false;
};

const tokenizeChain = (chain) => {
    const tokens = [];
    const re = /(\s*>\s*|\s+)?([^>\s]+)/g;
    let match;
    while ((match = re.exec(chain)) !== null) {
        let combinator = null;
        if (match[1] && match[1].includes('>')) combinator = '>';
        else if (match[1] && match[1].trim() !== '') combinator = ' ';
        tokens.push({ part: match[2], combinator });
    }
    if (tokens.length > 0 && tokens[0].part === ':scope') {
        const [head, ...rest] = tokens;
        rest[0].combinator = '>';
        return rest;
    }
    return tokens;
};

const descendantsInOrder = (root) => {
    const result = [];
    const stack = [...root.children];
    while (stack.length) {
        const node = stack.shift();
        result.push(node);
        stack.unshift(...node.children);
    }
    return result;
};

class FakeElement {
    constructor(tag, className = '') {
        this.tagName = String(tag).toUpperCase();
        this.classes = new Set(String(className).split(/\s+/).filter(Boolean));
        this.attributes = new Map();
        this.dataset = {};
        this.children = [];
        this.parentNode = null;
        this.removed = false;
        this.id = '';
        this.title = '';
        this.eventHandlers = {};
        this.classList = {
            add: (...names) => names.forEach((name) => this.classes.add(name)),
            remove: (...names) => names.forEach((name) => this.classes.delete(name)),
            contains: (name) => this.classes.has(name),
            toggle: (name) => {
                if (this.classes.has(name)) this.classes.delete(name);
                else this.classes.add(name);
            },
        };
        this.style = {
            setProperty: () => {},
            getPropertyValue: () => '',
            getPropertyPriority: () => '',
            removeProperty: () => {},
        };
        this.getBoundingClientRect = () => ({ left: 0, top: 0, width: 10, height: 10 });
    }

    matches(selector) {
        return String(selector).split(',').some((part) => part.trim() &&
            matchChainFrom(this, tokenizeChain(part.trim())));
    }

    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches(selector)) return node;
            node = node.parentNode;
        }
        return null;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] ?? null;
    }

    querySelectorAll(selector) {
        const alternatives = String(selector).split(',').map(
            (part) => tokenizeChain(part.trim()),
        );
        return descendantsInOrder(this).filter((candidate) =>
            alternatives.some((tokens) => matchChainFrom(candidate, tokens)));
    }

    appendChild(child) {
        this.children.push(child);
        child.parentNode = this;
        return child;
    }

    insertBefore(newNode, reference) {
        let index = reference ? this.children.indexOf(reference) : this.children.length;
        if (index === -1) index = this.children.length;
        this.children.splice(index, 0, newNode);
        newNode.parentNode = this;
        return newNode;
    }

    get firstChild() {
        return this.children[0] ?? null;
    }

    contains(other) {
        let node = other;
        while (node) {
            if (node === this) return true;
            node = node.parentNode;
        }
        return false;
    }

    remove() {
        if (this.parentNode) {
            const index = this.parentNode.children.indexOf(this);
            if (index !== -1) this.parentNode.children.splice(index, 1);
        }
        this.parentNode = null;
        this.removed = true;
    }

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
        if (name === 'id') this.id = String(value);
        if (/^[a-zA-Z][\w-]*$/.test(name)) this[name] = String(value);
        if (name === 'hidden') this.hidden = true;
    }

    getAttribute(name) {
        return this.attributes.has(name) ? this.attributes.get(name) : null;
    }

    removeAttribute(name) {
        this.attributes.delete(name);
    }

    hasAttribute(name) {
        return this.attributes.has(name);
    }

    addEventListener(name, handler) {
        (this.eventHandlers[name] ??= []).push(handler);
    }

    removeEventListener(name, handler) {
        this.eventHandlers[name] = (this.eventHandlers[name] ?? []).filter((h) => h !== handler);
    }

    cloneNode(deep) {
        const clone = new FakeElement(this.tagName, [...this.classes].join(' '));
        this.attributes.forEach((value, name) => clone.setAttribute(name, value));
        if (this.id) clone.id = this.id;
        Object.assign(clone.dataset, this.dataset);
        if (deep) this.children.forEach((child) => clone.appendChild(child.cloneNode(true)));
        return clone;
    }
}

const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const matTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(matTable);
const playerBoard = new FakeElement('div', 'playerBoard');
matTable.appendChild(playerBoard);

const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const holoRows = [];
const fieldCards = [];
 ['', '', '', ''].forEach((unused, laneIndex) => {
    const lane = new FakeElement('li', 'lane');
    lane.classList.add(['Intelligence', 'Speed', 'Visciousness', 'Resolve'][laneIndex]);
    lanesEl.appendChild(lane);
    const fieldCard = new FakeElement('li', 'cardContainer');
    fieldCard.setAttribute('tabindex', '0');
    fieldCard.dataset.cardLane = String(laneIndex + 1);
    const fieldId = new FakeElement('input');
    fieldId.setAttribute('type', 'hidden');
    fieldId.setAttribute('name', 'card_id');
    fieldId.setAttribute('value', `500${laneIndex + 1}`);
    fieldCard.appendChild(fieldId);
    lane.appendChild(fieldCard);
    fieldCards.push(fieldCard);
    const holoRow = new FakeElement('ul', 'hologramRow');
    lane.appendChild(holoRow);
    holoRows.push(holoRow);
});

const deckHand = new FakeElement('div', 'deckHand handContainer');
matTable.appendChild(deckHand);
const deckStack = new FakeElement('div', 'deck-stack own-deck-stack');
playerBoard.appendChild(deckStack);
const activeDeck = new FakeElement('ul', 'deck active-deck');
deckStack.appendChild(activeDeck);
const drawForm = new FakeElement('form', 'cardActionForm');
activeDeck.appendChild(drawForm);
const drawActionInput = new FakeElement('input');
drawActionInput.setAttribute('type', 'hidden');
drawActionInput.setAttribute('name', 'action');
drawActionInput.setAttribute('value', 'draw');
drawForm.appendChild(drawActionInput);
const drawButton = new FakeElement('button', 'card back draw');
drawForm.appendChild(drawButton);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);

const makeHandCard = (cardId, lane) => {
    const card = new FakeElement('li', 'cardContainer');
    card.setAttribute('tabindex', '0');
    card.setAttribute('draggable', 'true');
    card.dataset.cardLane = String(lane);
    card.dataset.sourceLane = '0';
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', 'card_id');
    input.setAttribute('value', String(cardId));
    card.appendChild(input);
    handList.appendChild(card);
    return card;
};
const handA = makeHandCard(201, 2);
const handB = makeHandCard(202, 3);
const handC = makeHandCard(203, 1);
const handCards = [handA, handB, handC];

const endTurnForm = new FakeElement('form', 'cardActionForm end-turn');
playerScreen.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);
const focusedHandCardInput = new FakeElement('input');
focusedHandCardInput.setAttribute('type', 'hidden');
focusedHandCardInput.setAttribute('name', 'focused_hand_card');
focusedHandCardInput.setAttribute('value', '1');
endTurnForm.appendChild(focusedHandCardInput);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) {
        return body.querySelector(selector);
    },
    querySelectorAll(selector) {
        return body.querySelectorAll(selector);
    },
    getElementById(id) {
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) {
        (documentListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};
const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
};
fakeDocument.getElementById = (id) => {
    if (id === 'turnLimits') return turnLimits;
    for (const el of descendantsInOrder(body)) {
        if (el.id === id) return el;
    }
    return null;
};

for (const el of [
    body, playerScreen, playerBoard, endTurnForm, endTurnButton,
    drawForm, drawButton, activeDeck,
    ...handCards, ...fieldCards, ...holoRows,
]) {
    el.focus = () => { fakeDocument.activeElement = el; };
    el.blur = () => { if (fakeDocument.activeElement === el) fakeDocument.activeElement = body; };
}

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/x/action' },
    setTimeout() { return 0; },
    clearTimeout() {},
};
global.CSS = { escape: (value) => String(value) };
global.MutationObserver = function (handler) {
    this.observe = () => {};
    this.disconnect = () => {};
};

const dragCode = __DRAG_JS__;
eval(dragCode);

(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];

const pressKey = (key) => {
    let prevented = false;
    const event = {
        key,
        repeat: false,
        target: fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};

const state = () => system.keyboardSelection;
const stagedClones = () => holoRows.flatMap((row) => row.children);
const activeIs = (element) => fakeDocument.activeElement === element;

fakeDocument.activeElement = handA;
assert('ArrowLeft from the first hand card focuses the draw button',
    pressKey('ArrowLeft') && activeIs(drawButton) && state().selectedCard === null);
assert('boundary exit to the draw button writes no ordinal or preview',
    focusedHandCardInput.value === '1' && stagedClones().length === 0);

fakeDocument.activeElement = handA;
assert('ArrowRight from the first hand card still selects the next card',
    pressKey('ArrowRight') && state().selectedCard === handB && activeIs(handB));
assert('cycling still writes the playable ordinal', focusedHandCardInput.value === '2');
pressKey('Escape');
pressKey('Escape');
assert('ArrowLeft from the middle card selects the first hand card',
    pressKey('ArrowLeft') && state().selectedCard === handA && activeIs(handA));
pressKey('Escape');
assert('the first hand card exits left back to the draw button',
    pressKey('ArrowLeft') && activeIs(drawButton) && state().selectedCard === null && stagedClones().length === 0);

fakeDocument.activeElement = handC;
const ordinalBeforeLastExit = focusedHandCardInput.value;
assert('ArrowRight from the last hand card focuses the end turn button',
    pressKey('ArrowRight') && activeIs(endTurnButton) && state().selectedCard === null);
assert('boundary exit to the end turn button keeps no selection',
    focusedHandCardInput.value === ordinalBeforeLastExit && stagedClones().length === 0);

fakeDocument.activeElement = handC;
assert('ArrowLeft from the last hand card selects the middle card without wraparound',
    pressKey('ArrowLeft') && state().selectedCard === handB && activeIs(handB));
pressKey('Escape');
pressKey('Escape');
assert('ArrowRight from the middle card selects the last hand card',
    pressKey('ArrowRight') && state().selectedCard === handC && activeIs(handC));
pressKey('Escape');
assert('ArrowRight from the last hand card exits again to the end turn button',
    pressKey('ArrowRight') && activeIs(endTurnButton) && state().selectedCard === null && stagedClones().length === 0);
assert('ArrowDown from the last hand card still focuses the end turn button',
    (() => { fakeDocument.activeElement = handC; return true; })() &&
    pressKey('ArrowDown') && activeIs(endTurnButton) && state().selectedCard === null);

console.log('hand arrow boundary exit ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping hand arrow boundary test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping hand arrow boundary test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'hand arrow boundary harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('hand arrow boundary exit ok', completed.stdout)

    def test_boundary_controls_arrow_into_hand_focus_without_selecting_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = FAKE_ELEMENT_DATASET_CORE + r'''
const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);

const makeHiddenInput = (name, value) => {
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', name);
    input.setAttribute('value', String(value));
    return input;
};

const matTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(matTable);
const playerBoard = new FakeElement('div', 'playerBoard');
matTable.appendChild(playerBoard);
const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const holoRows = [];
['Intelligence', 'Speed', 'Visciousness', 'Resolve'].forEach((laneType) => {
    const lane = new FakeElement('li', 'lane ' + laneType);
    lanesEl.appendChild(lane);
    const holoRow = new FakeElement('ul', 'hologramRow');
    lane.appendChild(holoRow);
    holoRows.push(holoRow);
});

const deckHand = new FakeElement('div', 'deckHand handContainer');
matTable.appendChild(deckHand);
const deckStack = new FakeElement('div', 'deck-stack own-deck-stack');
playerBoard.appendChild(deckStack);
const activeDeck = new FakeElement('ul', 'deck active-deck');
deckStack.appendChild(activeDeck);
const drawForm = new FakeElement('form', 'cardActionForm');
activeDeck.appendChild(drawForm);
drawForm.appendChild(makeHiddenInput('action', 'draw'));
const drawButton = new FakeElement('button', 'card back draw');
drawForm.appendChild(drawButton);

const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);
const makeHandCard = (cardId, lane) => {
    const card = new FakeElement('li', 'cardContainer');
    card.setAttribute('tabindex', '0');
    card.setAttribute('draggable', 'true');
    card.dataset.sourceLane = '0';
    card.appendChild(makeHiddenInput('card_id', cardId));
    card.appendChild(makeHiddenInput('lane', lane));
    handList.appendChild(card);
    return card;
};
const handA = makeHandCard(201, 1);
const handB = makeHandCard(202, 2);
const handC = makeHandCard(203, 4);

const endTurnForm = new FakeElement('form', 'cardActionForm end-turn');
playerScreen.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);
const focusedHandCardInput = makeHiddenInput('focused_hand_card', '1');
endTurnForm.appendChild(focusedHandCardInput);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) { return body.querySelector(selector); },
    querySelectorAll(selector) { return body.querySelectorAll(selector); },
    getElementById(id) {
        if (id === 'turnLimits') return turnLimits;
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) {
        (documentListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};
const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
    drawBlockedTitle: 'draw blocked',
    playBlockedTitle: 'play blocked',
    flipBlockedTitle: 'flip blocked',
};

let cookieWrites = 0;
Object.defineProperty(fakeDocument, 'cookie', {
    set() { cookieWrites += 1; },
    get() { return `writes:${cookieWrites}`; },
});

for (const el of [
    body, playerScreen, playerBoard, handA, handB, handC,
    activeDeck, drawForm, drawButton, endTurnForm, endTurnButton,
]) {
    el.focus = () => { fakeDocument.activeElement = el; };
    el.blur = () => { if (fakeDocument.activeElement === el) fakeDocument.activeElement = body; };
}

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/MMM/game/1/board/1/action/' },
};
global.CSS = { escape: (value) => String(value) };
global.Element = function Element() {};
global.MutationObserver = function () {
    this.observe = () => {};
    this.disconnect = () => {};
};

const dragCode = __DRAG_JS__;
eval(dragCode);

(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const pressKey = (key) => {
    let prevented = false;
    const event = {
        key,
        repeat: false,
        target: fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};
const state = () => system.keyboardSelection;
const stagedClones = () => holoRows.flatMap((row) => row.children);
const activeIs = (element) => fakeDocument.activeElement === element;

fakeDocument.activeElement = drawButton;
assert('draw ArrowLeft focuses the first hand card without selecting it',
    pressKey('ArrowLeft') && activeIs(handA) && state().selectedCard === null &&
    state().digitBuffer === '' && state().ghostFlip === false);
assert('draw ArrowLeft leaves the persisted slot and lane rows untouched',
    focusedHandCardInput.value === '1' && system.control.persistedHandSlot === 1 &&
    stagedClones().length === 0);
const guardCookieWrites = cookieWrites;

fakeDocument.activeElement = endTurnButton;
assert('end turn ArrowRight focuses the last hand card without selecting it',
    pressKey('ArrowRight') && activeIs(handC) && state().selectedCard === null &&
    state().digitBuffer === '' && state().ghostFlip === false);
assert('end turn ArrowRight leaves the persisted slot and lane rows untouched',
    focusedHandCardInput.value === '1' && system.control.persistedHandSlot === 1 &&
    stagedClones().length === 0 && cookieWrites === guardCookieWrites);

fakeDocument.activeElement = handA;
assert('typing 1 shows the lane preview for the first hand card',
    pressKey('1') && state().selectedCard === handA && state().lanePreviewActive === true);
assert('Enter stages the first play', pressKey('Enter') && handA.classList.contains('ghost'));
fakeDocument.activeElement = handB;
assert('typing 2 shows the lane preview for the middle hand card',
    pressKey('2') && state().selectedCard === handB);
assert('Enter stages the second play and exhausts the play allowance',
    pressKey('Enter') && handB.classList.contains('ghost') &&
    handC.classList.contains('blocked') && handC.getAttribute('tabindex') === null);
const spentCookieWrites = cookieWrites;

fakeDocument.activeElement = drawButton;
assert('draw ArrowLeft lands on the first still-focusable hand card',
    pressKey('ArrowLeft') && activeIs(handA) && state().selectedCard === null);
fakeDocument.activeElement = endTurnButton;
assert('end turn ArrowRight skips the blocked card to the last focusable hand card',
    pressKey('ArrowRight') && activeIs(handB) && state().selectedCard === null &&
    cookieWrites === spentCookieWrites);

fakeDocument.activeElement = endTurnButton;
assert('end turn ArrowLeft stays unrouted',
    !pressKey('ArrowLeft') && activeIs(endTurnButton) && state().selectedCard === null);
fakeDocument.activeElement = drawButton;
assert('draw ArrowRight stays unrouted',
    !pressKey('ArrowRight') && activeIs(drawButton) && state().selectedCard === null);

console.log('boundary control hand entry ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping boundary hand entry test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping boundary hand entry test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'boundary control hand entry harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('boundary control hand entry ok', completed.stdout)

    def test_field_arrow_left_right_walks_face_down_cards_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = FAKE_ELEMENT_NAVIGATION_CORE + r'''
const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);

const placeCard = (card, left, top) => {
    card.getBoundingClientRect = () => ({ left, top, width: 100, height: 140 });
};
const laneNames = ['Intelligence', 'Speed', 'Visciousness', 'Resolve'];
const buildLane = (container, name) => {
    const lane = new FakeElement('li', 'lane ' + name);
    container.appendChild(lane);
    const hologramRow = new FakeElement('ul', 'hologramRow');
    lane.appendChild(hologramRow);
    const cardRow = new FakeElement('ul', 'cardRow');
    cardRow.setAttribute('title', 'cards');
    lane.appendChild(cardRow);
    return { lane, hologramRow, cardRow };
};
const addFieldCard = (row, className, left, top) => {
    const card = new FakeElement('li', className);
    row.appendChild(card);
    placeCard(card, left, top);
    return card;
};
const addStagedHologram = (hologramRow, left, top) => {
    const wrap = new FakeElement('div', 'hologram keyboard-staged');
    hologramRow.appendChild(wrap);
    const card = new FakeElement('li', 'cardContainer faceDown');
    card.setAttribute('tabindex', '0');
    wrap.appendChild(card);
    placeCard(card, left, top);
    return card;
};
const makeFocusableFieldCard = (card, cardId) => {
    card.setAttribute('tabindex', '0');
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', 'card_id');
    input.setAttribute('value', String(cardId));
    card.appendChild(input);
    return card;
};

const enemyTable = new FakeElement('ul', 'enemyBoards basic-mat table');
playerScreen.appendChild(enemyTable);
const enemyBoard = new FakeElement('li', 'enemyBoard');
enemyTable.appendChild(enemyBoard);
const enemyLanes = new FakeElement('ul', 'lanes');
enemyBoard.appendChild(enemyLanes);
const enemyLane = buildLane(enemyLanes, 'Intelligence');
placeCard(
    addFieldCard(enemyLane.cardRow, 'cardContainer faceDown', 170, 50),
    170, 50,
);

const playerTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(playerTable);
const playerBoard = new FakeElement('div', 'playerBoard');
playerTable.appendChild(playerBoard);
const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const playerLanes = {};
for (const name of laneNames) {
    playerLanes[name] = buildLane(lanesEl, name);
}

const cardA = makeFocusableFieldCard(
    addFieldCard(playerLanes.Intelligence.cardRow, 'cardContainer faceDown', 10, 100),
    601,
);
const cardC = makeFocusableFieldCard(
    addFieldCard(playerLanes.Intelligence.cardRow, 'cardContainer faceDown', 60, 100),
    603,
);
placeCard(addFieldCard(playerLanes.Intelligence.cardRow, 'cardContainer', 250, 100), 250, 100);
const trustedRow = new FakeElement('ul', 'cardRow');
trustedRow.setAttribute('title', 'trustedCards');
playerLanes.Intelligence.lane.appendChild(trustedRow);
placeCard(addFieldCard(trustedRow, 'cardContainer', 220, 200), 220, 200);

const blockedFieldCard = makeFocusableFieldCard(
    addFieldCard(playerLanes.Speed.cardRow, 'cardContainer faceDown blocked', 30, 100),
    602,
);
const cardH = addStagedHologram(playerLanes.Visciousness.hologramRow, 200, 10);
const cardE = addStagedHologram(playerLanes.Resolve.hologramRow, 290, 10);
const cardD = makeFocusableFieldCard(
    addFieldCard(playerLanes.Resolve.cardRow, 'cardContainer faceDown', 290, 100),
    604,
);

const deckHand = new FakeElement('div', 'deckHand handContainer');
playerTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);
const makeHandCard = (cardId, lane) => {
    const card = new FakeElement('li', 'cardContainer');
    card.setAttribute('tabindex', '0');
    card.setAttribute('draggable', 'true');
    card.dataset.sourceLane = '0';
    const cardIdInput = new FakeElement('input');
    cardIdInput.setAttribute('type', 'hidden');
    cardIdInput.setAttribute('name', 'card_id');
    cardIdInput.setAttribute('value', String(cardId));
    card.appendChild(cardIdInput);
    const laneInput = new FakeElement('input');
    laneInput.setAttribute('type', 'hidden');
    laneInput.setAttribute('name', 'lane');
    laneInput.setAttribute('value', String(lane));
    card.appendChild(laneInput);
    handList.appendChild(card);
    return card;
};
const handA = makeHandCard(201, 2);

const endTurnForm = new FakeElement('form', 'cardActionForm end-turn');
playerScreen.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);
const focusedHandCardInput = new FakeElement('input');
focusedHandCardInput.setAttribute('type', 'hidden');
focusedHandCardInput.setAttribute('name', 'focused_hand_card');
focusedHandCardInput.setAttribute('value', '1');
endTurnForm.appendChild(focusedHandCardInput);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) {
        return body.querySelector(selector);
    },
    querySelectorAll(selector) {
        return body.querySelectorAll(selector);
    },
    getElementById(id) {
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) {
        (documentListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};
const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
};
fakeDocument.getElementById = (id) => {
    if (id === 'turnLimits') return turnLimits;
    for (const el of descendantsInOrder(body)) {
        if (el.id === id) return el;
    }
    return null;
};

for (const el of [
    body, playerScreen, endTurnForm, endTurnButton, handA,
    cardA, cardC, cardD, cardE, cardH, blockedFieldCard,
]) {
    el.focus = () => { fakeDocument.activeElement = el; };
    el.blur = () => { if (fakeDocument.activeElement === el) fakeDocument.activeElement = body; };
}

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/x/action' },
    setTimeout() { return 0; },
    clearTimeout() {},
};
global.CSS = { escape: (value) => String(value) };
global.MutationObserver = function () {
    this.observe = () => {};
    this.disconnect =     this.disconnect = () => {};
};

const dragCode = __DRAG_JS__;
eval(dragCode);

(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const pressKey = (key) => {
    let prevented = false;
    const event = {
        key,
        repeat: false,
        target: fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};
const state = () => system.keyboardSelection;
const activeIs = (element) => fakeDocument.activeElement === element;
const stagedCloneCount = () => laneNames.reduce(
    (total, name) => total + playerLanes[name].hologramRow.children.length,
    0,
);
const fieldCards = [cardA, blockedFieldCard, cardC, cardH, cardE, cardD];

fakeDocument.activeElement = cardA;
assert('ArrowLeft from the leftmost face-down field card is a boundary no-op',
    !pressKey('ArrowLeft') && activeIs(cardA) && state().selectedCard === null && state().digitBuffer === '');
assert('boundary ArrowLeft writes no ordinal and stages no clones',
    focusedHandCardInput.value === '1' && stagedCloneCount() === 2);

assert('ArrowRight from the leftmost face-down field card reaches the rendered-right neighbour',
    pressKey('ArrowRight') && activeIs(blockedFieldCard) && state().selectedCard === null);
assert('field navigation writes no ordinals and stages no clones',
    focusedHandCardInput.value === '1' && stagedCloneCount() === 2);
assert('field navigation leaves no keyboard-selected marks',
    fieldCards.every((card) => !card.classList.contains('keyboard-selected')));

assert('arrows stay no-ops while a blocked field card keeps focus',
    !pressKey('ArrowLeft') && !pressKey('ArrowRight') && activeIs(blockedFieldCard) && state().selectedCard === null);

fakeDocument.activeElement = cardC;
assert('ArrowLeft from the card after the blocked one resumes the rendered row',
    pressKey('ArrowLeft') && activeIs(blockedFieldCard));
fakeDocument.activeElement = cardA;
assert('ArrowRight from the leftmost field card reaches the blocked neighbour again',
    pressKey('ArrowRight') && activeIs(blockedFieldCard));

fakeDocument.activeElement = cardC;
assert('ArrowRight from the row continues onto the staged hologram of the next lane',
    pressKey('ArrowRight') && activeIs(cardH));
assert('ArrowLeft from the staged hologram skips the enemy board card',
    pressKey('ArrowLeft') && activeIs(cardC));

fakeDocument.activeElement = cardH;
assert('ArrowRight from the staged hologram skips the trusted and face-up cards',
    pressKey('ArrowRight') && activeIs(cardE));

fakeDocument.activeElement = cardE;
assert('ArrowLeft from the column-tied hologram steps back to the rendered-left column',
    pressKey('ArrowLeft') && activeIs(cardH));
fakeDocument.activeElement = cardE;
assert('ArrowRight inside a shared column steps onto its lower card',
    pressKey('ArrowRight') && activeIs(cardD));
assert('ArrowLeft from the column card returns to its hologram',
    pressKey('ArrowLeft') && activeIs(cardE));

fakeDocument.activeElement = cardD;
assert('ArrowRight from the rightmost face-down field card is a boundary no-op',
    !pressKey('ArrowRight') && activeIs(cardD) && state().selectedCard === null && stagedCloneCount() === 2);

fakeDocument.activeElement = cardA;
assert('ArrowUp from the field still focuses the end turn button',
    pressKey('ArrowUp') && activeIs(endTurnButton) && state().selectedCard === null);
fakeDocument.activeElement = cardA;
assert('ArrowDown from the field still selects the persisted hand slot',
    pressKey('ArrowDown') && state().selectedCard === handA && activeIs(handA));
pressKey('Escape');
assert('cancelling the hand selection restores the untouched field clones',
    state().selectedCard === null && stagedCloneCount() === 2 && focusedHandCardInput.value === '1');

fakeDocument.activeElement = handA;
assert('typing digit 1 selects the hand card for the cycle check',
    pressKey('1') && state().selectedCard === handA && state().currentLane === 2 && stagedCloneCount() === 3);
fakeDocument.activeElement = cardA;
assert('ArrowRight with an active selection cycles lanes instead of walking the field',
    pressKey('ArrowRight') && state().currentLane === 3 && activeIs(cardA));
assert('ArrowLeft with an active selection cycles lanes back',
    pressKey('ArrowLeft') && state().currentLane === 2 && activeIs(cardA));
pressKey('Escape');
assert('cancelling the cycle returns focus to the hand card with the preview removed',
    state().selectedCard === null && stagedCloneCount() === 2 && activeIs(handA));
fakeDocument.activeElement = cardA;
assert('field arrows resume after the cycle is cancelled',
    pressKey('ArrowRight') && activeIs(blockedFieldCard));

fakeDocument.activeElement = handA;
assert('ArrowUp from the hand still lands on the topmost focusable field card',
    pressKey('ArrowUp') && activeIs(cardH) && state().selectedCard === null);

console.log('field arrow neighbours ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping field arrow neighbour test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping field arrow neighbour test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'field arrow neighbour harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('field arrow neighbours ok', completed.stdout)

    def test_keyboard_selected_property_cleared_on_focus_loss_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = FAKE_ELEMENT_DATASET_CORE + r'''
const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const matTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(matTable);
const playerBoard = new FakeElement('div', 'playerBoard');
matTable.appendChild(playerBoard);

const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);
const holoRows = [];
const fieldCards = [];
 ['', '', '', ''].forEach((unused, laneIndex) => {
    const lane = new FakeElement('li', 'lane');
    lane.classList.add(['Intelligence', 'Speed', 'Visciousness', 'Resolve'][laneIndex]);
    lanesEl.appendChild(lane);
    const fieldCard = new FakeElement('li', 'cardContainer');
    fieldCard.setAttribute('tabindex', '0');
    fieldCard.dataset.cardLane = String(laneIndex + 1);
    const fieldId = new FakeElement('input');
    fieldId.setAttribute('type', 'hidden');
    fieldId.setAttribute('name', 'card_id');
    fieldId.setAttribute('value', `500${laneIndex + 1}`);
    fieldCard.appendChild(fieldId);
    lane.appendChild(fieldCard);
    fieldCards.push(fieldCard);
    const holoRow = new FakeElement('ul', 'hologramRow');
    lane.appendChild(holoRow);
    holoRows.push(holoRow);
});

const deckHand = new FakeElement('div', 'deckHand handContainer');
matTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);

const makeHandCard = (cardId, lane) => {
    const card = new FakeElement('li', 'cardContainer');
    card.setAttribute('tabindex', '0');
    card.setAttribute('draggable', 'true');
    card.dataset.cardLane = String(lane);
    card.dataset.sourceLane = '0';
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', 'card_id');
    input.setAttribute('value', String(cardId));
    card.appendChild(input);
    handList.appendChild(card);
    return card;
};
const handA = makeHandCard(201, 1);
const handB = makeHandCard(202, 2);
const cardButton = new FakeElement('button');
cardButton.setAttribute('type', 'button');
handA.appendChild(cardButton);
const handCards = [handA, handB];

const endTurnForm = new FakeElement('form', 'cardActionForm end-turn');
playerScreen.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);
const focusedHandCardInput = new FakeElement('input');
focusedHandCardInput.setAttribute('type', 'hidden');
focusedHandCardInput.setAttribute('name', 'focused_hand_card');
focusedHandCardInput.setAttribute('value', '1');
endTurnForm.appendChild(focusedHandCardInput);
for (const el of [handA, handB, cardButton, endTurnButton]) {
    el.focus = () => { fakeDocument.activeElement = el; };
    el.blur = () => { if (fakeDocument.activeElement === el) fakeDocument.activeElement = body; };
}

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) {
        return body.querySelector(selector);
    },
    querySelectorAll(selector) {
        return body.querySelectorAll(selector);
    },
    getElementById(id) {
        if (id === 'turnLimits') return turnLimits;
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) {
        (documentListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};
const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '1', tactics: '2',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
};

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/MMM/game/1/board/1/action/' },
};
global.CSS = { escape: (value) => String(value) };
global.MutationObserver = function (handler) {
    this.observe = () => {};
    this.disconnect = () => {};
};

const dragCode = __DRAG_JS__;
eval(dragCode);

(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const clickHandlers = documentListeners['click'] ?? [];

const pressKey = (key, options = {}) => {
    let prevented = false;
    const event = {
        key,
        repeat: options.repeat ?? false,
        target: options.target ?? fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const clickCard = (card) => {
    clickHandlers.forEach((entry) => entry({
        type: 'click', button: 0, target: card, clientX: 5, clientY: 5,
    }));
};
const fireScreenFocus = (type, target, relatedTarget) => {
    (playerScreen.eventHandlers[type] || []).forEach((entry) => entry({
        type, target, relatedTarget,
    }));
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};

const state = () => system.keyboardSelection;
const activeIs = (element) => fakeDocument.activeElement === element;
const bodyArrowsCount = () => body.children.filter(
    (child) => child.classes && child.classes.has('hologram-arrow'),
).length;

fakeDocument.activeElement = body;

assert('typing digit 1 selects card A with a lane preview while focused',
    pressKey('1') && state().selectedCard === handA && state().lanePreviewActive === true && activeIs(handA));
assert('hand selection writes the preview clone into lane 1 row',
    holoRows[0].children.length === 1 &&
    holoRows[0].children[0].classList.contains('hologram') &&
    holoRows[0].children[0].classList.contains('keyboard-preview'));
assert('lane preview keeps the property on the focused card',
    handA.getAttribute('data-keyboard-selected') === 'true' &&
    handA.classList.contains('keyboard-selected') &&
    handA.getAttribute('aria-selected') === 'true');

fireScreenFocus('focusout', handA, cardButton);
assert('focus moving inside the card keeps the selection styling',
    handA.getAttribute('data-keyboard-selected') === 'true' &&
    handA.classList.contains('keyboard-selected') &&
    handA.getAttribute('aria-selected') === 'true');

fireScreenFocus('focusout', handA, endTurnButton);
assert('true focus loss removes the property even for the last selected card',
    handA.getAttribute('data-keyboard-selected') === null &&
    handA.getAttribute('aria-selected') === null &&
    !handA.classList.contains('keyboard-selected'));
assert('the lane preview survives focus loss so a lane click can still confirm',
    state().selectedCard === handA && holoRows[0].children.length === 1);

fireScreenFocus('focusin', handA, undefined);
assert('refocusing the still selected card restores the property',
    handA.getAttribute('data-keyboard-selected') === 'true' &&
    handA.classList.contains('keyboard-selected') &&
    system.control._focusArrow !== null && system.control._focusArrow.source === handA);
assert('filtering the focus arrow keeps exactly one svg in the body', bodyArrowsCount() === 1);

fakeDocument.activeElement = handA;
assert('Enter stages the play into the preview lane',
    pressKey('Enter') && handA.classList.contains('ghost') && handA.dataset.stagedLane === '1');
const stagedHologram = holoRows[0].children.filter((child) => !child.classList.contains('drop-zone'))[0];
assert('staged hologram replaces the preview clone in lane 1 row',
    holoRows[0].children.length === 1 && stagedHologram.classList.contains('hologram') &&
    stagedHologram.classList.contains('keyboard-staged'));
const stagedClone = stagedHologram.querySelector('.cardContainer');
assert('staged hologram links the played card id',
    stagedHologram.getAttribute('data-staged-for-card-id') === '201');
assert('staged play removes the property from the hand card',
    handA.getAttribute('data-keyboard-selected') === null &&
    !handA.classList.contains('keyboard-selected'));
assert('staged clone gains a flip tab stop while flips remain',
    stagedClone.getAttribute('tabindex') === '0');

fakeDocument.activeElement = handA;
assert('digit 1 selects the played ghost for its flip',
    pressKey('1') && state().ghostFlip === true && state().selectedCard === handA);
assert('ghost-flip selection carries the property again',
    handA.getAttribute('data-keyboard-selected') === 'true' &&
    handA.getAttribute('aria-selected') === 'true');

fireScreenFocus('focusout', handA, stagedClone);
assert('focus moving between the ghost and its lane clone keeps the property',
    handA.getAttribute('data-keyboard-selected') === 'true' && state().ghostFlip === true);

fireScreenFocus('focusout', handA, endTurnButton);
assert('focus loss keeps the property while the card is being played to a lane',
    handA.getAttribute('data-keyboard-selected') === 'true' &&
    handA.classList.contains('keyboard-selected') &&
    handA.getAttribute('aria-selected') === 'true' && state().ghostFlip === true);

assert('Enter confirms the ghost flip and clears the property',
    pressKey('Enter') && handA.dataset.stagedFlipped === 'true' &&
    handA.getAttribute('data-keyboard-selected') === null &&
    !handA.classList.contains('keyboard-selected'));
assert('the flipped predecessor stays face up after the flip confirm',
    stagedClone.classList.contains('faceDown') === false);

fakeDocument.activeElement = body;
clickCard(handB);
assert('mouse click selects card B',
    state().selectedCard === handB && state().mouseSelecting === true && activeIs(handB));
assert('mouse selection carries the property',
    handB.getAttribute('data-keyboard-selected') === 'true');
assert('mouse preview cursor follows the selection',
    fakeDocument.getElementById('mousePreviewCursor') !== null);
assert('mousemove route is installed for the mouse selection',
    (documentListeners['mousemove'] || []).length === 1);

fireScreenFocus('focusout', handB, null);
assert('mouse selection styling is removed when focus truly leaves the card',
    handB.getAttribute('data-keyboard-selected') === null &&
    handB.getAttribute('aria-selected') === null &&
    !handB.classList.contains('keyboard-selected'));
assert('the mouse selection stays confirmable after focus loss',
    state().selectedCard === handB && state().mouseSelecting === true &&
    fakeDocument.getElementById('mousePreviewCursor') !== null);

assert('Escape cancels the abandoned mouse selection and repairs focus',
    pressKey('Escape') && state().selectedCard === null && state().digitBuffer === '' &&
    state().mouseSelecting === false && activeIs(handB));
assert('Escape teardown removes the cursor marker and mousemove route',
    fakeDocument.getElementById('mousePreviewCursor') === null &&
    (documentListeners['mousemove'] || []).length === 0);
assert('no selection property lingers after Escape',
    handB.getAttribute('data-keyboard-selected') === null);

system.destroy();
assert('destroy cleans up', bodyArrowsCount() === 0);

console.log('keyboard-selected property focus lifecycle ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping focus-loss property DOM test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping focus-loss property DOM test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'keyboard-selected property focus lifecycle harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('keyboard-selected property focus lifecycle ok', completed.stdout)


        import os
        css_path = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static', 'cards.css')
        with open(css_path) as css_file:
            cards_css = css_file.read()
        self.assertNotIn(
            'li.cardContainer:not(.blocked):focus-within {\n        & .smallCard{',
            cards_css,
        )
        self.assertIn(
            'li.cardContainer:not(.blocked):not(.faceDown):focus-within',
            cards_css,
        )
        self.assertIn(
            '.playingCards li.cardContainer:focus-within{\n        outline-offset: 4px;\n        outline: 3px solid;',
            cards_css,
        )

    def test_lane_indicator_keeps_position_when_rows_split(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cards.css')) as css_file:
            cards_css = css_file.read()
        with open(os.path.join(static_dir, 'laneStacking.js')) as js_file:
            stacking_js = js_file.read()
        self.assertRegex(cards_css, r'ul\.lanes li\.lane\s*>\s*p[^{]*\{[^}]*position:\s*absolute')
        self.assertIn('translate(-50%, -50%)', cards_css)
        self.assertNotIn('lane-indicator', stacking_js)

    def test_player_phase_focuses_end_turn_button_after_scroll(self):
        import os
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()
        player_branch = _extract_js_brace_block(loading_js, "if (phase === 'player')")
        self.assertIn('.playerScreen .deckHand .end-turn', player_branch)
        self.assertIn('endTurnBtn.focus', player_branch)
        self.assertIn('requestAnimationFrame', player_branch)
        self.assertIn("autofocus", open(
            os.path.join(os.path.dirname(__file__), '..', 'MMM', 'jinja2', 'MMM', 'battle', 'viewBoard.jinja2')
        ).read())

        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)
        response = self.client.get(board_url)
        self.assertContains(response, 'class="end-turn"')
        self.assertRegex(response.content.decode(), r'<button[^>]*class="end-turn"[^>]*autofocus')

    def test_focused_hand_card_persists_across_turns_and_round_trips(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        action_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        response = self.client.get(board_url)
        content = response.content.decode()
        self.assertIn('data-focused-hand-card="1"', content)
        self.assertIn('name="focused_hand_card" value="1"', content)

        self.client.post(action_url, {"action": "draw", "focused_hand_card": "4"})
        self.human_participant.refresh_from_db()
        self.assertEqual(self.human_participant.focusedHandCard, 4)

        self.client.post(action_url, {"action": "end_turn", "focused_hand_card": "abc"})
        self.human_participant.refresh_from_db()
        self.assertEqual(self.human_participant.focusedHandCard, 4)

        response = self.client.get(board_url)
        self.assertIn('data-focused-hand-card="4"', response.content.decode())

    def test_arrow_key_routing_uses_region_navigator_and_persists_focused_hand_card(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        self.assertIn('class RegionNavigator {', drag_js)
        self.assertIn('class KeyboardSelectionControl {', drag_js)
        self.assertIn('class CardDragDropSystem {', drag_js)

        shortcut_class = drag_js.index('class ShortcutHoldAction {')
        navigator_start = drag_js.index('class RegionNavigator {')
        keyboard_selection_start = drag_js.index('class KeyboardSelectionControl {')
        card_drag_drop_start = drag_js.index('class CardDragDropSystem {')
        self.assertGreater(navigator_start, shortcut_class)
        self.assertLess(navigator_start, keyboard_selection_start)
        self.assertLess(keyboard_selection_start, card_drag_drop_start)

        navigator_class = drag_js[navigator_start:keyboard_selection_start]
        self.assertIn('regionFor(element)', navigator_class)
        self.assertIn('firstFieldCard()', navigator_class)
        self.assertIn('nextFieldCard(fromElement, step)', navigator_class)
        self.assertIn('fieldCardForFocus(fromElement)', navigator_class)
        self.assertIn('focusableFieldCards()', navigator_class)
        self.assertIn('handCardAt(slot)', navigator_class)
        self.assertIn('endTurnButton()', navigator_class)
        self.assertIn('drawButton()', navigator_class)

        self.assertIn(
            '.playerScreen .deckHand .hand-scroll ul.hand li.cardContainer',
            navigator_class,
        )
        self.assertIn(
            '.playerScreen .deckHand ul.hand li.cardContainer',
            navigator_class,
        )
        self.assertIn('.playerScreen .lanes .cardContainer', navigator_class)
        self.assertIn('.playerScreen .end-turn', navigator_class)
        self.assertIn(
            '.playerBoard .deck-stack .active-deck button.draw',
            navigator_class,
        )

        self.assertIn('getBoundingClientRect()', navigator_class)
        self.assertIn(
            '.playerScreen .playerBoard .lanes .cardContainer[tabindex="0"]',
            navigator_class[
                navigator_class.index('    focusableFieldCards()'):
                navigator_class.index('    firstFieldCard()')
            ],
        )
        self.assertNotIn(
            '.playerScreen .lanes .cardContainer[tabindex="0"]',
            navigator_class,
        )
        next_field_block = navigator_class[
            navigator_class.index('    nextFieldCard(fromElement, step)'):
            navigator_class.index('    handCardAt(slot)')
        ]
        self.assertIn("if (ra.left !== rb.left) return ra.left - rb.left;", next_field_block)
        self.assertIn('return ra.top - rb.top;', next_field_block)
        self.assertIn(
            ".closest('.playerScreen .lanes .cardContainer')",
            navigator_class[
                navigator_class.index('    fieldCardForFocus(fromElement)'):
                navigator_class.index('    focusableFieldCards()')
            ],
        )
        self.assertIn('currentIndex === -1', next_field_block)
        self.assertIn('cards[currentIndex + step] ?? null', next_field_block)
        self.assertIn('orderableKeyboardCards()', navigator_class)
        self.assertIn('_findEndTurnControl()', navigator_class)
        self.assertIn('_findDrawControl()', navigator_class)

        control_class = drag_js[keyboard_selection_start:card_drag_drop_start]
        self.assertIn('navigate(direction, fromElement)', control_class)
        self.assertIn('persistedHandSlot', control_class)
        self.assertIn("getElementById('turnLimits')", control_class)
        self.assertIn('dataset.focusedHandCard', control_class)
        self.assertIn('this.navigator', control_class)
        self.assertIn('this.system', control_class)

        constructor_block = control_class[
            control_class.index('constructor({'):control_class.index('    _emptyKeyboardSelection() {')
        ]
        self.assertIn('this.persistedHandSlot = Number.isInteger(raw) && raw >= 1 ? raw : 1;', constructor_block)

        select_keyboard_code = control_class[
            control_class.index('    selectKeyboardCard(card'):
            control_class.index('    moveKeyboardSelection(laneValue)')
        ]
        self.assertIn("form.cardActionForm input[name=\"focused_hand_card\"]", select_keyboard_code)
        clear_index = select_keyboard_code.rindex('this.clearKeyboardSelection()')
        state_index = select_keyboard_code.rindex('this.state = {')
        write_index = select_keyboard_code.index(
            "form.cardActionForm input[name=\"focused_hand_card\"]"
        )
        self.assertGreater(write_index, clear_index)
        self.assertLess(write_index, state_index)

        navigate_method = control_class[
            control_class.index('    navigate(direction, fromElement)'):
        ]
        next_method_match = navigate_method.index('    ', navigate_method.index('\n    _mirrorStagedFocus'))
        navigate_method = navigate_method[:next_method_match]

        self.assertIn("region === 'hand' && direction === 'ArrowUp'", navigate_method)
        self.assertIn("region === 'hand' && direction === 'ArrowDown'", navigate_method)
        self.assertIn("region === 'field' && direction === 'ArrowUp'", navigate_method)
        field_branch_start = navigate_method.index(
            "region === 'field' && (direction === 'ArrowLeft' || direction === 'ArrowRight')"
        )
        field_branch = navigate_method[
            field_branch_start:field_branch_start +
            navigate_method[field_branch_start:].index("region === 'field' && direction === 'ArrowDown'")
        ]
        self.assertIn(
            "target = this.navigator.nextFieldCard(fromElement, direction === 'ArrowRight' ? 1 : -1);",
            field_branch,
        )
        self.assertNotIn('selectKeyboardCard', field_branch)
        self.assertNotIn('isHandCard', field_branch)
        self.assertIn("region === 'field' && direction === 'ArrowDown'", navigate_method)
        self.assertIn("region === 'end-turn' && direction === 'ArrowUp'", navigate_method)
        self.assertIn("region === 'end-turn' && direction === 'ArrowDown'", navigate_method)
        self.assertIn("region === 'end-turn' && direction === 'ArrowRight'", navigate_method)
        self.assertIn("region === 'draw' && direction === 'ArrowUp'", navigate_method)
        self.assertIn("region === 'draw' && direction === 'ArrowDown'", navigate_method)
        self.assertIn("region === 'draw' && direction === 'ArrowLeft'", navigate_method)
        self.assertIn(
            "target = this.navigator.lastFocusableOrderableHandCard()",
            navigate_method,
        )
        self.assertIn(
            "target = this.navigator.firstFocusableOrderableHandCard()",
            navigate_method,
        )
        self.assertIn('firstFieldCard()', navigate_method)
        self.assertIn('endTurnButton()', navigate_method)
        self.assertIn('drawButton()', navigate_method)
        self.assertIn('handCardAt(this.persistedHandSlot)', navigate_method)
        self.assertIn(
            "region === 'hand' && (direction === 'ArrowLeft' || direction === 'ArrowRight')",
            navigate_method,
        )
        self.assertIn('const handStep = direction === \'ArrowRight\' ? 1 : -1;', navigate_method)
        self.assertIn('this.navigator.handArrowAtBoundary(fromElement, handStep)', navigate_method)
        self.assertIn('this.navigator.handArrowExitButton(handStep)', navigate_method)
        self.assertIn('this.navigator.nextHandCard(fromElement, handStep)', navigate_method)
        self.assertIn('const targetIndex = this.system.playableKeyboardCards().indexOf(target);', navigate_method)
        self.assertIn('let ordinal = this.persistedHandSlot;', navigate_method)
        self.assertIn(
            "if (typeof target.focus !== 'function') return false;",
            navigate_method,
        )
        self.assertEqual(
            navigate_method.count('target.focus({ preventScroll: true })'),
            2,
        )
        self.assertNotIn("region === 'end-turn' && direction === 'ArrowLeft'", navigate_method)
        self.assertNotIn("region === 'draw' && direction === 'ArrowRight'", navigate_method)
        self.assertIn('this.system.selectKeyboardCard(target, String(ordinal))', navigate_method)

        parent_class = drag_js[card_drag_drop_start:]
        self.assertIn('    onKeyboardKeyDown(event)', parent_class)
        self.assertIn('    selectOrderedCard(', parent_class)
        keydown_code = parent_class[
            parent_class.index('    onKeyboardKeyDown(event)'):
            parent_class.index('    selectOrderedCard(')
        ]

        self.assertIn(
            "key === 'ArrowUp' || key === 'ArrowDown' || key === 'ArrowLeft' || key === 'ArrowRight'",
            keydown_code,
        )
        self.assertIn(
            '!this.keyboardSelection.selectedCard',
            keydown_code,
        )
        self.assertIn(
            '!this.keyboardSelection.ghostFlip',
            keydown_code,
        )
        self.assertIn(
            'this.control.navigate(key, document.activeElement)',
            keydown_code,
        )
        self.assertIn(
            'if (this.control.navigate(key, document.activeElement)) event.preventDefault();',
            keydown_code,
        )

        arrow_branch_index = keydown_code.index(
            "key === 'ArrowUp' || key === 'ArrowDown' || key === 'ArrowLeft' || key === 'ArrowRight'"
        )
        lane_step_index = keydown_code.index('const laneStep = {')
        self.assertLess(arrow_branch_index, lane_step_index)

        navigate_call_count = keydown_code.count('.navigate(')
        self.assertEqual(navigate_call_count, 1)

        parent_navigate_count = parent_class.count('.navigate(')
        self.assertEqual(parent_navigate_count, 1)

        self.assertIn('this.moveKeyboardSelection(nextLane)', keydown_code)
        self.assertIn("ArrowLeft: -1", keydown_code)
        self.assertIn("ArrowRight: 1", keydown_code)
        self.assertIn("ArrowUp: -1", keydown_code)
        self.assertIn("ArrowDown: 1", keydown_code)

        self.assertIn("get control() {", parent_class)
        self.assertIn("return this._keyboardSelectionControl;", parent_class)

    def test_hand_arrow_boundaries_focus_draw_and_end_turn_without_selecting(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        navigator_start = drag_js.index('class RegionNavigator {')
        keyboard_selection_start = drag_js.index('class KeyboardSelectionControl {')
        card_drag_drop_start = drag_js.index('class CardDragDropSystem {')
        navigator_class = drag_js[navigator_start:keyboard_selection_start]
        control_class = drag_js[keyboard_selection_start:card_drag_drop_start]

        boundary_start = navigator_class.index('    handArrowAtBoundary(fromElement, step) {')
        exit_start = navigator_class.index('    handArrowExitButton(step) {')
        exit_end = navigator_class.index('    endTurnButton()', exit_start)
        boundary_block = navigator_class[boundary_start:exit_start]
        exit_block = navigator_class[exit_start:exit_end]

        self.assertIn('handCardForFocus(fromElement)', boundary_block)
        self.assertIn(
            'const orderableCards = this.system.orderableKeyboardCards();',
            boundary_block,
        )
        self.assertIn(
            'const currentIndex = orderableCards.indexOf(this.handCardForFocus(fromElement));',
            boundary_block,
        )
        self.assertIn(
            'return step < 0 ? currentIndex === 0 : currentIndex === orderableCards.length - 1;',
            boundary_block,
        )
        self.assertIn(
            'return step < 0 ? this.drawButton() : this.endTurnButton();',
            exit_block,
        )
        self.assertIn('focusableOrderableHandCards()', exit_block)
        self.assertIn(
            "card => card?.getAttribute?.('tabindex') === '0'",
            exit_block,
        )
        self.assertIn('return this.focusableOrderableHandCards()[0] || null;', exit_block)
        self.assertIn(
            'return focusableCards[focusableCards.length - 1] || null;',
            exit_block,
        )
        self.assertIn('selectKeyboardCard', control_class)
        self.assertNotIn('selectKeyboardCard', exit_block)

        navigate_method = control_class[
            control_class.index('    navigate(direction, fromElement)'):
        ]
        navigate_method = navigate_method[:navigate_method.index('\n    _mirrorStagedFocus')]
        hand_branch = navigate_method[
            navigate_method.index(
                "region === 'hand' && (direction === 'ArrowLeft' || direction === 'ArrowRight')"
            ):
            navigate_method.index("region === 'field' && direction === 'ArrowUp'")
        ]

        self.assertIn("const handStep = direction === 'ArrowRight' ? 1 : -1;", hand_branch)
        self.assertIn('this.navigator.handArrowAtBoundary(fromElement, handStep)', hand_branch)
        self.assertIn('target = this.navigator.handArrowExitButton(handStep);', hand_branch)
        boundary_index = hand_branch.index('this.navigator.handArrowAtBoundary(fromElement, handStep)')
        exit_index = hand_branch.index('target = this.navigator.handArrowExitButton(handStep);')
        next_card_index = hand_branch.index('this.navigator.nextHandCard(fromElement, handStep)')
        self.assertLess(boundary_index, exit_index)
        self.assertLess(exit_index, next_card_index)

        self.assertNotIn('selectKeyboardCard', navigator_class)
        self.assertNotIn('isHandCard', hand_branch[boundary_index:next_card_index])
        self.assertIn('isHandCard = true', hand_branch[next_card_index:])

    def test_zero_allowances_keep_staged_ghosts_and_facedown_cards_focusable_via_dom(self):
        import os
        import subprocess
        import tempfile

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        harness = FAKE_ELEMENT_DATASET_CORE + r'''
const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);

const placeCard = (card, left, top) => {
    card.getBoundingClientRect = () => ({ left, top, width: 100, height: 140 });
};
const makeHiddenInput = (name, value) => {
    const input = new FakeElement('input');
    input.setAttribute('type', 'hidden');
    input.setAttribute('name', name);
    input.setAttribute('value', String(value));
    return input;
};

const enemyTable = new FakeElement('ul', 'enemyBoards basic-mat table');
playerScreen.appendChild(enemyTable);
const enemyBoard = new FakeElement('li', 'enemyBoard');
enemyTable.appendChild(enemyBoard);
const enemyLanes = new FakeElement('ul', 'lanes');
enemyBoard.appendChild(enemyLanes);
const enemyLane = new FakeElement('li', 'lane Intelligence');
enemyLanes.appendChild(enemyLane);
const enemyCardRow = new FakeElement('ul', 'cardRow');
enemyCardRow.setAttribute('title', 'cards');
enemyLane.appendChild(enemyCardRow);
const enemyCard = new FakeElement('li', 'cardContainer faceDown');
enemyCard.setAttribute('tabindex', '0');
enemyCard.appendChild(makeHiddenInput('card_id', 900));
enemyCardRow.appendChild(enemyCard);
placeCard(enemyCard, 500, 60);

const playerTable = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(playerTable);
const playerBoard = new FakeElement('div', 'playerBoard');
playerTable.appendChild(playerBoard);
const lanesEl = new FakeElement('ul', 'lanes');
playerBoard.appendChild(lanesEl);

const playerLane = new FakeElement('li', 'lane Speed');
lanesEl.appendChild(playerLane);
const hologramRow = new FakeElement('ul', 'hologramRow');
playerLane.appendChild(hologramRow);
const cardRow = new FakeElement('ul', 'cardRow');
cardRow.setAttribute('title', 'cards');
playerLane.appendChild(cardRow);
const trustedRow = new FakeElement('ul', 'cardRow');
trustedRow.setAttribute('title', 'trustedCards');
playerLane.appendChild(trustedRow);

const fieldCard = new FakeElement('li', 'cardContainer faceDown');
fieldCard.setAttribute('tabindex', '0');
fieldCard.dataset.sourceLane = '2';
fieldCard.dataset.sourceOrdinal = '1';
fieldCard.appendChild(makeHiddenInput('card_id', 611));
fieldCard.appendChild(new FakeElement('div', 'card back smallCard'));
cardRow.appendChild(fieldCard);
placeCard(fieldCard, 10, 20);

const faceUpCard = new FakeElement('li', 'cardContainer');
faceUpCard.appendChild(makeHiddenInput('card_id', 612));
cardRow.appendChild(faceUpCard);
placeCard(faceUpCard, 300, 20);

const trustedCard = new FakeElement('li', 'cardContainer');
trustedCard.setAttribute('card_id', '550');
trustedCard.appendChild(makeHiddenInput('card_id', 550));
trustedRow.appendChild(trustedCard);
placeCard(trustedCard, 400, 60);

const deckHand = new FakeElement('div', 'deckHand handContainer');
playerTable.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const handList = new FakeElement('ul', 'hand');
handScroll.appendChild(handList);
const makeHandCard = (cardId, lane) => {
    const card = new FakeElement('li', 'cardContainer');
    card.setAttribute('tabindex', '0');
    card.setAttribute('draggable', 'true');
    card.dataset.sourceLane = '0';
    card.appendChild(makeHiddenInput('card_id', cardId));
    card.appendChild(makeHiddenInput('lane', lane));
    handList.appendChild(card);
    return card;
};
const handA = makeHandCard(201, 1);
const handB = makeHandCard(202, 2);
const handC = makeHandCard(203, 4);

const endTurnForm = new FakeElement('form', 'cardActionForm end-turn');
playerScreen.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) { return body.querySelector(selector); },
    querySelectorAll(selector) { return body.querySelectorAll(selector); },
    getElementById(id) {
        if (id === 'turnLimits') return turnLimits;
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) {
        (documentListeners[event] ??= []).push(handler);
    },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};
const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '0',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
    drawBlockedTitle: 'draw blocked',
    playBlockedTitle: 'play blocked',
    flipBlockedTitle: 'flip blocked',
};

let cookieWrites = 0;
Object.defineProperty(fakeDocument, 'cookie', {
    set() { cookieWrites += 1; },
    get() { return `writes:${cookieWrites}`; },
});

for (const el of [body, playerScreen, playerBoard, fieldCard, handA, handB, handC, endTurnForm, endTurnButton]) {
    el.focus = () => { fakeDocument.activeElement = el; };
    el.blur = () => { if (fakeDocument.activeElement === el) fakeDocument.activeElement = body; };
}

global.document = fakeDocument;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/MMM/game/1/board/1/action/' },
};
global.CSS = { escape: (value) => String(value) };
global.Element = function Element() {};
global.MutationObserver = function () {
    this.observe = () => {};
    this.disconnect = () => {};
};

const dragCode = __DRAG_JS__;
eval(dragCode);

(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const pressKey = (key) => {
    let prevented = false;
    const event = {
        key,
        repeat: false,
        target: fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};
const state = () => system.keyboardSelection;
const fieldCollection = () => system.control.navigator.focusableFieldCards();
const activeIs = (element) => fakeDocument.activeElement === element;
const collectorLacks = (card) => !fieldCollection().includes(card);

fakeDocument.activeElement = fieldCard;
assert('the face-down lane card turns ghostly without losing its flip tab stop',
    (() => {
        system.onFaceDownCardClick({ currentTarget: fieldCard, target: fieldCard }, 2);
        return fieldCard.classList.contains('ghost') && fieldCard.getAttribute('tabindex') === '0';
    })());
const flipHologram = hologramRow.children.filter(
    (el) => el.getAttribute('data-flip-for-card-id') === '611',
)[0];
assert('the lane flip renders a face-up ghost hologram', Boolean(flipHologram));
const flipClone = flipHologram.querySelector('.cardContainer');
assert('the face-up flip clone keeps no faceDown marker and no tab stop',
    flipClone.classList.contains('faceUp') && !flipClone.classList.contains('faceDown') &&
    flipClone.getAttribute('tabindex') === null);
assert('face-up and enemy cards stay outside the field focus collection',
    collectorLacks(flipClone) && collectorLacks(faceUpCard) &&
    collectorLacks(trustedCard) && collectorLacks(enemyCard));

fakeDocument.activeElement = handA;
assert('typing digit 1 opens a play preview for card A',
    pressKey('1') && state().selectedCard === handA && state().lanePreviewActive === true);
const previewClone = fakeDocument.querySelectorAll('.hologram.keyboard-preview .cardContainer')[0];
assert('the play preview is a face-up copy without a tab stop',
    previewClone && previewClone.classList.contains('faceUp') &&
    previewClone.getAttribute('tabindex') === null);

assert('Enter stages the play and spends the last play allowance',
    pressKey('Enter') && handA.classList.contains('ghost') && system.staged.plays === 1);
const stagedClone = fakeDocument.querySelectorAll(
    '.hologram.keyboard-staged .cardContainer',
)[0];
console.log('DEBUG stagedClone=', stagedClone ? 'yes' : 'no',
    stagedClone ? [...stagedClone.classes].join('|') : '',
    stagedClone ? stagedClone.getAttribute('data-staged-for-card-id') : '',
    stagedClone ? stagedClone.getAttribute('tabindex') : '',
    stagedClone ? stagedClone.classList.contains('faceDown') : '',
    stagedClone ? stagedClone.dataset.stagedForCardId : '');
assert('the staged lane copy links the played hand card id',
    stagedClone && stagedClone.parentNode.getAttribute('data-staged-for-card-id') === '201');
assert('the staged lane copy is a face-down copy with a tab stop',
    stagedClone.classList.contains('faceDown') && stagedClone.getAttribute('tabindex') === '0');
placeCard(stagedClone, 60, 20);
placeCard(flipClone, 200, 20);
stagedClone.focus = () => { fakeDocument.activeElement = stagedClone; };
stagedClone.blur = () => { if (fakeDocument.activeElement === stagedClone) fakeDocument.activeElement = body; };
assert('the played hand ghost keeps its tab stop once plays are exhausted',
    handA.getAttribute('tabindex') === '0' && !handA.classList.contains('blocked'));
assert('plain unplayed hand cards lose the tab stop while plays are blocked',
    handB.getAttribute('tabindex') === null && handB.classList.contains('blocked') &&
    handC.getAttribute('tabindex') === null && handC.classList.contains('blocked'));
assert('the keyboard order carries only the staged ghost',
    system.orderableKeyboardCards().length === 1 &&
    system.orderableKeyboardCards().includes(handA));
assert('face-down field cards stay in the focus collection with flips blocked',
    fieldCollection().includes(fieldCard) && fieldCollection().includes(stagedClone));
const guardCookieWrites = cookieWrites;

fakeDocument.activeElement = stagedClone;
assert('ArrowDown from the field focuses the played ghost without selecting it',
    pressKey('ArrowDown') && activeIs(handA) && state().selectedCard === null &&
    state().ghostFlip === false && state().digitBuffer === '');
assert('ghost focus with no flips left writes no flip cookie', cookieWrites === guardCookieWrites);
pressKey('Enter');
assert('Enter on the focused ghost starts no flip selection or mutation without flips',
    state().selectedCard === null && state().digitBuffer === '' &&
    cookieWrites === guardCookieWrites && activeIs(handA));
assert('ArrowRight from the lone ghost exits to the end turn button',
    pressKey('ArrowRight') && activeIs(endTurnButton) && state().selectedCard === null);
assert('ArrowUp from end turn refocuses the played ghost without selecting it',
    pressKey('ArrowUp') && activeIs(handA) && state().selectedCard === null &&
    state().digitBuffer === '' && cookieWrites === guardCookieWrites);

fakeDocument.activeElement = handA;
assert('ArrowUp from the hand reaches the blocked face-down field card',
    pressKey('ArrowUp') && activeIs(fieldCard) && state().selectedCard === null);
assert('Enter on the blocked face-down card flips nothing',
    !pressKey('Enter') && cookieWrites === guardCookieWrites &&
    hologramRow.children.filter(
        (el) => el.getAttribute('data-flip-for-card-id') === '611',
    ).length === 1);

fakeDocument.activeElement = fieldCard;
assert('field ArrowRight steps onto the face-down staged copy',
    pressKey('ArrowRight') && activeIs(stagedClone));
fakeDocument.activeElement = stagedClone;
assert('field ArrowRight stops before face-up, trusted and enemy cards',
    !pressKey('ArrowRight') && activeIs(stagedClone));
fakeDocument.activeElement = stagedClone;
assert('field ArrowLeft steps back to the face-down lane card',
    pressKey('ArrowLeft') && activeIs(fieldCard));
fakeDocument.activeElement = fieldCard;
assert('field ArrowLeft from the leftmost face-down card is a boundary no-op',
    !pressKey('ArrowLeft') && activeIs(fieldCard) && state().selectedCard === null);

console.log('zero allowance focusability ok');
'''.replace('__DRAG_JS__', repr(drag_js))

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping zero allowance focusability test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping zero allowance focusability test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'zero allowance focusability harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('zero allowance focusability ok', completed.stdout)


def _extract_js_brace_block(source, opener):
    """Return source from opener through its balanced closing brace."""
    start = source.index(opener)
    depth = 0
    for index in range(source.index('{', start), len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise ValueError(f"Unbalanced braces after {opener!r}")


class ChallengeFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = []
        self.labels = []
        self.input_end_tags = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input":
            self.inputs.append(attributes)
        elif tag == "label":
            self.labels.append(attributes)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "input":
            self.input_end_tags.append(tag)


class ChallengePageTests(TestCase):
    radio_names = ("challengePlayer", "startingDeck", "startingCard")

    def _create_form_fixture(self, saved_decks):
        challenger = Player.objects.create(name="Challenger")
        opponents = [
            Player.objects.create(name="Opponent One"),
            Player.objects.create(name="Opponent Two"),
        ]
        owner_history = CardOwnerHistory.objects.create(cardOwner=challenger)
        cards = []
        for index in range(2):
            card = Card.objects.create(
                title=f"Starting card {index + 1}",
                artSource="static" if index == 0 else "",
                cardType=index,
            )
            card.ownerHistory.add(owner_history)
            cards.append(card)

        for index, opponent in enumerate(opponents):
            opponent_history = CardOwnerHistory.objects.create(cardOwner=opponent)
            opponent_card = Card.objects.create(
                title=f"Opponent card {index + 1}",
                artSource="",
                cardType=0,
            )
            opponent_card.ownerHistory.add(opponent_history)

        decks = []
        if saved_decks:
            decks = [
                Deck.create(
                    challenger.id,
                    deckTitle="First deck",
                    newDescription="first deck description",
                    newDeckCards=[cards[0]],
                ),
                Deck.create(
                    challenger.id,
                    deckTitle="Second deck",
                    newDescription="second deck description",
                    newDeckCards=cards,
                ),
            ]

        response = self.client.get(reverse("MMM:createGame", args=[challenger.id]))
        return response, challenger, opponents, cards, decks

    def _parse_form(self, response):
        parser = ChallengeFormParser()
        parser.feed(response.content.decode())
        parser.close()
        return parser

    def _radio_groups(self, parser):
        return {
            name: [
                attributes
                for attributes in parser.inputs
                if attributes.get("type") == "radio"
                and attributes.get("name") == name
            ]
            for name in self.radio_names
        }

    def _assert_valid_radio_form(self, response):
        content = response.content.decode()
        parser = self._parse_form(response)
        self.assertNotIn("</input>", content)
        self.assertEqual(parser.input_end_tags, [])

        radio_inputs = [
            attributes
            for attributes in parser.inputs
            if attributes.get("type") == "radio"
        ]
        radio_ids = [attributes["id"] for attributes in radio_inputs]
        label_for_values = [attributes.get("for") for attributes in parser.labels]
        self.assertEqual(sorted(radio_ids), sorted(label_for_values))
        self.assertEqual(len(radio_ids), len(set(radio_ids)))

        groups = self._radio_groups(parser)
        for name, options in groups.items():
            self.assertTrue(options, f"missing {name} radio group")
            self.assertEqual(
                sum("checked" in option for option in options),
                1,
                f"expected one checked {name} option",
            )
            self.assertIn("checked", options[0])
            self.assertTrue(all("required" in option for option in options))
        return parser, groups

    def _form_data(self, parser, selected_values=None):
        selected_values = selected_values or {}
        form_data = {
            attributes["name"]: attributes["value"]
            for attributes in parser.inputs
            if attributes.get("name") in {"newGameIdValue", "challenger"}
        }
        groups = self._radio_groups(parser)
        for name, options in groups.items():
            selected_value = selected_values.get(name)
            selected_option = next(
                (
                    option
                    for option in options
                    if option.get("value") == selected_value
                ),
                next(option for option in options if "checked" in option),
            )
            form_data[name] = selected_option["value"]
        return form_data

    def test_existing_deck_form_defaults_and_submits_through_initialize_game(self):
        response, challenger, opponents, cards, decks = self._create_form_fixture(
            saved_decks=True
        )
        parser, groups = self._assert_valid_radio_form(response)

        self.assertIn("staticCard", response.content.decode())
        self.assertEqual(len(groups["startingDeck"]), len(decks))
        form_data = self._form_data(parser)
        game_id = int(form_data["newGameIdValue"])

        initialize_response = self.client.post(
            reverse("MMM:initializeGame"), form_data
        )

        self.assertRedirects(
            initialize_response,
            reverse("MMM:viewGameAsPlayer", args=[game_id, challenger.id]),
        )
        human_participant = BattleParticipant.objects.get(
            player_id=challenger.id,
            battles__game__id=game_id,
        )
        self.assertEqual(human_participant.startingCard_id, cards[0].id)
        self.assertEqual(human_participant.deck_id, decks[0].id)
        self.assertTrue(
            BattleParticipant.objects.filter(
                player_id=opponents[0].id,
                battles__game__id=game_id,
            ).exists()
        )

    def test_challenge_form_posts_replacement_radio_options(self):
        response, challenger, opponents, cards, decks = self._create_form_fixture(
            saved_decks=True
        )
        parser, groups = self._assert_valid_radio_form(response)
        selected_values = {
            "challengePlayer": groups["challengePlayer"][1]["value"],
            "startingDeck": groups["startingDeck"][1]["value"],
            "startingCard": groups["startingCard"][1]["value"],
        }
        form_data = self._form_data(parser, selected_values)
        game_id = int(form_data["newGameIdValue"])

        initialize_response = self.client.post(
            reverse("MMM:initializeGame"), form_data
        )

        self.assertRedirects(
            initialize_response,
            reverse("MMM:viewGameAsPlayer", args=[game_id, challenger.id]),
        )
        human_participant = BattleParticipant.objects.get(
            player_id=challenger.id,
            battles__game__id=game_id,
        )
        self.assertEqual(human_participant.startingCard_id, cards[1].id)
        self.assertEqual(human_participant.deck_id, decks[1].id)
        self.assertTrue(
            BattleParticipant.objects.filter(
                player_id=opponents[1].id,
                battles__game__id=game_id,
            ).exists()
        )

    def test_new_deck_fallback_is_checked_and_submits_through_initialize_game(self):
        response, challenger, opponents, cards, decks = self._create_form_fixture(
            saved_decks=False
        )
        parser, groups = self._assert_valid_radio_form(response)

        self.assertEqual(len(decks), 0)
        self.assertEqual(groups["startingDeck"][0]["id"], "startingDeckNew")
        self.assertEqual(groups["startingDeck"][0]["value"], "New")
        form_data = self._form_data(parser)
        game_id = int(form_data["newGameIdValue"])

        initialize_response = self.client.post(
            reverse("MMM:initializeGame"), form_data
        )

        self.assertRedirects(
            initialize_response,
            reverse("MMM:viewGameAsPlayer", args=[game_id, challenger.id]),
        )
        human_participant = BattleParticipant.objects.get(
            player_id=challenger.id,
            battles__game__id=game_id,
        )
        new_deck = human_participant.deck
        self.assertEqual(new_deck.cards.count(), len(cards))
        self.assertEqual(human_participant.startingCard_id, cards[0].id)
        self.assertTrue(
            BattleParticipant.objects.filter(
                player_id=opponents[0].id,
                battles__game__id=game_id,
            ).exists()
        )


class PlayerPageTests(TestCase):
    def _create_owned_card(self, player, title, card_type=0, art_source="", acquired_at=None):
        owner_history = CardOwnerHistory.objects.create(
            cardOwner=player,
            aquiredAt=acquired_at or timezone.now(),
        )
        card = Card.objects.create(
            title=title,
            artSource=art_source,
            cardType=card_type,
        )
        card.ownerHistory.add(owner_history)
        return card, owner_history

    def _collection_card_ids(self, response):
        return [
            int(card_id)
            for card_id in re.findall(
                r'href="[^\"]*/card/(\d+)/"',
                response.content.decode(),
            )
        ]

    def _create_challenge(self, challenger_name="Meg", include_opponent=True):
        challenger = Player.objects.create(name=challenger_name)
        card = Card.objects.create(title="Loot card", artSource="", cardType=0)
        deck = Deck.objects.create(
            title="Challenger deck",
            description="test deck",
            player=challenger,
        )
        challenger_participant = BattleParticipant.objects.create(
            player=challenger,
            startingCard=card,
            deck=deck,
            fled=False,
            defeated=False,
            computerControlled=False,
        )
        history = BattleHistory.objects.create(challenger=challenger)
        history.participants.add(challenger_participant)
        history.lootPile.add(card)
        game = Game.objects.create(title="Challenge game", history=history)

        if include_opponent:
            opponent = Player.objects.create(name="Opponent")
            opponent_deck = Deck.objects.create(
                title="Opponent deck",
                description="test deck",
                player=opponent,
            )
            opponent_participant = BattleParticipant.objects.create(
                player=opponent,
                startingCard=card,
                deck=opponent_deck,
                fled=False,
                defeated=False,
                computerControlled=True,
            )
            history.participants.add(opponent_participant)

        return challenger, history, game

    def test_player_page_uses_name_appropriate_possessives(self):
        lucas = Player.objects.create(name="Lucas")
        meg = Player.objects.create(name="Meg")
        uppercase = Player.objects.create(name="MARS")

        lucas_response = self.client.get(reverse("MMM:viewPlayer", args=[lucas.id]))
        meg_response = self.client.get(reverse("MMM:viewPlayer", args=[meg.id]))
        uppercase_response = self.client.get(
            reverse("MMM:viewPlayer", args=[uppercase.id])
        )

        self.assertContains(lucas_response, "<h1>Lucas' page</h1>")
        self.assertContains(meg_response, "<h1>Meg's page</h1>")
        self.assertContains(uppercase_response, "<h1>MARS' page</h1>")
        self.assertContains(lucas_response, 'alt="Lucas\'s profile picture"')
        self.assertContains(meg_response, 'alt="Meg\'s profile picture"')

    def test_player_profile_alt_text_is_escaped_without_changing_name(self):
        player = Player.objects.create(name="O'Reilly & Co")

        response = self.client.get(reverse("MMM:viewPlayer", args=[player.id]))

        self.assertContains(
            response,
            'alt="O&#39;Reilly &amp; Co\'s profile picture"',
        )
        self.assertContains(response, "Welcome O&#39;Reilly &amp; Co")

    def test_challenge_card_is_one_keyboard_link_with_valid_metadata_markup(self):
        challenger, history, game = self._create_challenge()

        response = self.client.get(reverse("MMM:viewPlayer", args=[challenger.id]))
        content = response.content.decode()

        expected_url = reverse("MMM:viewBoard", args=[game.id, challenger.id])
        self.assertContains(
            response,
            f'<a class="challenge-card-link" href="{expected_url}" draggable="false">',
        )
        self.assertContains(response, '<li class="challenge-card">')
        self.assertContains(response, '<h3 class="challenge-card-title">Game 1</h3>')
        self.assertContains(
            response,
            'class="challenge-card-subtitle challenge-card-meta"',
        )
        self.assertContains(
            response,
            'challenge-card-loot">lootPile: Loot card</p>',
        )
        self.assertContains(response, "(Started ")
        self.assertContains(response, "Meg")
        self.assertContains(response, "versus")
        self.assertContains(response, "Opponent")
        self.assertNotContains(response, "challenge-result-badge")

        challenge_link = re.search(
            r'<a class="challenge-card-link"[^>]*>(.*?)</a>',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(challenge_link)
        self.assertNotIn("<a", challenge_link.group(1))

        participant_list = re.search(
            r'<ul class="challenge-participants">(.*?)</ul>',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(participant_list)
        self.assertNotIn("<p", participant_list.group(1))
        self.assertEqual(
            len(re.findall(r"<li(?:\s|>)", participant_list.group(1))),
            history.participants.count() + 1,
        )

    def test_finished_challenge_shows_result_badge_and_links_to_board(self):
        winner, winner_history, winner_game = self._create_challenge(
            challenger_name="Winnie"
        )
        loser, loser_history, loser_game = self._create_challenge(
            challenger_name="Loes"
        )
        fleer, fleer_history, fleer_game = self._create_challenge(
            challenger_name="Vlinder"
        )

        winner_opponent = winner_history.participants.exclude(
            player_id=winner.id
        ).get()
        winner_opponent.defeated = True
        winner_opponent.save()

        loser_own_participant = loser_history.participants.get(player_id=loser.id)
        loser_own_participant.defeated = True
        loser_own_participant.save()

        fleer_own_participant = fleer_history.participants.get(player_id=fleer.id)
        fleer_own_participant.fled = True
        fleer_own_participant.save()

        for challenger, game, result_class, result_label in (
            (winner, winner_game, "won", "Won"),
            (loser, loser_game, "lost", "Lost"),
            (fleer, fleer_game, "fled", "Fled"),
        ):
            response = self.client.get(reverse("MMM:viewPlayer", args=[challenger.id]))
            self.assertContains(
                response,
                '<a class="challenge-card-link" '
                f'href="{reverse("MMM:viewBoard", args=[game.id, challenger.id])}" '
                'draggable="false">',
            )
            self.assertContains(
                response,
                'class="challenge-result-badge '
                f'challenge-result--{result_class}">{result_label}</span>',
            )
            for absent_class in {"won", "lost", "fled"} - {result_class}:
                self.assertNotContains(response, f"challenge-result--{absent_class}")

    def test_player_page_keeps_empty_challenge_participant_state(self):
        challenger, _, _ = self._create_challenge(include_opponent=False)
        empty_history = BattleHistory.objects.create(challenger=challenger)
        empty_game = Game.objects.create(title="Empty challenge", history=empty_history)

        response = self.client.get(reverse("MMM:viewPlayer", args=[challenger.id]))

        self.assertContains(response, "No participants")
        self.assertContains(response, f"game/{empty_game.id}/{challenger.id}")

    def test_challenge_card_styles_cover_stacking_hover_and_focus(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), "..", "var", "www", "static")
        with open(os.path.join(static_dir, "style.css")) as css_file:
            style_css = css_file.read()

        challenge_block = style_css[
            style_css.index(".players .challenge-list"):
            style_css.index(".playerOptions")
        ]

        self.assertIn(".challenge-card-link {", challenge_block)
        self.assertIn("display: block;", challenge_block)
        self.assertIn(".challenge-card-link:hover", challenge_block)
        self.assertIn(".challenge-card-link:focus-visible", challenge_block)
        self.assertIn("padding: 0.5rem 0.75rem;", challenge_block)
        self.assertIn("gap: 0.4rem;", challenge_block)
        self.assertIn("flex-direction: row;", challenge_block)
        self.assertIn("flex-wrap: wrap;", challenge_block)
        self.assertIn("line-height: 1.2;", challenge_block)
        self.assertIn("overflow-wrap: anywhere;", challenge_block)
        self.assertIn(".challenge-participants", challenge_block)
        self.assertIn(".challenge-result-badge {", challenge_block)
        self.assertIn("font-weight: 700;", challenge_block)
        self.assertIn(".challenge-result--won", challenge_block)
        self.assertIn(".challenge-result--lost", challenge_block)
        self.assertIn(".challenge-result--fled", challenge_block)

    def test_owned_cards_sort_by_case_insensitive_name_with_static_titles(self):
        player = Player.objects.create(name="Collector")
        static_card, _ = self._create_owned_card(
            player,
            "Zulu of Clubs",
            art_source="static",
        )
        image_card, _ = self._create_owned_card(
            player,
            "alpha image",
            art_source="cards/alpha.jpg",
        )
        middle_card, _ = self._create_owned_card(player, "Bravo", art_source="")

        response = self.client.get(
            reverse("MMM:viewPlayer", args=[player.id]) + "?sort=name"
        )

        self.assertEqual(
            self._collection_card_ids(response),
            [image_card.id, middle_card.id, static_card.id],
        )
        self.assertContains(response, "staticCard")
        self.assertContains(response, f"card/{static_card.id}/")
        self.assertContains(response, f"card/{image_card.id}/")

    def test_owned_cards_sort_by_numeric_card_type_then_name(self):
        player = Player.objects.create(name="Collector")
        cards = [
            self._create_owned_card(player, "Resolve", card_type=3)[0],
            self._create_owned_card(player, "Intelligence", card_type=0)[0],
            self._create_owned_card(player, "Viciousness", card_type=2)[0],
            self._create_owned_card(player, "Speed", card_type=1)[0],
        ]

        response = self.client.get(
            reverse("MMM:viewPlayer", args=[player.id]) + "?sort=type"
        )

        self.assertEqual(
            self._collection_card_ids(response),
            [cards[1].id, cards[3].id, cards[2].id, cards[0].id],
        )

    def test_owned_cards_date_sort_uses_latest_current_player_acquisition(self):
        player = Player.objects.create(name="Collector")
        other_player = Player.objects.create(name="Former owner")
        now = timezone.now()
        early = now - timedelta(days=30)
        late = now - timedelta(days=2)
        transferred_at = now - timedelta(days=1)

        older_card, early_history = self._create_owned_card(
            player,
            "Older card",
            acquired_at=early,
        )
        newer_card, _ = self._create_owned_card(
            player,
            "Newer card",
            acquired_at=late,
        )
        newer_card.ownerHistory.add(early_history)

        transferred_card, _ = self._create_owned_card(
            player,
            "Transferred card",
            acquired_at=early,
        )
        other_history = CardOwnerHistory.objects.create(
            cardOwner=other_player,
            aquiredAt=transferred_at,
        )
        transferred_card.ownerHistory.add(other_history)

        response = self.client.get(
            reverse("MMM:viewPlayer", args=[player.id]) + "?sort=date"
        )

        self.assertEqual(
            self._collection_card_ids(response),
            [newer_card.id, older_card.id],
        )
        self.assertNotContains(response, f"card/{transferred_card.id}/")

    def test_default_and_invalid_owned_card_sort_keep_default_order_and_links(self):
        player, _, game = self._create_challenge()
        first_card, _ = self._create_owned_card(player, "Zulu")
        second_card, _ = self._create_owned_card(player, "Alpha")
        player_url = reverse("MMM:viewPlayer", args=[player.id])

        default_response = self.client.get(player_url)
        invalid_response = self.client.get(player_url + "?sort=unsupported")

        self.assertEqual(
            self._collection_card_ids(default_response),
            [first_card.id, second_card.id],
        )
        self.assertEqual(
            self._collection_card_ids(invalid_response),
            [first_card.id, second_card.id],
        )
        self.assertContains(
            default_response,
            'class="collection-sort-control is-active"',
        )
        self.assertContains(default_response, f'href="{player_url}"')
        self.assertContains(
            default_response,
            'aria-current="true">Default',
        )
        for sort_key, label in (
            ("name", "Name"),
            ("type", "Type"),
            ("date", "Date achieved"),
        ):
            self.assertContains(
                default_response,
                f'href="{player_url}?sort={sort_key}"',
            )
            self.assertContains(default_response, label)
            sorted_response = self.client.get(player_url + f"?sort={sort_key}")
            self.assertContains(
                sorted_response,
                'class="collection-sort-control is-active"',
            )
            self.assertContains(sorted_response, f'aria-current="true">{label}')
        self.assertContains(
            invalid_response,
            f'href="{player_url}?sort=name"',
        )
        self.assertContains(
            invalid_response,
            f"game/{game.id}/board/{player.id}",
        )
        self.assertContains(
            invalid_response,
            f"card/{first_card.id}/",
        )

    def test_owned_card_sort_controls_have_responsive_focus_and_active_styles(self):
        import os

        style_path = os.path.join(
            os.path.dirname(__file__), "..", "var", "www", "static", "style.css"
        )
        with open(style_path) as css_file:
            style_css = css_file.read()

        self.assertIn(".owned-cards-heading", style_css)
        self.assertIn("flex-wrap: wrap", style_css)
        self.assertIn(".collection-sort-control:focus-visible", style_css)
        self.assertIn('.collection-sort-control[aria-current="true"]', style_css)


class SpecialTimelineTests(TestCase):
    """Unit tests for the special draw sequence timeline construction."""

    def setUp(self):
        self.human = Player.objects.create(name="Human")
        self.bot = Player.objects.create(name="Bot")

        human_owner = CardOwnerHistory.objects.create(cardOwner=self.human)
        bot_owner = CardOwnerHistory.objects.create(cardOwner=self.bot)

        # Create enough cards for testing (need more than default deck for shuffle tests)
        self.human_cards = [
            Card.objects.create(title=f"H-{i}", artSource="", cardType=i % 4)
            for i in range(12)
        ]
        for card in self.human_cards:
            card.ownerHistory.add(human_owner)

        self.bot_cards = [
            Card.objects.create(title=f"B-{i}", artSource="", cardType=i % 4)
            for i in range(12)
        ]
        for card in self.bot_cards:
            card.ownerHistory.add(bot_owner)

        self.human_deck = Deck.create(
            self.human.id, deckTitle="HD", newDescription="", newDeckCards=self.human_cards,
        )
        self.bot_deck = Deck.create(
            self.bot.id, deckTitle="BD", newDescription="", newDeckCards=self.bot_cards,
        )

        history = BattleHistory.objects.create(challenger=self.human)
        self.game = Game.objects.create(title="Test", history=history, roundNumber=0)
        self.human_participant = history.addHumanChallenger(
            challengerPlayer_id=self.human.id,
            startingCard_id=self.human_cards[0].id,
            deck_id=self.human_deck.id,
        )
        self.bot_participant = history.addRobotChallenger(
            challengerPlayer_id=self.bot.id,
            startingCard_id=self.bot_cards[0].id,
            deck_id=self.bot_deck.id,
        )

        # Confirm the challenge to initialize game state (creates GameCards)
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)

    def _reset_all_cards_to_deck(self, participant=None):
        """Move all of a participant's cards back to the deck."""
        if participant is None:
            participant = self.human_participant
        for gc in GameCard.objects.filter(game_id=self.game.id, user_id=participant.id):
            gc.state.reset()
            gc.state.save()

    def test_build_shuffle_step_excludes_trusted_and_facedown(self):
        """Verify shuffle-back step only includes untrusted face-up + hand cards."""
        from MMM.special_timeline import build_shuffle_step

        self._reset_all_cards_to_deck()
        gc = GameCard.objects.filter(game_id=self.game.id, user_id=self.human_participant.id)
        cards = list(gc)

        # Need at least 4 cards; starting card is in a lane, others are in deck
        self.assertGreaterEqual(len(cards), 4)

        # Cards start in deck. Draw them to hand first, then play to lanes.
        cards[0].state.draw()
        cards[0].state.updateOrdinal(1)
        cards[0].state.save()

        cards[1].state.draw()
        cards[1].state.updateOrdinal(2)
        cards[1].state.save()

        cards[2].state.draw()
        cards[2].state.updateOrdinal(3)
        cards[2].state.save()

        cards[3].state.draw()
        cards[3].state.updateOrdinal(4)
        cards[3].state.save()

        # Now play cards from hand to lanes
        # Card 0 stays in hand (already drawn above)

        # Card 1: face-up untrusted in lane 1
        cards[1].state.play(1)
        cards[1].state.reveal()
        cards[1].state.updateOrdinal(1)
        cards[1].state.save()

        # Card 2: face-up trusted in lane 2
        cards[2].state.play(2)
        cards[2].state.reveal()
        cards[2].state.trust()
        cards[2].state.updateOrdinal(1)
        cards[2].state.save()

        # Card 3: face-down untrusted in lane 3
        cards[3].state.play(3)
        cards[3].state.updateOrdinal(1)
        cards[3].state.save()  # faceDown=True by default

        steps = build_shuffle_step(self.human_participant)
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step["kind"], "shuffle-back")

        affected_ids = [c["cardId"] for c in step["affectedCards"]]
        # Card 0 (hand) should be included
        self.assertIn(cards[0].id, affected_ids)
        # Card 1 (face-up untrusted) should be included
        self.assertIn(cards[1].id, affected_ids)
        # Card 2 (trusted) should NOT be included
        self.assertNotIn(cards[2].id, affected_ids)
        # Card 3 (face-down) should NOT be included
        self.assertNotIn(cards[3].id, affected_ids)

    def test_build_int_timeline_structure(self):
        """Verify intSpecial produces correct timeline steps."""
        from MMM.special_timeline import build_int_timeline

        self._reset_all_cards_to_deck()
        gc = GameCard.objects.filter(game_id=self.game.id, user_id=self.human_participant.id)
        cards = list(gc)

        # Draw some cards to hand
        cards[1].state.draw()
        cards[1].state.updateOrdinal(1)
        cards[1].state.save()
        cards[2].state.draw()
        cards[2].state.updateOrdinal(2)
        cards[2].state.save()

        timeline = []
        build_int_timeline(self.human_participant, 3, timeline)

        self.assertGreaterEqual(len(timeline), 2)
        # Step 0 should be special-trigger
        self.assertEqual(timeline[0]["kind"], "special-trigger")
        self.assertIn("enacts master plan", timeline[0]["banner"])
        self.assertEqual(timeline[0]["lane"], 1)  # Intelligence lane

        # Should have card-effect steps
        card_effect_steps = [s for s in timeline if s["kind"] == "card-effect"]
        self.assertGreaterEqual(len(card_effect_steps), 1)

        # Verify each step has correct participantId
        for step in timeline:
            self.assertEqual(step["participantId"], self.human_participant.id)

    def test_build_res_timeline_structure(self):
        """Verify resSpecial produces correct timeline steps."""
        from MMM.special_timeline import build_res_timeline

        self._reset_all_cards_to_deck()
        gc = GameCard.objects.filter(game_id=self.game.id, user_id=self.human_participant.id)
        cards = list(gc)

        # Draw cards to hand first, then play to Resolve lane
        cards[1].state.draw()
        cards[1].state.updateOrdinal(1)
        cards[1].state.save()
        cards[2].state.draw()
        cards[2].state.updateOrdinal(2)
        cards[2].state.save()

        cards[1].state.play(4)
        cards[1].state.reveal()
        cards[1].state.updateOrdinal(1)
        cards[1].state.save()
        cards[2].state.play(4)
        cards[2].state.reveal()
        cards[2].state.updateOrdinal(2)
        cards[2].state.save()

        timeline = []
        build_res_timeline(self.human_participant, 2, timeline)

        self.assertGreaterEqual(len(timeline), 2)
        # Step 0: special-trigger
        self.assertEqual(timeline[0]["kind"], "special-trigger")
        self.assertIn("holds and trusts", timeline[0]["banner"])
        self.assertEqual(timeline[0]["lane"], 4)  # Resolve lane

        # Step 1+: card-effect with trust flag
        card_effect_steps = [s for s in timeline if s["kind"] == "card-effect"]
        self.assertGreaterEqual(len(card_effect_steps), 1)
        for step in card_effect_steps:
            for c in step["affectedCards"]:
                self.assertTrue(c["trust"])

    def test_build_spd_timeline_rush_down(self):
        """Verify spdSpecial rush-down produces trigger step."""
        from MMM.special_timeline import build_spd_timeline

        opponent = self.bot_participant
        timeline = []
        result = build_spd_timeline(
            self.human_participant, 5, 10, opponent, timeline
        )

        # Rush down: result is empty
        self.assertEqual(result, "")
        self.assertGreaterEqual(len(timeline), 1)
        self.assertEqual(timeline[0]["kind"], "special-trigger")
        self.assertIn("rushes down", timeline[0]["banner"])
        self.assertEqual(timeline[0]["lane"], 2)  # Speed lane

    def test_build_spd_timeline_flee(self):
        """Verify spdSpecial flee produces trigger + participant-effect."""
        from MMM.special_timeline import build_spd_timeline, PARTICIPANT_EFFECT

        # Opponent has higher power but lower speed — we need to structure
        # stats so that power < opponentPower but speed > opponentSpd
        # Give opponent many cards to make opponentPower high
        gc = GameCard.objects.filter(game_id=self.game.id, user_id=self.bot_participant.id)
        for g in gc:
            g.state.reset()
            g.state.draw()
            g.state.save()
        for g in gc:
            g.state.play(1)
            g.state.reveal()
            g.state.save()

        opponent = self.bot_participant
        timeline = []
        result = build_spd_timeline(
            self.human_participant, 10, 0, opponent, timeline
        )

        # Flee: result contains "fled"
        self.assertIn("fled", result)
        self.assertGreaterEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["kind"], "special-trigger")
        self.assertIn("flees", timeline[0]["banner"])
        # Should have a participant-effect step
        participant_effects = [s for s in timeline if s["kind"] == PARTICIPANT_EFFECT]
        self.assertGreaterEqual(len(participant_effects), 1)

    def test_build_spd_timeline_fail_flee(self):
        """Verify spdSpecial fail produces only trigger step."""
        from MMM.special_timeline import build_spd_timeline, PARTICIPANT_EFFECT

        # Give opponent many cards so opponentPower is high and opponentSpd is high
        gc = GameCard.objects.filter(game_id=self.game.id, user_id=self.bot_participant.id)
        for g in gc:
            g.state.reset()
            g.state.draw()
            g.state.save()
        for idx, g in enumerate(gc):
            lane = (idx % 4) + 1
            g.state.play(lane)
            g.state.reveal()
            g.state.save()

        opponent = self.bot_participant
        timeline = []
        result = build_spd_timeline(
            self.human_participant, 0, 0, opponent, timeline
        )

        # Fail flee: result is empty string
        self.assertEqual(result, "")
        self.assertGreaterEqual(len(timeline), 1)
        self.assertEqual(timeline[0]["kind"], "special-trigger")
        self.assertIn("fails to flee", timeline[0]["banner"])
        # No participant-effect
        participant_effects = [s for s in timeline if s["kind"] == PARTICIPANT_EFFECT]
        self.assertEqual(len(participant_effects), 0)

    def test_build_vis_timeline_no_resolve_card(self):
        """Verify visSpecial drain produces trigger + self-defeat."""
        from MMM.special_timeline import build_vis_timeline, PARTICIPANT_EFFECT

        self._reset_all_cards_to_deck()
        gc = GameCard.objects.filter(game_id=self.game.id, user_id=self.human_participant.id)
        cards = list(gc)
        # Move cards to lanes but ensure none are in lane 4 (Resolve) face-up
        for g in cards:
            if g.state.lane == 4 and not g.state.faceDown:
                g.state.trust()
                g.state.save()

        opponent = self.bot_participant
        timeline = []
        result = build_vis_timeline(self.human_participant, 5, opponent, timeline)

        # Drain
        self.assertIn("drains", result)
        self.assertGreaterEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["kind"], "special-trigger")
        self.assertEqual(timeline[0]["lane"], 3)  # Viciousness

        participant_effects = [s for s in timeline if s["kind"] == PARTICIPANT_EFFECT]
        self.assertGreaterEqual(len(participant_effects), 1)

    def test_build_vis_timeline_win_outcome_after_resolve_trusted(self):
        """A successful vis attack must NOT read as a resolve drain.

        visSpecial trusts the resolve card before building the timeline, so
        re-deriving the outcome from trustable cards would report the drain
        banner. The explicit outcome/trusted-card arguments must win.
        """
        from MMM.special_timeline import (
            build_vis_timeline,
            PARTICIPANT_EFFECT,
        )

        # Give the human a face-up untrusted resolve card and trust it
        # (exactly what visSpecial does before recording the timeline).
        self._reset_all_cards_to_deck()
        gc = list(GameCard.objects.filter(
            game_id=self.game.id, user_id=self.human_participant.id
        ))
        resolve_card = gc[0]
        resolve_card.state.draw()
        resolve_card.state.play(4)
        resolve_card.state.reveal()
        resolve_card.state.updateOrdinal(1)
        resolve_card.state.save()
        resolve_card.state.trust()
        resolve_card.state.save()

        opponent = self.bot_participant
        timeline = []
        result = build_vis_timeline(
            self.human_participant, 5, opponent, timeline,
            outcome="win",
            trusted_res_card=resolve_card,
        )

        self.assertIn("attacks and defeats", result)
        self.assertNotIn("drains", result)
        self.assertGreaterEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["kind"], "special-trigger")
        self.assertIn("attacks and defeats", timeline[0]["banner"])

        participant_effects = [s for s in timeline if s["kind"] == PARTICIPANT_EFFECT]
        self.assertGreaterEqual(len(participant_effects), 1)
        # The defeated participant is the OPPONENT, never the attacker.
        self.assertEqual(participant_effects[0]["defeatedParticipantId"], opponent.id)
        self.assertIsNone(participant_effects[0]["fledParticipantId"])

    def test_vis_special_win_defeats_opponent_and_records_attack_timeline(self):
        """End-to-end: winning via viciousness must not read as a resolve drain."""
        from MMM.battle_services import run_vis_special

        # Human: one face-up untrusted resolve card to spend.
        self._reset_all_cards_to_deck()
        gc = list(GameCard.objects.filter(
            game_id=self.game.id, user_id=self.human_participant.id
        ))
        resolve_card = gc[0]
        resolve_card.state.draw()
        resolve_card.state.play(4)
        resolve_card.state.reveal()
        resolve_card.state.updateOrdinal(1)
        resolve_card.state.save()

        timeline = []
        result = run_vis_special(self.human_participant, 5, timeline=timeline)

        # The human had resolve, so the attack succeeds and the OPPONENT loses.
        self.assertIn("attacks and defeats", result)
        self.assertNotIn("drains", result)
        self.human_participant.refresh_from_db()
        self.bot_participant.refresh_from_db()
        self.assertTrue(self.bot_participant.defeated)
        self.assertFalse(self.human_participant.defeated)

        banners = [step.get("banner", "") for step in timeline]
        self.assertTrue(any("attacks and defeats" in banner for banner in banners))
        self.assertFalse(any("drains" in banner for banner in banners))

    def test_normal_draw_produces_no_timeline(self):
        """Verify drawing a card normally (deck not emptied) produces no timeline."""
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.post(draw_url, {"action": "draw"})

        # Normal draw should not have timeline script tag
        self.assertNotContains(response, 'id="timelineSteps"')

    def test_timeline_steps_are_json_serializable(self):
        """Verify timeline steps are plain dicts (JSON-serializable)."""
        import json
        from MMM.special_timeline import (
            build_trigger_step, build_card_effect_step,
            build_participant_effect_step, build_shuffle_step,
        )

        step = build_trigger_step(self.human_participant, "test banner", 1)
        json_str = json.dumps(step)
        self.assertIn("test banner", json_str)

        affected = [{"cardId": 1, "sourceLane": 0, "sourceOrdinal": 1, "destinationLane": 1, "destinationOrdinal": 1, "flipFaceUp": True, "trust": False}]
        step2 = build_card_effect_step(self.human_participant, affected)
        json_str2 = json.dumps(step2)
        self.assertIn("card-effect", json_str2)

        step3 = build_participant_effect_step(self.human_participant, "defeated", defeated_id=1)
        json_str3 = json.dumps(step3)
        self.assertIn("defeated", json_str3)

        step4 = build_shuffle_step(self.human_participant)
        json_str4 = json.dumps(step4)
        self.assertIn("shuffle-back", json_str4)

    def test_int_special_via_views_produces_card_effects(self):
        """Verify intSpecial (from views.py) produces card-effect steps after playCard.

        This tests the real flow: draw last card -> specialActions -> intSpecial,
        which calls playCard BEFORE building the timeline. The timeline should
        still include card-effect steps for the played cards.
        """
        from MMM.battle_services import run_int_special
        from MMM.special_timeline import SPECIAL_TRIGGER, CARD_EFFECT

        self._reset_all_cards_to_deck()
        gc = GameCard.objects.filter(game_id=self.game.id, user_id=self.human_participant.id)
        cards = list(gc)

        # Draw some cards to hand (simulate having a hand)
        cards[1].state.draw()
        cards[1].state.updateOrdinal(1)
        cards[1].state.save()
        cards[2].state.draw()
        cards[2].state.updateOrdinal(2)
        cards[2].state.save()

        # Verify cards are in hand before intSpecial
        hand_before = GameCard.objects.filter(
            game_id=self.game.id, user_id=self.human_participant.id, state__lane=0
        )
        self.assertGreaterEqual(len(hand_before), 2)

        # Call intSpecial with a timeline (this calls playCard then build_int_timeline)
        timeline = []
        try:
            run_int_special(self.human_participant, 3, timeline)
        except Exception as e:
            self.fail(f"intSpecial raised exception: {e}")

        self.assertGreaterEqual(len(timeline), 1)

        # Should have at least a trigger step
        self.assertEqual(timeline[0]["kind"], SPECIAL_TRIGGER)

        # Check that cards were actually played (no longer in hand)
        hand_after = GameCard.objects.filter(
            game_id=self.game.id, user_id=self.human_participant.id, state__lane=0
        )
        # Cards should have been moved out of hand
        self.assertEqual(len(hand_after), 0)

        # Check for card-effect steps — this is the critical assertion
        card_effect_steps = [s for s in timeline if s["kind"] == CARD_EFFECT]
        self.assertGreaterEqual(
            len(card_effect_steps), 1,
            "intSpecial should produce card-effect steps even after playCard moves cards. "
            "Bug: build_int_timeline looks for cards in hand after playCard already moved them."
        )


class BattlePagePolishBacktickOverlayTests(TestCase):
    def setUp(self):
        self.human = Player.objects.create(name="Human")
        self.bot = Player.objects.create(name="Bot")

        human_owner = CardOwnerHistory.objects.create(cardOwner=self.human)
        bot_owner = CardOwnerHistory.objects.create(cardOwner=self.bot)

        self.human_cards = [
            Card.objects.create(title=f"Human-{index}", artSource="", cardType=index % 4)
            for index in range(4)
        ]
        for card in self.human_cards:
            card.ownerHistory.add(human_owner)
        self.bot_cards = [
            Card.objects.create(title=f"Bot-{index}", artSource="", cardType=index % 4)
            for index in range(4)
        ]
        for card in self.bot_cards:
            card.ownerHistory.add(bot_owner)

        self.human_deck = Deck.create(
            self.human.id,
            deckTitle="Human deck",
            newDescription="test deck",
            newDeckCards=self.human_cards,
        )
        self.bot_deck = Deck.create(
            self.bot.id,
            deckTitle="Bot deck",
            newDescription="test deck",
            newDeckCards=self.bot_cards,
        )

        history = BattleHistory.objects.create(challenger=self.human)
        self.game = Game.objects.create(title="Test game", history=history, roundNumber=0)
        self.human_participant = history.addHumanChallenger(
            challengerPlayer_id=self.human.id,
            startingCard_id=self.human_cards[0].id,
            deck_id=self.human_deck.id,
        )
        self.bot_participant = history.addRobotChallenger(
            challengerPlayer_id=self.bot.id,
            startingCard_id=self.bot_cards[0].id,
            deck_id=self.bot_deck.id,
        )

    def _read_card_drag_drop_js(self):
        import os

        js_path = os.path.join(
            os.path.dirname(__file__), '..', 'var', 'www', 'static', 'cardDragDrop.js'
        )
        with open(js_path) as js_file:
            return js_file.read()

    def _slice_on_keyboard_key_down(self, drag_js):
        return drag_js[
            drag_js.index('    onKeyboardKeyDown(event)'):
            drag_js.index('    selectOrderedCard(')
        ]

    def _slice_js_method(self, source, signature, end_marker):
        start = source.index(signature)
        end = source.index(end_marker, start)
        return source[start:end]

    def _read_cards_css(self):
        import os

        css_path = os.path.join(
            os.path.dirname(__file__), '..', 'var', 'www', 'static', 'cards.css'
        )
        with open(css_path) as css_file:
            return css_file.read()

    def _css_rules_for_selector(self, cards_css, selector):
        """(start_index, body) of every rule whose selector list uses only `selector`."""
        return [
            (match.start(), match.group(2).strip())
            for match in re.finditer(r'([^{}]+)\{([^{}]+)\}', cards_css)
            if all(part.strip() == selector for part in match.group(1).split(','))
        ]

    def test_backtick_overlay_keydown_branch_toggles_three_targets(self):
        drag_js = self._read_card_drag_drop_js()
        keydown_code = self._slice_on_keyboard_key_down(drag_js)

        self.assertIn("event.key === '`'", keydown_code)
        self.assertIn("event.code === 'Backquote'", keydown_code)
        self.assertIn("event.key !== '~'", keydown_code)
        self.assertNotIn("event.key === '~'", keydown_code)
        self.assertIn("classList.toggle('debug-overlay-visible'", keydown_code)

        for selector in (
            ".playerScreen .deckHand > p",
            ".playerScreen .enemyDeckHand > p",
            ".playerScreen .lanes .lane > p",
        ):
            self.assertIn(selector, keydown_code)

        toggle_index = keydown_code.index("classList.toggle('debug-overlay-visible'")
        self.assertIn('event.preventDefault()', keydown_code[:toggle_index])

    def test_backtick_overlay_skips_text_controls(self):
        drag_js = self._read_card_drag_drop_js()
        keydown_code = self._slice_on_keyboard_key_down(drag_js)

        backtick_index = keydown_code.index("event.key === '`'")
        toggle_index = keydown_code.index("classList.toggle('debug-overlay-visible'")
        self.assertLess(backtick_index, toggle_index)

        guard_block = keydown_code[backtick_index:toggle_index]
        self.assertIn('_isTextControlTarget', guard_block)
        self.assertIn('event.preventDefault()', guard_block)

    def test_backtick_overlay_css_rule_uses_absolute_white_z3(self):
        cards_css = self._read_cards_css()

        overlay_rules = self._css_rules_for_selector(cards_css, '.debug-overlay')
        self.assertNotEqual(
            overlay_rules, [],
            "No .debug-overlay CSS rule found for the debug overlay box",
        )

        rule_body = overlay_rules[0][1]
        self.assertIn('position: absolute', rule_body)
        self.assertIn('background: white', rule_body)
        self.assertIn('z-index: 3', rule_body)

        for forbidden in ('top:', 'width: ', 'left: ', 'height: '):
            self.assertNotIn(forbidden, rule_body)

    def test_backtick_overlay_targets_exist_in_rendered_board(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))
        content = response.content.decode()

        player_p_match = re.search(
            r'<div class="deckHand[^"]*">\s*(<p[^>]*>[\s\S]*?</p>)\s*<div class="hand-scroll"',
            content,
        )
        self.assertIsNotNone(
            player_p_match,
            "Player deck/hand counter <p> is not the first child of the deckHand container",
        )
        self.assertIn('Deck:', player_p_match.group(1))
        self.assertIn('| Hand:', player_p_match.group(1))

        enemy_p_match = re.search(
            r'<div class="enemyDeckHand">\s*(<p class="cardType[^"]*"[^>]*>[\s\S]*?</p>)'
            r'\s*<div class="deck-stack enemy-deck-stack"',
            content,
        )
        self.assertIsNotNone(
            enemy_p_match,
            "Enemy deck/hand counter <p class=\"cardType\"> is not the first child of "
            "<div class=\"enemyDeckHand\">",
        )
        self.assertIn('Deck:', enemy_p_match.group(1))
        self.assertIn('| Hand:', enemy_p_match.group(1))

        lane_finder = _LaneIndicatorFinder()
        lane_finder.feed(content)
        for lane_name in ('Intelligence', 'Speed', 'Visciousness', 'Resolve'):
            self.assertIn(
                lane_name,
                lane_finder.found,
                f"Lane <li class=\"lane {lane_name}\"> has no <p> direct child",
            )
            self.assertIn(lane_name, lane_finder.found[lane_name])

    def test_backtick_overlay_targets_are_visible_not_dev_only(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))
        content = response.content.decode()

        def strip_blocks(source, pattern):
            return re.sub(pattern, '', source, flags=re.DOTALL)

        scrubbed = strip_blocks(content, r'<script\b[^>]*>[\s\S]*?</script>')
        scrubbed = strip_blocks(scrubbed, r'<template\b[^>]*>[\s\S]*?</template>')
        scrubbed = strip_blocks(scrubbed, r'<div\b[^>]*\bhidden\b[^>]*>[\s\S]*?</div>')

        self.assertRegex(
            scrubbed,
            r'<p class="debug-overlay">\s*Deck: \d+ \| Hand: \d+',
            "Player counter <p> must not be inside <script>, <template>, or hidden <div>",
        )
        self.assertRegex(
            scrubbed,
            r'<p class="cardType debug-overlay">Deck: \d+ \| Hand: \d+</p>',
            "Enemy counter <p class=\"cardType\"> must not be inside dev-only blocks",
        )
        for lane_name in ('Intelligence', 'Speed', 'Visciousness', 'Resolve'):
            self.assertRegex(
                scrubbed,
                rf'<p class="debug-overlay">\s*\d+ \| {lane_name}\s*</p>',
                f"Lane <p> for {lane_name} must not be inside dev-only blocks",
            )

    def test_backtick_debug_branch_toggles_only_paragraph_groups_without_panel(self):
        drag_js = self._read_card_drag_drop_js()
        keydown_code = self._slice_on_keyboard_key_down(drag_js)

        self.assertNotIn('debugOverlay', keydown_code)
        self.assertNotIn('getElementById', keydown_code)

        branch_index = keydown_code.index(
            "event.key === '`' || (event.code === 'Backquote' && event.key !== '~')"
        )
        toggle_call_index = keydown_code.index(
            'this.toggleDebugParagraphOverlay()', branch_index
        )
        end_of_branch = keydown_code.index('if (this._isEndTurnKey(event))', branch_index)
        branch = keydown_code[branch_index:end_of_branch]
        self.assertIn('event.preventDefault()', branch)
        self.assertIn('this.toggleDebugParagraphOverlay();', branch)

        self.assertEqual(
            keydown_code.count("classList.toggle('debug-overlay-visible'"), 1
        )
        self.assertEqual(keydown_code.count('document.querySelectorAll'), 1)

        combined_selector = keydown_code[keydown_code.index('.playerScreen .deckHand > p'):]
        combined_selector = combined_selector[:combined_selector.index(')')]
        for selector in (
            ".playerScreen .deckHand > p",
            ".playerScreen .enemyDeckHand > p",
            ".playerScreen .lanes .lane > p",
        ):
            self.assertIn(selector, combined_selector)

    def test_backtick_debug_paragraph_css_styling_applies_visibility_class(self):
        cards_css = self._read_cards_css()

        hidden_rules = self._css_rules_for_selector(cards_css, '.debug-overlay')
        visible_rules = self._css_rules_for_selector(cards_css, '.debug-overlay-visible')
        self.assertNotEqual(hidden_rules, [], "No .debug-overlay CSS rule found")
        self.assertNotEqual(
            visible_rules, [], "No .debug-overlay-visible CSS rule found"
        )

        self.assertIn('display:none', hidden_rules[0][1])
        self.assertIn('display:block', visible_rules[0][1])
        self.assertLess(
            hidden_rules[0][0], visible_rules[0][0],
            "The display:block rule must come after the display:none rule "
            "so toggling debug-overlay-visible wins the cascade",
        )

    def test_backtick_dead_key_and_grave_dispatch_toggles_paragraphs_via_dom(self):
        import os
        import subprocess
        import tempfile

        drag_js = self._read_card_drag_drop_js()
        text_control_target = self._slice_js_method(
            drag_js,
            '    _isTextControlTarget(target) {',
            '    _keyboardTransitionActive() {',
        )
        end_turn_key = self._slice_js_method(
            drag_js,
            '    _isEndTurnKey(event) {',
            '    _isDrawKey(event) {',
        )
        draw_key = self._slice_js_method(
            drag_js,
            '    _isDrawKey(event) {',
            '    _findEndTurnControl() {',
        )
        keydown_handler = self._slice_js_method(
            drag_js,
            '    onKeyboardKeyDown(event) {',
            '    toggleDebugParagraphOverlay() {',
        )
        paragraph_toggle = self._slice_js_method(
            drag_js,
            '    toggleDebugParagraphOverlay() {',
            '    selectOrderedCard(',
        )

        harness_parts = [
            'const expectedSelector =',
            repr(
                '.playerScreen .deckHand > p, '
                '.playerScreen .enemyDeckHand > p, '
                '.playerScreen .lanes .lane > p'
            ) + ';',
            '',
            'const makeFakeParagraph = (name) => {',
            '    const paragraph = { name, toggledUp: 0 };',
            '    paragraph.classList = {',
            '        toggle(className) {',
            "            if (className !== 'debug-overlay-visible') {",
            '                throw new Error("unexpected toggled class " + className);',
            '            }',
            '            paragraph.toggledUp += 1;',
            '        },',
            '    };',
            '    return paragraph;',
            '};',
            '',
            'const playerCounter = makeFakeParagraph("player");',
            'const enemyCounter = makeFakeParagraph("enemy");',
            'const laneIndicator = makeFakeParagraph("lane");',
            'const paragraphTargets = [playerCounter, enemyCounter, laneIndicator];',
            '',
            'let recordedSelector = null;',
            'global.document = {',
            '    activeElement: null,',
            '    querySelectorAll(selector) {',
            '        if (!recordedSelector) recordedSelector = selector;',
            '        return paragraphTargets;',
            '    },',
            '};',
            '',
            'const system = { keyboardSelection: { selectedCard: null, digitBuffer: "" } };',
            'system._isTextControlTarget = eval(`(function ${' + repr(text_control_target) + '})`);',
            'system._isEndTurnKey = eval(`(function ${' + repr(end_turn_key) + '})`);',
            'system._isDrawKey = eval(`(function ${' + repr(draw_key) + '})`);',
            'system.onKeyboardKeyDown = eval(`(function ${' + repr(keydown_handler) + '})`);',
            'system.toggleDebugParagraphOverlay = eval(`(function ${' + repr(paragraph_toggle) + '})`);',
            '',
            'const dispatch = (descriptor) => {',
            '    playerCounter.toggledUp = 0;',
            '    enemyCounter.toggledUp = 0;',
            '    laneIndicator.toggledUp = 0;',
            '    recordedSelector = null;',
            '    const event = {',
            '        key: descriptor.key,',
            '        code: descriptor.code,',
            '        defaultPrevented: false,',
            '        repeat: false,',
            '        target: descriptor.target,',
            '        preventDefault() { event.prevented = true; },',
            '    };',
            '    system.onKeyboardKeyDown(event);',
            '    return { selector: recordedSelector, prevented: Boolean(event.prevented) };',
            '};',
            '',
            'const expectToggled = (dispatched) => {',
            '    if (dispatched.selector !== expectedSelector) {',
            '        throw new Error("querySelectorAll selector mismatch: " + dispatched.selector);',
            '    }',
            '    for (const paragraph of paragraphTargets) {',
            '        if (paragraph.toggledUp !== 1) {',
            '            throw new Error(paragraph.name + " did not receive the debug class");',
            '        }',
            '    }',
            '};',
            '',
            'let dispatchResult = dispatch({ key: "Dead", code: "Backquote" });',
            'expectToggled(dispatchResult);',
            'if (!dispatchResult.prevented) throw new Error("Dead backtick was not consumed");',
            '',
            'dispatchResult = dispatch({ key: "`", code: "Backquote" });',
            'expectToggled(dispatchResult);',
            'if (!dispatchResult.prevented) throw new Error("grave backtick was not consumed");',
            '',
            'dispatchResult = dispatch({ key: "Dead", code: "Backquote", target: { closest: () => null } });',
            'expectToggled(dispatchResult);',
            '',
            'const textControlTarget = { closest: (selector) => ({ matches: () => true }) };',
            'dispatchResult = dispatch({ key: "Dead", code: "Backquote", target: textControlTarget });',
            'if (playerCounter.toggledUp !== 0 || enemyCounter.toggledUp !== 0 || laneIndicator.toggledUp !== 0) {',
            '    throw new Error("text-control target must not trigger the debug toggle");',
            '}',
            'if (!dispatchResult.prevented) throw new Error("backtick in text control was not consumed");',
            '',
            'global.document.activeElement = textControlTarget;',
            'dispatchResult = dispatch({ key: "`", code: "Backquote" });',
            'if (playerCounter.toggledUp !== 0) {',
            '    throw new Error("focused text control must block the debug toggle");',
            '}',
            'global.document.activeElement = null;',
            '',
            'dispatchResult = dispatch({ key: "~", code: "Backquote" });',
            'if (playerCounter.toggledUp !== 0 || enemyCounter.toggledUp !== 0 || laneIndicator.toggledUp !== 0) {',
            '    throw new Error("shifted tilde must not trigger the debug toggle");',
            '}',
            'if (dispatchResult.prevented) throw new Error("tilde keydown should reach other handlers");',
            '',
            'console.log("backtick debug paragraphs ok");',
        ]
        harness = '\n'.join(harness_parts)

        try:
            node_binary = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest('node binary unavailable; skipping backtick dispatch test')
        if node_binary.returncode != 0:
            self.skipTest('node binary unavailable; skipping backtick dispatch test')

        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
            handle.write(harness)
            temp_path = handle.name
        try:
            completed = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(temp_path)
        if completed.returncode != 0:
            self.fail(
                'backtick dispatch harness failed:\n'
                f'stdout={completed.stdout}\nstderr={completed.stderr}'
            )
        self.assertIn('backtick debug paragraphs ok', completed.stdout)


class PlayerPageToBoardEndToEndTests(TestCase):
    """Browser regression walk: open a player page, start and resume a challenge,
    and keep the board loaded with its required assets and staged action flow."""

    def setUp(self):
        self.human = Player.objects.create(name="Human")
        self.bot = Player.objects.create(name="Bot")

        human_owner = CardOwnerHistory.objects.create(cardOwner=self.human)
        self.human_cards = [
            Card.objects.create(title=f"Human-{index}", artSource="", cardType=index % 4)
            for index in range(4)
        ]
        for card in self.human_cards:
            card.ownerHistory.add(human_owner)
        self.bot_cards = [
            Card.objects.create(title=f"Bot-{index}", artSource="", cardType=index % 4)
            for index in range(4)
        ]
        bot_owner = CardOwnerHistory.objects.create(cardOwner=self.bot)
        for card in self.bot_cards:
            card.ownerHistory.add(bot_owner)

        self.human_deck = Deck.create(
            self.human.id,
            deckTitle="Human walk deck",
            newDescription="walking a challenge",
            newDeckCards=self.human_cards,
        )
        self.bot_deck = Deck.create(
            self.bot.id,
            deckTitle="Bot walk deck",
            newDescription="defending the walk",
            newDeckCards=self.bot_cards,
        )

    def _open(self, url):
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200, f"Navigation failed for {url}")
        html = response.content.decode()
        scripts = re.findall(r'<script[^>]*src="[^"]*?/static/([a-zA-Z0-9._-]+)"', html)
        links = re.findall(r'<link[^>]*href="[^"]*?/static/([a-zA-Z0-9._-]+)"', html)
        referenced = sorted(set(scripts + links))
        missing = [ref for ref in referenced if finders.find(ref) is None]
        self.assertEqual(
            missing, [],
            f"Page at {url} references missing required assets: {missing}",
        )
        return response

    def _input_values(self, html, field_name):
        values = []
        for tag in re.findall(r'<input[^>]*>', html):
            if re.search(rf'name="{field_name}"', tag):
                value = re.search(r'value="([^"]*)"', tag)
                if value:
                    values.append(value.group(1))
        return values

    def _player_counter(self, board_html):
        deck_hand = re.split(r'<div class="deckHand[^"]*">', board_html, 1)[1]
        match = re.search(r'Deck: (\d+) \| Hand: (\d+)', deck_hand)
        self.assertIsNotNone(match, "Board is missing its deck/hand counter")
        return int(match.group(1)), int(match.group(2))

    def test_player_page_starts_challenge_board_loads_assets_and_keeps_flow(self):
        player_url = reverse("MMM:viewPlayer", args=[self.human.id])
        response = self._open(player_url)
        content = response.content.decode()
        self.assertIn("Challenges", content)
        create_link = reverse("MMM:createGame", args=[self.human.id]).rstrip("/")
        self.assertContains(response, create_link)

        response = self._open(reverse("MMM:createGame", args=[self.human.id]))
        content = response.content.decode()
        self.assertContains(response, "Initialize new game")
        game_id = int(self._input_values(content, "newGameIdValue").pop())
        self.assertEqual(self._input_values(content, "challenger"), [str(self.human.id)])
        opponent_id = int(self._input_values(content, "challengePlayer").pop())
        deck_id = int(self._input_values(content, "startingDeck").pop())
        starting_card_id = int(self._input_values(content, "startingCard").pop())
        self.assertEqual(self.human_deck.id, deck_id)

        response = self.client.post(
            reverse("MMM:initializeGame"),
            {
                "newGameIdValue": game_id,
                "challenger": self.human.id,
                "challengePlayer": opponent_id,
                "startingDeck": deck_id,
                "startingCard": starting_card_id,
            },
        )
        game_detail_url = reverse("MMM:viewGameAsPlayer", args=[game_id, self.human.id])
        self.assertRedirects(response, game_detail_url)

        response = self._open(game_detail_url)
        content = response.content.decode()
        self.assertIn(self.bot.name, content)
        self.assertIn("challenger:", content)
        self.assertContains(response, "Shuffle the deck and load board")
        confirm_url = reverse("MMM:confirmChallenge", args=[game_id, self.human.id])
        self.assertContains(response, confirm_url)

        board_url = reverse("MMM:viewBoard", args=[game_id, self.human.id])
        response = self.client.post(confirm_url)
        self.assertRedirects(response, board_url)

        response = self._open(board_url)
        board_before_draw = response.content.decode()
        self.assertContains(response, '<link rel="stylesheet" href="/static/style.css">')
        self.assertContains(response, '<link rel="stylesheet" href="/static/cards.css">')
        self.assertContains(response, '<script type="module" src="/static/cardDragDrop.js"></script>')
        self.assertContains(
            response, '<script type="module" src="/static/loadingAnimations.js"></script>'
        )
        self.assertContains(response, '<script type="module" src="/static/laneStacking.js"></script>')
        self.assertContains(response, '<script type="module" src="/static/hoverCooldown.js"></script>')
        self.assertContains(
            response, '<link rel="stylesheet" type="text/css" href="/static/cardDragDrop.css">'
        )
        self.assertContains(response, 'id="turnLimits"')
        self.assertContains(response, '<div class="deckHand')
        self.assertContains(response, 'class="end-turn"')
        self.assertContains(response, reverse("MMM:boardAction", args=[game_id, self.human.id]))
        deck_count_before, hand_count_before = self._player_counter(board_before_draw)
        self.assertGreater(deck_count_before, 0, "Loaded board left the player without a deck")

        draw_url = reverse("MMM:boardAction", args=[game_id, self.human.id])
        response = self.client.post(draw_url, {"action": "draw"})
        content = response.content.decode()
        self.assertNotContains(response, "Action error")
        self.assertIn('class="cardContainer loading"', content)

        board_after_draw = self._open(board_url).content.decode()
        deck_count_after, hand_count_after = self._player_counter(board_after_draw)
        self.assertEqual(deck_count_after, deck_count_before - 1)
        self.assertEqual(hand_count_after, hand_count_before + 1)
        self.assertIn('draggable="true" tabindex="0"', board_after_draw)
        self.assertIn("data-card-id", board_after_draw)

        self.assertContains(self._open(player_url), board_url)
        resumed = self._open(board_url)
        self.assertContains(resumed, 'id="turnLimits"')

        self.client.post(draw_url, {"action": "end_turn"})
        response = self._open(board_url)
        self.assertContains(response, 'data-phase="enemy"')
        response = self._open(board_url)
        self.assertContains(response, 'data-phase="player"')

        defeated_participant = Game.objects.get(pk=game_id).history.participants.get(
            player_id=self.human.id
        )
        defeated_participant.defeated = True
        defeated_participant.save()

        response = self.client.post(draw_url, {"action": "end_turn"})
        response = self._open(board_url)
        result_url = reverse("MMM:viewResult", args=[game_id, self.human.id])
        self.assertContains(response, f'data-next-url="{result_url}"')

        response = self._open(result_url)
        content = response.content.decode()
        self.assertIn("result", content)
        self.assertIn(self.human.name, content)
        self.assertIn("Play again", content)


class _LaneIndicatorFinder(HTMLParser):
    """Walk rendered board and collect <p> indicators that are direct children of lane <li>s."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.target_lanes = ('Intelligence', 'Speed', 'Visciousness', 'Resolve')
        self.found = {}
        self.current_lane = None
        self.li_depth_in_lane = 0
        self.in_p_at_lane_depth = False
        self.p_text = ''

    def handle_starttag(self, tag, attrs):
        if tag == 'li':
            attrs_dict = dict(attrs)
            cls = attrs_dict.get('class', '')
            if self.current_lane is None:
                parts = cls.split(' ', 1)
                if len(parts) == 2 and parts[0] == 'lane' and parts[1] in self.target_lanes:
                    self.current_lane = parts[1]
                    self.li_depth_in_lane = 1
                    return
            else:
                self.li_depth_in_lane += 1
        elif tag == 'p' and self.current_lane is not None and self.li_depth_in_lane == 1:
            self.in_p_at_lane_depth = True
            self.p_text = ''

    def handle_endtag(self, tag):
        if tag == 'li' and self.current_lane is not None:
            self.li_depth_in_lane -= 1
            if self.li_depth_in_lane == 0:
                self.current_lane = None
        elif tag == 'p' and self.in_p_at_lane_depth:
            if self.current_lane and self.li_depth_in_lane == 1:
                self.found[self.current_lane] = self.p_text
            self.in_p_at_lane_depth = False
            self.p_text = ''

    def handle_data(self, data):
        if self.in_p_at_lane_depth:
            self.p_text += data


class GameActionApiTests(BattleBoardFixture):
    """JSON API for the board actions, its OpenAPI docs and browser parity."""

    def setUp(self):
        super().setUp()
        self.schema_url = reverse("MMM:apiSchema")
        self.docs_url = reverse("MMM:apiSwaggerUI")
        self.reset_url = reverse("MMM:apiResetGames")
        self.board_url = reverse("MMM:apiBoardState", args=[self.game.id, self.human.id])
        self.play_url = reverse("MMM:apiPlayCardsAction", args=[self.game.id, self.human.id])
        self.draw_url = reverse("MMM:apiDrawCardAction", args=[self.game.id, self.human.id])
        self.end_turn_url = reverse("MMM:apiEndTurnAction", args=[self.game.id, self.human.id])

    def _confirm_via_browser(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))

    def _hand_card_ids(self, participant=None):
        participant = participant or self.human_participant
        return list(
            GameCard.objects.filter(
                game_id=self.game.id, user_id=participant.id, state__lane=0
            ).order_by("state__laneOrdinal").values_list("id", flat=True)
        )

    def _participant_zone_counts(self, participant):
        game_cards = GameCard.objects.filter(game_id=self.game.id, user_id=participant.id)
        return {
            "hand": game_cards.filter(state__lane=0).count(),
            "lanes": game_cards.filter(state__lane__gt=0).count(),
            "deck": game_cards.filter(state__inDeck=True).count(),
        }

    def _post_json(self, url, body=None, raw=None):
        payload = raw if raw is not None else json.dumps(body) if body is not None else "{}"
        return self.client.post(url, payload, content_type="application/json")

    def _state_json(self, phase=None):
        url = self.board_url if not phase else f"{self.board_url}?phase={phase}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content.decode())
        return json.loads(response.content.decode())

    def test_openapi_schema_documents_actions_and_errors(self):
        response = self.client.get(self.schema_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.has_header("Location"))
        schema = json.loads(response.content.decode())

        self.assertEqual(schema["openapi"], "3.0.3")
        self.assertIn("game-action API", schema["info"]["title"])
        self.assertNotIn("security", schema)
        self.assertIn("", schema["components"]["schemas"]["BoardState"]["properties"]["turnPhase"]["enum"])

        for path in (
            self.schema_url,
            self.docs_url,
            self.reset_url,
            api_docs.BOARD_PATH,
            api_docs.PLAY_PATH,
            api_docs.DRAW_PATH,
            api_docs.END_TURN_PATH,
        ):
            self.assertIn(path, schema["paths"], path)

        self.assertEqual(api_docs.BOARD_PATH.format(gameId=1, playerId=2), reverse("MMM:apiBoardState", args=[1, 2]))
        self.assertEqual(api_docs.PLAY_PATH.format(gameId=1, playerId=2), reverse("MMM:apiPlayCardsAction", args=[1, 2]))
        self.assertEqual(api_docs.DRAW_PATH.format(gameId=1, playerId=2), reverse("MMM:apiDrawCardAction", args=[1, 2]))
        self.assertEqual(api_docs.END_TURN_PATH.format(gameId=1, playerId=2), reverse("MMM:apiEndTurnAction", args=[1, 2]))

        play_operation = schema["paths"][api_docs.PLAY_PATH]["post"]
        self.assertTrue(play_operation["requestBody"]["required"])
        self.assertIn("200", play_operation["responses"])
        for status in ("400", "404"):
            self.assertIn(status, play_operation["responses"])
            self.assertIn("#/components/schemas/Error", play_operation["responses"][status]["content"]["application/json"]["schema"]["$ref"])

        end_turn_operation = schema["paths"][api_docs.END_TURN_PATH]["post"]
        self.assertFalse(end_turn_operation["requestBody"]["required"])
        for status in ("200", "400", "404"):
            self.assertIn(status, end_turn_operation["responses"])

        board_operation = schema["paths"][api_docs.BOARD_PATH]["get"]
        draw_operation = schema["paths"][api_docs.DRAW_PATH]["post"]
        for operation in (board_operation, play_operation, draw_operation, end_turn_operation):
            path_parameters = {
                parameter["name"]: parameter
                for parameter in operation["parameters"]
                if parameter["in"] == "path"
            }
            self.assertEqual(set(path_parameters), {"gameId", "playerId"}, operation["summary"])
            for name in ("gameId", "playerId"):
                self.assertTrue(path_parameters[name]["required"], name)
                self.assertEqual(path_parameters[name]["schema"]["type"], "integer", name)

        phase_parameter = next(
            parameter for parameter in board_operation["parameters"] if parameter["name"] == "phase"
        )
        self.assertEqual(phase_parameter["in"], "query")
        self.assertEqual(
            phase_parameter["schema"]["enum"],
            ["player", "playerMoves", "enemy"],
        )
        for status in ("200", "400", "404", "409"):
            self.assertIn(status, board_operation["responses"])

        components = schema["components"]["schemas"]
        for schema_name in (
            "PlayRecord",
            "ExecutedPlay",
            "BoardActionResult",
            "BoardState",
            "ParticipantState",
            "TurnAllowances",
            "ResetResult",
            "Error",
        ):
            self.assertIn(schema_name, components)

        self.assertEqual(components["PlayRecord"]["required"], ["cardId", "laneValue"])
        self.assertEqual(components["PlayRecord"]["properties"]["laneValue"]["enum"], [1, 2, 3, 4])
        self.assertIn("error", components["Error"]["required"])

    def test_swagger_ui_serves_open_docs_and_assets(self):
        from django.contrib.staticfiles import finders

        response = self.client.get(self.docs_url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.schema_url, content)
        self.assertIn("swagger-ui/swagger-ui-bundle.js", content)
        self.assertIn("swagger-ui/swagger-ui.css", content)
        self.assertIn("window.SwaggerUIBundle", content)
        self.assertIn('dom_id: "#openApiDocs"', content)
        self.assertIn("tryItOutEnabled: true", content)

        for asset in (
            "apiDocs.css",
            "swagger-ui/swagger-ui.css",
            "swagger-ui/swagger-ui-bundle.js",
        ):
            self.assertIsNotNone(finders.find(asset), asset)

    def test_api_board_state_409_before_browser_confirm(self):
        response = self.client.get(self.board_url)
        self.assertEqual(response.status_code, 409)
        self.assertIn(
            "not initialized", json.loads(response.content.decode())["error"]
        )

    def test_api_board_state_404s_are_json(self):
        response = self.client.get(reverse("MMM:apiBoardState", args=[999999, 1]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            json.loads(response.content.decode())["error"],
            "no such game or participant",
        )

        response = self.client.get(reverse("MMM:apiBoardState", args=[self.game.id, 999999]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            json.loads(response.content.decode())["error"],
            "no such game or participant",
        )

    def test_api_board_state_rejects_unknown_phase(self):
        self._confirm_via_browser()
        response = self.client.get(f"{self.board_url}?phase=boss")
        self.assertEqual(response.status_code, 400)
        self.assertIn("phase", json.loads(response.content.decode())["error"])

    def test_api_board_state_maps_verified_browser_board_to_json(self):
        self._confirm_via_browser()

        browser_response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))
        self.assertEqual(browser_response.status_code, 200)
        self.assertNotIn("Action error", browser_response.content.decode())

        state = self._state_json()
        self.assertEqual(state["gameId"], self.game.id)
        self.assertEqual(state["playerId"], self.human.id)
        self.assertEqual(state["roundNumber"], 1)
        self.assertNotIn("error", state)
        self.assertFalse(state["finished"])
        self.assertEqual(state["turnPhase"], "")
        self.assertEqual(state["nextTurnPhase"], "")
        self.assertFalse(state["botTurnRan"])
        self.assertEqual(state["botPlays"], [])

        viewer = state["viewer"]
        self.assertEqual(viewer["participantId"], self.human_participant.id)
        self.assertEqual(viewer["playerName"], self.human.name)
        self.assertFalse(viewer["computerControlled"])
        self.assertEqual(viewer["deckCount"], self.human_deck.cards.count() - 1)
        self.assertEqual(viewer["handCount"], 0)
        self.assertEqual(viewer["allowances"]["draws_left"], 2)
        self.assertEqual(viewer["allowances"]["plays_left"], 3)
        self.assertEqual(viewer["allowances"]["flips_left"], 1)

        lanes = {lane["name"]: lane for lane in viewer["lanes"]}
        self.assertEqual(list(lanes), ["Intelligence", "Speed", "Visciousness", "Resolve"])
        starting_card = lanes["Intelligence"]["trustedCards"][0]
        self.assertTrue(starting_card["trusted"])
        self.assertFalse(starting_card["faceDown"])
        self.assertEqual(starting_card["lane"], 1)
        self.assertEqual(starting_card["laneOrdinal"], 1)

        participants = {entry["playerId"]: entry for entry in state["participants"]}
        self.assertEqual(sorted(participants), [self.human.id, self.bot.id])
        bot_state = participants[self.bot.id]
        self.assertTrue(bot_state["computerControlled"])
        self.assertEqual(bot_state["deckCount"], self.bot_deck.cards.count() - 1)
        self.assertEqual(bot_state["handCards"], [])

    def test_api_draw_matches_browser_limit_and_counts(self):
        self._confirm_via_browser()

        for drawn_amount in (1, 2):
            response = self._post_json(self.draw_url)
            self.assertEqual(response.status_code, 200, response.content.decode())
            result = json.loads(response.content.decode())
            self.assertIsNone(result["error"])
            self.assertEqual(result["action"], "draw")
            self.assertEqual(len(result["plays"]), 1)
            self.assertEqual(result["plays"][0]["laneValue"], 0)
            self.assertFalse(result["enemyPhasePending"])
            self.assertEqual(
                result["turnAllowances"]["draws_left"],
                2 - drawn_amount,
            )
            self.assertEqual(len(self._hand_card_ids()), drawn_amount)

        self.human_participant.refresh_from_db()
        self.assertEqual(self.human_participant.drawnCardsAmount, 2)

        zones_before = self._participant_zone_counts(self.human_participant)
        response = self._post_json(self.draw_url)
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "cannot draw more cards this turn", json.loads(response.content.decode())["error"]
        )
        self.assertEqual(
            self._participant_zone_counts(self.human_participant), zones_before
        )

    def test_api_draw_empty_deck_reports_without_mutation(self):
        self._confirm_via_browser()
        GameCard.objects.filter(
            game_id=self.game.id, user_id=self.human_participant.id, state__inDeck=True
        ).delete()

        response = self._post_json(self.draw_url)
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "No cards left in", json.loads(response.content.decode())["error"]
        )
        self.assertEqual(self._participant_zone_counts(self.human_participant), {
            "hand": 0, "lanes": 1, "deck": 0,
        })

    def test_api_play_consumes_play_and_flip(self):
        self._confirm_via_browser()
        self._post_json(self.draw_url)
        hand_card_id = self._hand_card_ids()[0]

        response = self._post_json(self.play_url, {
            "plays": [{
                "cardId": hand_card_id,
                "laneValue": 3,
                "flipFaceUp": False,
                "sourceLane": 0,
                "sourceOrdinal": 1,
            }]
        })
        self.assertEqual(response.status_code, 200, response.content.decode())
        result = json.loads(response.content.decode())
        self.assertEqual(result["action"], "play")
        self.assertEqual(result["plays"], [{
            "cardId": hand_card_id,
            "participantId": self.human_participant.id,
            "laneValue": 3,
            "sourceLane": 0,
            "sourceOrdinal": 1,
            "flipFaceUp": False,
        }])
        self.assertEqual(result["turnAllowances"]["played"], 1)
        self.assertEqual(result["turnAllowances"]["flipped"], 0)

        lane_card = GameCard.objects.get(pk=hand_card_id)
        self.assertEqual(lane_card.state.lane, 3)
        self.assertTrue(lane_card.state.faceDown)
        self.assertFalse(lane_card.state.trusted)

        response = self._post_json(self.play_url, {
            "plays": [{
                "cardId": hand_card_id,
                "laneValue": 3,
                "flipFaceUp": True,
                "sourceLane": 3,
                "sourceOrdinal": 1,
            }]
        })
        self.assertEqual(response.status_code, 200, response.content.decode())
        result = json.loads(response.content.decode())
        self.assertEqual(result["plays"], [{
            "cardId": hand_card_id,
            "participantId": self.human_participant.id,
            "laneValue": 3,
            "sourceLane": 3,
            "sourceOrdinal": 1,
            "flipFaceUp": True,
        }])
        self.assertEqual(result["turnAllowances"]["flipped"], 1)

        lane_card.refresh_from_db()
        self.assertFalse(lane_card.state.faceDown)
        self.assertEqual(
            self._participant_zone_counts(self.human_participant)["lanes"], 2
        )

    def test_api_play_validation_rejects_without_mutation(self):
        self._confirm_via_browser()
        self._post_json(self.draw_url)
        hand_card_id = self._hand_card_ids()[0]
        foreign_card = GameCard.objects.filter(
            game_id=self.game.id, user_id=self.bot_participant.id
        ).first()
        zones_before = self._participant_zone_counts(self.human_participant)

        rejections = [
            ("plays missing laneValue", {"plays": [{"cardId": hand_card_id}]}, "laneValue"),
            ("unsupported fields", {"plays": [{"cardId": hand_card_id, "laneValue": 2, "magic": 1}]}, "unsupported"),
            ("foreign card", {"plays": [{"cardId": foreign_card.id, "laneValue": 2}]}, "not a game card"),
            ("lane out of range", {"plays": [{"cardId": hand_card_id, "laneValue": 5}]}, "laneValue"),
            ("duplicate cards", {"plays": [
                {"cardId": hand_card_id, "laneValue": 2},
                {"cardId": hand_card_id, "laneValue": 3},
            ]}, "more than once"),
            ("flip not boolean", {"plays": [{"cardId": hand_card_id, "laneValue": 2, "flipFaceUp": "yes"}]}, "flipFaceUp"),
            ("plays not a list", {"plays": "two"}, "array of play records"),
            ("plays missing entirely", {}, "at least one"),
        ]
        for label, body, expected_text in rejections:
            response = self._post_json(self.play_url, body)
            self.assertEqual(response.status_code, 400, label)
            self.assertIn(expected_text, json.loads(response.content.decode())["error"], label)

        response = self._post_json(self.play_url, raw="{not json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("not valid JSON", json.loads(response.content.decode())["error"])

        response = self._post_json(self.play_url, raw="[1,2]")
        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON object", json.loads(response.content.decode())["error"])

        self.assertEqual(
            self._participant_zone_counts(self.human_participant), zones_before
        )

    def test_api_play_over_limit_rolls_back_partial_execution(self):
        self._confirm_via_browser()
        for _ in range(2):
            response = self._post_json(self.draw_url)
            self.assertEqual(response.status_code, 200)
        hand_card_ids = self._hand_card_ids()
        self.assertEqual(len(hand_card_ids), 2)
        zones_before = self._participant_zone_counts(self.human_participant)

        response = self._post_json(self.play_url, {"plays": [
            {"cardId": hand_card_ids[0], "laneValue": 2},
            {"cardId": hand_card_ids[1], "laneValue": 3},
        ]})
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "cannot play more cards", json.loads(response.content.decode())["error"]
        )
        self.assertEqual(
            self._participant_zone_counts(self.human_participant), zones_before
        )
        self.human_participant.refresh_from_db()
        self.assertEqual(self.human_participant.playedCardsAmount, 0)

    def test_api_end_turn_defers_bot_turn_to_board_state_phase(self):
        self._confirm_via_browser()
        bot_before = self._participant_zone_counts(self.bot_participant)

        response = self._post_json(self.end_turn_url)
        self.assertEqual(response.status_code, 200, response.content.decode())
        result = json.loads(response.content.decode())
        self.assertTrue(result["enemyPhasePending"])
        self.assertEqual(result["plays"], [])
        self.assertEqual(result["turnAllowances"]["drawn"], 0)
        self.assertEqual(result["turnAllowances"]["played"], 0)

        self.game.refresh_from_db()
        self.assertEqual(self.game.roundNumber, 1)
        self.assertEqual(
            self._participant_zone_counts(self.bot_participant), bot_before
        )

        state = self._state_json("enemy")
        bot_after = self._participant_zone_counts(self.bot_participant)
        self.assertTrue(state["botTurnRan"])
        self.assertEqual(len(state["botPlays"]), 2)
        self.assertEqual(state["nextTurnPhase"], "player")
        self.assertGreater(bot_after["lanes"], bot_before["lanes"])
        self.assertEqual(state["roundNumber"], 2)

        idle_state = self._state_json()
        self.assertFalse(idle_state["botTurnRan"])
        self.assertEqual(
            self._participant_zone_counts(self.bot_participant), bot_after
        )
        self.assertEqual(idle_state["roundNumber"], 2)

    def test_api_reset_and_browser_route_declare_removed_games(self):
        self._confirm_via_browser()

        response = self._post_json(self.reset_url)
        self.assertEqual(response.status_code, 200, response.content.decode())
        result = json.loads(response.content.decode())
        self.assertEqual(result["status"], "reset")
        self.assertEqual(result["removedGames"], 1)

        self.assertEqual(Game.objects.count(), 0)
        self.assertEqual(BattleHistory.objects.count(), 0)
        self.assertEqual(BattleParticipant.objects.count(), 0)
        self.assertEqual(GameCard.objects.count(), 0)
        self.assertEqual(CardState.objects.count(), 0)
        self.assertEqual(Deck.objects.count(), 0)
        self.assertEqual(Player.objects.count(), 2)

        response = self.client.get(reverse("MMM:resetGames"))
        self.assertRedirects(response, reverse("MMM:home"), target_status_code=302)
        self.assertEqual(self.client.get(reverse("MMM:titlePage")).status_code, 200)

    def test_api_methods_follow_documented_status_codes(self):
        self._confirm_via_browser()
        self.assertEqual(self.client.get(self.draw_url).status_code, 405)
        self.assertEqual(self.client.get(self.end_turn_url).status_code, 405)
        self.assertEqual(self.client.get(self.reset_url).status_code, 405)
        self.assertEqual(self.client.post(self.board_url, {}).status_code, 405)

    def test_api_full_round_through_the_demo_flow(self):
        response = self.client.get(reverse("MMM:createGame", args=[self.human.id]))
        create_html = response.content.decode()
        demo_game_id = int(
            re.search(r'name="newGameIdValue"[^>]*value="(\d+)"', create_html).group(1)
        )

        response = self.client.post(
            reverse("MMM:initializeGame"),
            {
                "newGameIdValue": demo_game_id,
                "challenger": self.human.id,
                "challengePlayer": self.bot.id,
                "startingDeck": self.human_deck.id,
                "startingCard": self.human_cards[0].id,
            },
        )
        self.assertEqual(response.status_code, 302)

        demo_board_url = reverse("MMM:apiBoardState", args=[demo_game_id, self.human.id])

        response = self.client.post(
            reverse("MMM:confirmChallenge", args=[demo_game_id, self.human.id])
        )
        self.assertEqual(response.status_code, 302)

        for drawn_amount in (1, 2):
            response = self._post_json(f"{demo_board_url}draw/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                GameCard.objects.filter(
                    game_id=demo_game_id,
                    user__player_id=self.human.id,
                    state__lane=0,
                ).count(),
                drawn_amount,
            )

        response = self._post_json(f"{demo_board_url}end-turn/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content.decode())["enemyPhasePending"])

        state = self._state_json_at(demo_board_url, "enemy")
        self.assertTrue(state["botTurnRan"])
        self.assertEqual(state["roundNumber"], 2)
        self.assertEqual(state["gameId"], demo_game_id)
        bot_view = next(
            entry for entry in state["participants"]
            if entry["playerId"] == self.bot.id
        )
        self.assertEqual(bot_view["handCount"], 0)
        self.assertGreaterEqual(bot_view["deckCount"], 1)
        self.assertGreater(
            sum(lane["revealedCount"] for lane in bot_view["lanes"]), 0
        )

        idle_state = self._state_json_at(demo_board_url)
        self.assertFalse(idle_state["botTurnRan"])
        self.assertEqual(idle_state["roundNumber"], 2)

    def _state_json_at(self, board_url, phase=None):
        url = board_url if not phase else f"{board_url}?phase={phase}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content.decode())
        return json.loads(response.content.decode())


class TitleGreetingTests(TestCase):
    """First-visit rule and applicability of the title greetings."""

    def _recording_chooser(self):
        offered_candidate_lists = []

        def chooser(candidates):
            offered_candidate_lists.append(list(candidates))
            return candidates[0]

        return offered_candidate_lists, chooser

    def test_first_visit_returns_the_new_visitor_greeting_without_any_pool(self):
        offered_candidate_lists, chooser = self._recording_chooser()

        greeting = title_greeting(False, "Hunters", chooser)

        self.assertEqual(greeting, NEW_VISITOR_GREETING)
        self.assertEqual(offered_candidate_lists, [])

    def test_later_visits_without_name_mention_offer_only_generic_greetings(self):
        offered_candidate_lists, chooser = self._recording_chooser()

        greeting = title_greeting(True, None, chooser)

        self.assertEqual(greeting, GENERIC_GREETINGS[0])
        self.assertEqual(offered_candidate_lists, [GENERIC_GREETINGS])

    def test_later_visits_with_a_logged_in_name_add_name_specific_greetings(self):
        offered_candidate_lists, chooser = self._recording_chooser()

        greeting = title_greeting(True, "Lucas", chooser)

        applicable = applicable_title_greetings("Lucas")
        self.assertEqual(greeting, applicable[0])
        self.assertEqual(offered_candidate_lists, [applicable])
        self.assertEqual(len(applicable), len(GENERIC_GREETINGS) + len(LOGGED_IN_NAME_GREETINGS))
        for greeting_message in applicable[len(GENERIC_GREETINGS):]:
            self.assertIn("Lucas", greeting_message)

    def test_title_page_greets_only_once_and_later_from_the_applicable_pool(self):
        first_response = self.client.get(reverse("MMM:titlePage"))
        self.assertContains(first_response, NEW_VISITOR_GREETING)

        second_response = self.client.get(reverse("MMM:titlePage"))
        greeting_text = re.search(
            r'<p class="demoGreeting">\s*(.*?)\s*</p>',
            second_response.content.decode(),
            re.S,
        ).group(1).strip()
        self.assertNotEqual(greeting_text, NEW_VISITOR_GREETING)
        self.assertIn(greeting_text, applicable_title_greetings(None))


class BoardCardPresentationTests(BattleBoardFixture):
    """Board presentation: trusted cards render on both boards in their own
    rows, hover zoom ships enabled by default with a session toggle, and
    staged plays and flips move real board cards."""

    def _confirm_and_get_board(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)
        return self.client.get(board_url).content.decode()

    def test_trusted_cards_render_for_both_participants(self):
        content = self._confirm_and_get_board()

        enemy_section = re.search(
            r'<ul class="enemyBoards.*?>(.*?)</ul>\s*<ul class="basic-mat table">',
            content, re.DOTALL,
        ).group(1)
        own_section = re.search(
            r'<li class="playerBoard.*?(?=<div class="[^"]*deckHand)',
            content, re.DOTALL,
        ).group(0)

        for section, participant in (
            (enemy_section, self.bot_participant),
            (own_section, self.human_participant),
        ):
            trusted_titles = [
                game_card.card.title
                for game_card in GameCard.objects.filter(
                    game_id=self.game.id,
                    user_id=participant.id,
                    state__trusted=True,
                )
            ]
            self.assertTrue(trusted_titles)

            trusted_rows = "".join(
                re.findall(r'<ul class="cardRow" title="trustedCards">(.*?)</ul>', section, re.DOTALL)
            )
            lane_rows = "".join(
                re.findall(r'<ul class="cardRow" title="cards">(.*?)</ul>', section, re.DOTALL)
            )
            for card_title in trusted_titles:
                self.assertIn(f'title="{card_title} of ', trusted_rows)
                self.assertNotIn(f'title="{card_title} of ', lane_rows)

    def test_board_zoom_is_on_by_default_and_togglable_per_session(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)

        fresh_content = self._confirm_and_get_board()
        self.assertIn('<div class="playerScreen playingCards rotateHand zoomCards">', fresh_content)

        toggle_url = reverse("MMM:toggleCardZoom")
        self.client.post(toggle_url, {"enable": "false"})
        disabled_content = self._confirm_and_get_board()
        self.assertIn('<div class="playerScreen playingCards rotateHand">', disabled_content)
        self.assertNotIn("zoomCards", disabled_content)

        self.client.post(toggle_url, {"enable": "true"})
        enabled_content = self._confirm_and_get_board()
        self.assertIn("zoomCards", enabled_content)

    def test_card_zoom_toggle_lives_on_the_settings_page_session_roundtrip(self):
        settings_url = reverse("MMM:demoSettings")
        response = self.client.get(settings_url)
        content = response.content.decode()
        self.assertRegex(content, r'data-card-zoom="enabled"')
        self.assertRegex(content, r'<form method="post"[^>]*action="%s"' % re.escape(reverse("MMM:toggleCardZoom")))
        self.assertIn('<input type="hidden" name="enable" value="false">', content)
        self.assertIn("Disable hover card zoom", content)

        self.client.post(reverse("MMM:toggleCardZoom"), {"enable": "false"})
        response = self.client.get(settings_url)
        content = response.content.decode()
        self.assertRegex(content, r'data-card-zoom="disabled"')
        self.assertIn('<input type="hidden" name="enable" value="true">', content)
        self.assertIn("Enable hover card zoom", content)

        response = self.client.get(reverse("MMM:toggleCardZoom"))
        self.assertEqual(response.status_code, 302)

    def test_zoom_feature_files_and_board_wiring_contract(self):
        with open(os.path.join(STATIC_TEST_DIR, "cardZoom.css")) as css_file:
            zoom_css = css_file.read()
        with open(os.path.join(STATIC_TEST_DIR, "cardZoom.js")) as js_file:
            zoom_js = js_file.read()

        self.assertIn(".playerScreen.zoomCards", zoom_css)
        self.assertIn("transform: scale(var(--card-zoom-scale));", zoom_css)
        self.assertNotIn("fullscreen", zoom_css)
        self.assertNotIn("Fullscreen", zoom_css)
        self.assertNotIn(":hover", zoom_css)
        for forbidden in ("requestFullscreen", "showModal", "dialog"):
            self.assertNotIn(forbidden, zoom_css)
            self.assertNotIn(forbidden, zoom_js)

        self.assertIn("const ZOOM_CLASS = 'card-zoomed';", zoom_js)
        self.assertIn("release()", zoom_js)
        self.assertIn("event.key === 'Escape'", zoom_js)
        self.assertIn(
            "'.playerScreen .cardContainer:not(.ghost):not(.loading):not(.duplicate)'",
            zoom_js,
        )

        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)
        content = self._confirm_and_get_board()
        self.assertIn("zoomCards", content)
        self.assertIn('<script type="module" src="/static/cardZoom.js">', content)
        self.assertIn('<link rel="stylesheet" type="text/css" href="/static/cardZoom.css">', content)

    def test_staged_play_moves_hand_card(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        action_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)

        hand_card = self._initialize_with_hand_card(self.human_participant, self.human_cards[1])
        self.client.cookies[str(hand_card.id)] = (
            '{"laneValue": 2, "sourceLane": 0, "sourceOrdinal": 99, "flipFaceUp": false}'
        )

        response = self.client.post(action_url, {"action": "play"})

        self.assertNotContains(response, "Action error")
        hand_card.refresh_from_db()
        self.assertEqual(hand_card.state.lane, 2)
        self.assertIn('cardContainer faceDown loading', response.content.decode())

    def test_staged_flip_reveals_face_down_card(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        action_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        self.client.post(confirm_url)

        lane_card = self._initialize_with_hand_card(self.human_participant, self.human_cards[2])
        self.human_participant.playCard(lane_card.id, specialClause=True)
        lane_card.refresh_from_db()
        self.assertTrue(lane_card.state.faceDown)

        self.client.cookies[str(lane_card.id)] = (
            '{"laneValue": 1, "sourceLane": 1, "sourceOrdinal": 1, "flipFaceUp": true}'
        )

        response = self.client.post(action_url, {"action": "play"})

        self.assertNotContains(response, "Action error")
        lane_card.refresh_from_db()
        self.assertFalse(lane_card.state.faceDown)


class DemoNavigationTests(TestCase):
    """Root/title/admin routing plus the anonymous and team demo flows."""

    def setUp(self):
        self.lucas = Player.objects.create(name="Lucas")
        self.lucas_owner = CardOwnerHistory.objects.create(cardOwner=self.lucas)
        self.lucas_card_ids = []
        for index in range(14):
            card = Card.objects.create(
                title=f"Collection-{index}", artSource="", cardType=index % 4
            )
            card.ownerHistory.add(self.lucas_owner)
            self.lucas_card_ids.append(card.id)

    def _created_player(self, name):
        return Player.objects.filter(name=name).first()

    def _latest_team_game(self, team_name):
        team = self._created_player(team_name)
        return (
            Game.objects.filter(history__participants__player=team)
            .latest("id")
            if team
            else None
        )

    def _deck_card_ids(self, deck):
        return sorted(card.id for card in deck.cards.all())

    def _sign_in_admin(self):
        self.client.force_login(_verified_account("paintedpillars", ADMIN_ACCOUNT_EMAIL))

    def test_admin_route_requires_the_designated_admin_account(self):
        anonymous_response = self.client.get(reverse("MMM:index"))
        self.assertRedirects(
            anonymous_response, f"{reverse('account_login')}?next={reverse('MMM:index')}"
        )

        self._sign_in_admin()
        response = self.client.get(reverse("MMM:index"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Players", content)
        self.assertIn("Cards", content)

    def test_admin_page_links_lead_to_the_pages_they_name(self):
        self._sign_in_admin()
        content = self.client.get(reverse("MMM:index")).content.decode()
        player_url = reverse("MMM:viewPlayer", args=[self.lucas.id])
        card_url = reverse("MMM:viewCard", args=[self.lucas_card_ids[0]])
        reset_url = reverse("MMM:resetGames")
        docs_url = reverse("MMM:apiSwaggerUI")
        self.assertIn(f'href="{player_url}"', content)
        self.assertIn(f'href="{card_url}"', content)
        self.assertIn(f'href="{reset_url}"', content)
        self.assertIn(f'href="{docs_url}"', content)
        self.assertEqual(self.client.get(player_url).status_code, 200)
        self.assertEqual(self.client.get(card_url).status_code, 200)
        self.assertRedirects(self.client.get(reset_url, follow=True), reverse("MMM:titlePage"))
        docs_response = self.client.get(docs_url)
        self.assertEqual(docs_response.status_code, 200)
        self.assertIn("Game action API", docs_response.content.decode())

    def test_settings_page_holds_only_the_card_zoom_preference(self):
        self._sign_in_admin()
        response = self.client.get(reverse("MMM:demoSettings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for link in ("Title", "Deck", "Settings", "Admin"):
            self.assertContains(response, link)
        self.assertContains(response, "Card zoom")
        self.assertContains(response, '<input type="hidden" name="enable" value="false">')
        self.assertContains(response, "Disable hover card zoom")
        self.assertNotIn("cardContainer", content)

    def test_settings_page_toggles_card_zoom_from_the_demo_menu(self):
        self._sign_in_admin()
        settings_url = reverse("MMM:demoSettings")

        content = self.client.get(settings_url).content.decode()
        for menu_entry in ("Title", "Deck", "Settings", "Admin"):
            self.assertIn(menu_entry, content)
        self.assertNotIn("Playing as", content)
        self.assertRegex(content, r'data-card-zoom="enabled"')
        self.assertIn("Disable hover card zoom", content)

        self.client.post(reverse("MMM:toggleCardZoom"), {"enable": "false"})
        disabled_content = self.client.get(settings_url).content.decode()
        self.assertRegex(disabled_content, r'data-card-zoom="disabled"')
        self.assertIn("Enable hover card zoom", disabled_content)

        self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Owlbears"})
        owlbears = self._created_player("Owlbears")
        game = self._latest_team_game("Owlbears")
        known_player_settings = self.client.get(settings_url).content.decode()
        self.assertIn("Playing as", known_player_settings)
        self.assertIn("Owlbears", known_player_settings)

        self.client.post(reverse("MMM:confirmChallenge", args=[game.id, owlbears.id]))
        board_url = reverse("MMM:viewBoard", args=[game.id, owlbears.id])
        self.assertNotIn("zoomCards", self.client.get(board_url).content.decode())

        self.client.post(reverse("MMM:toggleCardZoom"), {"enable": "true"})
        self.assertIn("zoomCards", self.client.get(board_url).content.decode())

    def test_back_button_follows_the_demo_pages_but_never_the_title_page(self):
        title_content = self.client.get(reverse("MMM:titlePage")).content.decode()
        self.assertNotIn('class="backlink"', title_content)

        self.client.post(reverse("MMM:play"))
        game = Game.objects.get(title="Annabel vs Lucas")
        annabel = self._created_player("Annabel")
        self.client.get(reverse("MMM:viewGameAsPlayer", args=[game.id, annabel.id]))
        confirm_url = reverse("MMM:confirmChallenge", args=[game.id, annabel.id])
        self.assertRedirects(self.client.post(confirm_url), reverse("MMM:viewBoard", args=[game.id, annabel.id]))

        title_backlink = f'<a class="backlink" href="{reverse("MMM:titlePage")}">back</a>'
        for page_url in (
            reverse("MMM:viewBoard", args=[game.id, annabel.id]),
            reverse("MMM:deckPage"),
            reverse("MMM:demoSettings"),
        ):
            content = self.client.get(page_url).content.decode()
            self.assertEqual(content.count('class="backlink"'), 1)
            self.assertIn(title_backlink, content)

        self.assertNotIn('class="backlink"', self.client.get(reverse("MMM:titlePage")).content.decode())

    def test_back_button_covers_the_admin_pages_too(self):
        self._sign_in_admin()
        admin_root = self.client.get(reverse("MMM:index")).content.decode()
        self.assertEqual(admin_root.count('class="backlink"'), 1)
        self.assertIn(f'<a class="backlink" href="{reverse("MMM:titlePage")}">back</a>', admin_root)

        entry_backlink = f'<a class="backlink" href="{reverse("MMM:home")}">back</a>'
        for page_url in (
            reverse("MMM:viewPlayer", args=[self.lucas.id]),
            reverse("MMM:viewCard", args=[self.lucas_card_ids[0]]),
        ):
            content = self.client.get(page_url).content.decode()
            self.assertEqual(content.count('class="backlink"'), 1)
            self.assertIn(entry_backlink, content)

        started_challenge = self.client.get(reverse("MMM:createGame", args=[self.lucas.id])).content.decode()
        self.assertEqual(started_challenge.count('class="backlink"'), 1)
        self.assertIn(f'<a class="backlink" href="{reverse("MMM:viewPlayer", args=[self.lucas.id])}">back</a>', started_challenge)

        fresh_game = Game.objects.latest("id")
        game_page = self.client.get(reverse("MMM:viewGame", args=[fresh_game.id])).content.decode()
        self.assertEqual(game_page.count('class="backlink"'), 1)
        self.assertIn(entry_backlink, game_page)

    def test_back_button_lies_after_admin_page_content_instead_of_over_it(self):
        """A long collection must never run under the back button.

        The link used generic absolute positioning, so it floated over the
        viewport corner and the player page's cards ran right under it. The
        admin pages now render the link at the end of the document in normal
        flow; only the demo shell pages keep the floating corner link.
        """
        self._sign_in_admin()
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'style.css')) as style_file:
            style_css = style_file.read()
        with open(os.path.join(static_dir, 'demoNavigation.css')) as demo_css_file:
            demo_css = demo_css_file.read()

        backlink_rule = _extract_js_brace_block(style_css, "a.backlink{")
        self.assertIn("font-weight: 800", backlink_rule)
        self.assertNotIn("absolute", backlink_rule)
        self.assertNotIn("fixed", backlink_rule)

        demo_backlink_rule = re.search(r'body\.demoPage a\.backlink\{[^}]*\}', demo_css)
        self.assertIsNotNone(demo_backlink_rule, "demo pages lost their corner back link")
        self.assertIn("position: absolute", demo_backlink_rule.group(0))

        for admin_url in (
            reverse("MMM:index"),
            reverse("MMM:viewPlayer", args=[self.lucas.id]),
            reverse("MMM:apiSwaggerUI"),
        ):
            content = self.client.get(admin_url).content.decode()
            self.assertIn('<body class="">', content)
            self.assertGreater(
                content.index('class="backlink"'),
                content.rindex("</div>"),
                f"back button must follow the content on {admin_url}",
            )

        for demo_url in (reverse("MMM:deckPage"), reverse("MMM:demoSettings")):
            self.assertIn('<body class="demoPage">', self.client.get(demo_url).content.decode())

    def test_admin_pages_never_scroll_horizontally(self):
        """Admin and swagger pages fit the viewport width, vertically only.

        The player page's portrait box carried a negative right margin, so it
        poked past the viewport edge and gave long pages a horizontal scrollbar
        next to the vertical one. The admin pages now wrap that box, and every
        non-demo page clamps horizontal overflow so a second scrollbar can
        never appear; the demo shell pages keep their full-bleed boards.
        """
        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'style.css')) as style_file:
            style_css = style_file.read()
        with open(os.path.join(static_dir, 'demoNavigation.css')) as demo_css_file:
            demo_css = demo_css_file.read()

        player_info_rule = re.search(r'\.playerInfo\{[^}]*\}', style_css)
        self.assertIsNotNone(player_info_rule, "player info rule missing from style.css")
        self.assertNotIn("margin-right: -3rem", player_info_rule.group(0))

        demo_nav_player_info = re.search(r'\.demoNav \.playerInfo\{[^}]*\}', demo_css)
        self.assertIsNotNone(demo_nav_player_info, "demo nav lost its player info margin")
        self.assertIn("margin-right: -3rem", demo_nav_player_info.group(0))

        horizontal_clamp = re.search(r'body:not\(\.demoPage\)\s*\{[^}]*\}', style_css)
        self.assertIsNotNone(horizontal_clamp, "admin pages lack the horizontal clamp")
        self.assertIn("overflow-x: hidden", horizontal_clamp.group(0))

    def test_anonymous_play_opens_the_existing_annabel_vs_lucas_game(self):
        response = self.client.post(reverse("MMM:play"))
        board_url = response["Location"]
        self.assertEqual(response.status_code, 302)
        self.assertTrue(board_url.startswith("/MMM/game/"))
        self.assertTrue(board_url.endswith("/board/%d/" % self._created_player("Annabel").id))

        game = Game.objects.get(title="Annabel vs Lucas")
        self.assertEqual(board_url, reverse("MMM:viewBoard", args=[game.id, self._created_player("Annabel").id]))
        participants = list(game.history.participants.select_related("player"))
        participants_by_player = {
            participant.player.name: participant for participant in participants
        }
        self.assertEqual(
            set(participants_by_player), {"Annabel", "Lucas"}
        )
        self.assertFalse(participants_by_player["Annabel"].computerControlled)
        self.assertTrue(participants_by_player["Lucas"].computerControlled)

        annabel_deck = participants_by_player["Annabel"].deck
        self.assertEqual(len(self._deck_card_ids(annabel_deck)), DEMO_DECK_CARD_COUNT)
        self.assertTrue(set(self._deck_card_ids(annabel_deck)) <= set(self.lucas_card_ids))
        lucas_deck = participants_by_player["Lucas"].deck
        self.assertEqual(len(self._deck_card_ids(lucas_deck)), DEMO_DECK_CARD_COUNT)
        self.assertTrue(set(self._deck_card_ids(lucas_deck)) <= set(self.lucas_card_ids))

        draft_response = self.client.get(board_url)
        self.assertRedirects(
            draft_response,
            reverse("MMM:viewGameAsPlayer", args=[game.id, participants_by_player["Annabel"].player_id]),
        )
        draft = self.client.get(draft_response["Location"])
        self.assertContains(draft, "Annabel vs Lucas game details")
        self.assertContains(draft, "Shuffle the deck and load board")

        confirm_response = self.client.post(
            reverse("MMM:confirmChallenge", args=[game.id, participants_by_player["Annabel"].player_id])
        )
        self.assertRedirects(confirm_response, board_url)
        board = self.client.get(board_url)
        self.assertEqual(board.status_code, 200)
        self.assertIn("Deck: 9 | Hand: 0", board.content.decode())

        resumed = self.client.post(reverse("MMM:play"))
        self.assertEqual(resumed["Location"], board_url)
        self.assertEqual(self.client.get(board_url).status_code, 200)

    def test_owlbears_play_passes_the_draft_and_reaches_lucasbot(self):
        response = self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Owlbears"})
        self.assertEqual(response.status_code, 302)

        owlbears = self._created_player("Owlbears")
        game = self._latest_team_game("Owlbears")
        draft_url = response["Location"]
        self.assertEqual(
            draft_url, reverse("MMM:viewGameAsPlayer", args=[game.id, owlbears.id])
        )

        draft = self.client.get(draft_url)
        self.assertContains(draft, "Owlbears vs Lucasbot game details")
        self.assertContains(draft, "Lucasbot")
        self.assertContains(draft, "Shuffle the deck and load board")

        deck_page = self.client.get(reverse("MMM:deckPage"))
        self.assertContains(deck_page, "Playing as Owlbears")

        confirm = self.client.post(
            reverse("MMM:confirmChallenge", args=[game.id, owlbears.id])
        )
        board_url = confirm["Location"]
        self.assertEqual(board_url, reverse("MMM:viewBoard", args=[game.id, owlbears.id]))
        board = self.client.get(board_url)
        self.assertEqual(board.status_code, 200)
        self.assertIn("Deck: 9 | Hand: 0", board.content.decode())

        participants = {
            participant.player.name: participant
            for participant in game.history.participants.select_related("player")
        }
        self.assertFalse(participants["Owlbears"].computerControlled)
        self.assertTrue(participants["Lucasbot"].computerControlled)
        self.assertEqual(len(self._deck_card_ids(participants["Owlbears"].deck)), DEMO_DECK_CARD_COUNT)
        self.assertTrue(
            set(self._deck_card_ids(participants["Owlbears"].deck)) <= set(self.lucas_card_ids)
        )

        replay = self.client.post(reverse("MMM:play"))
        self.assertEqual(replay["Location"], board_url)

    def test_team_play_returns_to_the_board_of_the_single_in_progress_game(self):
        self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Owlbears"})
        owlbears = self._created_player("Owlbears")
        game = self._latest_team_game("Owlbears")

        self.client.post(reverse("MMM:confirmChallenge", args=[game.id, owlbears.id]))
        board_url = reverse("MMM:viewBoard", args=[game.id, owlbears.id])
        self.assertEqual(self.client.get(board_url).status_code, 200)

        response = self.client.post(reverse("MMM:play"))

        self.assertRedirects(response, board_url, fetch_redirect_response=False)
        self.assertIn("Deck: 9 | Hand: 0", self.client.get(board_url).content.decode())

    def test_team_play_without_a_begun_game_opens_the_draft_game_page(self):
        self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Hunters"})
        hunters = self._created_player("Hunters")
        game = self._latest_team_game("Hunters")

        response = self.client.post(reverse("MMM:play"))

        draft_url = reverse("MMM:viewGameAsPlayer", args=[game.id, hunters.id])
        self.assertRedirects(response, draft_url, fetch_redirect_response=False)
        self.assertContains(self.client.get(draft_url), "Shuffle the deck and load board")

    def test_team_play_with_two_in_progress_games_falls_back_to_the_draft(self):
        self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Owlbears"})
        owlbears = self._created_player("Owlbears")
        first_game = self._latest_team_game("Owlbears")
        self.client.post(reverse("MMM:confirmChallenge", args=[first_game.id, owlbears.id]))

        second_game = create_demo_scenario(
            owlbears, demo_player("Lucasbot"), "Owlbears second begun game"
        )
        battle_services.ensure_game_initialized(second_game)

        response = self.client.post(reverse("MMM:play"))

        draft_url = reverse("MMM:viewGameAsPlayer", args=[second_game.id, owlbears.id])
        self.assertRedirects(response, draft_url, fetch_redirect_response=False)
        self.assertContains(self.client.get(draft_url), "Shuffle the deck and load board")

    def test_hunters_play_passes_the_draft_and_reaches_annabelbot(self):
        response = self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Hunters"})
        self.assertEqual(response.status_code, 302)

        hunters = self._created_player("Hunters")
        game = self._latest_team_game("Hunters")
        draft_url = response["Location"]
        self.assertEqual(draft_url, reverse("MMM:viewGameAsPlayer", args=[game.id, hunters.id]))

        draft = self.client.get(draft_url)
        self.assertContains(draft, "Hunters vs Annabelbot game details")
        self.assertContains(draft, "Annabelbot")

        participants = {
            participant.player.name: participant
            for participant in game.history.participants.select_related("player")
        }
        self.assertFalse(participants["Hunters"].computerControlled)
        self.assertTrue(participants["Annabelbot"].computerControlled)
        self.assertEqual(len(self._deck_card_ids(participants["Hunters"].deck)), DEMO_DECK_CARD_COUNT)

    def test_every_team_selection_deals_a_new_random_ten_card_lucas_deck(self):
        self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Owlbears"})
        first_deck = self._created_player("Owlbears").deck_set.latest("id")
        deck_count_after_first_selection = Deck.objects.count()

        self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Owlbears"})
        second_deck = self._created_player("Owlbears").deck_set.latest("id")

        self.assertEqual(Deck.objects.count(), deck_count_after_first_selection + 1)
        self.assertNotEqual(second_deck.id, first_deck.id)
        self.assertEqual(len(self._deck_card_ids(second_deck)), DEMO_DECK_CARD_COUNT)
        self.assertEqual(second_deck.description, "ten cards from Lucas's collection")
        self.assertTrue(set(self._deck_card_ids(second_deck)) <= set(self.lucas_card_ids))

    def test_changing_team_leaves_the_old_scenario_and_enters_the_new_one(self):
        self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Owlbears"})

        response = self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Hunters"})

        hunters = self._created_player("Hunters")
        game = self._latest_team_game("Hunters")
        self.assertEqual(response["Location"], reverse("MMM:viewGameAsPlayer", args=[game.id, hunters.id]))
        draft = self.client.get(response["Location"])
        self.assertContains(draft, "Hunters vs Annabelbot game details")
        deck_page = self.client.get(reverse("MMM:deckPage"))
        self.assertContains(deck_page, "Playing as Hunters")
        self.assertNotContains(deck_page, "Playing as Owlbears")

    def test_deck_page_name_change_persists_on_the_logged_in_player(self):
        self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Hunters"})
        hunters = self._created_player("Hunters")

        response = self.client.post(reverse("MMM:renameDeckPlayer"), {"name": "Hunters Prime"})

        self.assertEqual(response.status_code, 302)
        hunters.refresh_from_db()
        self.assertEqual(hunters.name, "Hunters Prime")
        deck_page = self.client.get(reverse("MMM:deckPage"))
        self.assertContains(deck_page, "Playing as Hunters Prime")
        self.assertContains(deck_page, 'value="Hunters Prime"')

        self.client.get(reverse("MMM:titlePage"))
        title_page = self.client.get(reverse("MMM:titlePage"))
        self.assertNotContains(title_page, NEW_VISITOR_GREETING)
        self.assertIn(re.search(
            r'<p class="demoGreeting">\s*(.*?)\s*</p>',
            title_page.content.decode(),
            re.S,
        ).group(1).strip(), applicable_title_greetings("Hunters Prime"))

    def test_anonymous_deck_page_shows_teams_without_name_or_deck(self):
        response = self.client.get(reverse("MMM:deckPage"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("You are a visitor", content)
        self.assertIn("Owlbears", content)
        self.assertIn("Hunters", content)
        self.assertNotIn("name=\"name\"", content)
        self.assertNotIn("cardContainer", content)

    def test_unknown_team_selection_is_refused(self):
        with self.assertRaises(Exception):
            self.client.post(reverse("MMM:pickDeckTeam"), {"team": "Cats"})
        self.assertIsNone(self._created_player("Cats"))


class MmmUrlPrefixTests(TestCase):
    """The game owns /MMM/ and nothing else: representative pages and APIs
    resolve under the mount, their unprefixed equivalents route to no game
    view, and static assets stay at the root-relative /static/."""

    def test_reverse_resolves_representative_pages_and_apis_under_the_prefix(self):
        self.assertEqual(reverse("MMM:home"), "/MMM/")
        self.assertEqual(reverse("MMM:titlePage"), "/MMM/title/")
        self.assertEqual(reverse("MMM:play"), "/MMM/play/")
        self.assertEqual(reverse("MMM:resetGames"), "/MMM/game/reset/")
        self.assertEqual(reverse("MMM:index"), "/MMM/admin/")
        self.assertEqual(reverse("MMM:apiSchema"), "/MMM/api/schema/")
        self.assertEqual(reverse("MMM:apiSwaggerUI"), "/MMM/api/docs/")
        self.assertEqual(reverse("MMM:apiResetGames"), "/MMM/api/games/reset/")

    def test_representative_prefixed_pages_and_apis_serve_the_game(self):
        for url in (
            reverse("MMM:titlePage"),
            reverse("MMM:apiSchema"),
            reverse("MMM:apiSwaggerUI"),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
        self.assertRedirects(
            self.client.get(reverse("MMM:index")),
            f"{reverse('account_login')}?next={reverse('MMM:index')}",
        )

    def test_unprefixed_equivalents_do_not_serve_game_views(self):
        for url in (
            "/title/",
            "/play/",
            "/deck/",
            "/settings/",
            "/admin/",
            "/game/reset/",
            "/game/1/board/1/",
            "/api/schema/",
            "/api/docs/",
            "/api/games/reset/",
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404, url)

    def test_static_urls_stay_root_relative_from_the_prefixed_pages(self):
        self.assertEqual(settings.STATIC_URL, "/static/")
        content = self.client.get(reverse("MMM:titlePage")).content.decode()
        self.assertIn('href="/static/style.css"', content)
        self.assertNotIn('"/MMM/static/', content)


class BandSiteTests(TestCase):
    """The archived Painted Pillars band site is served at the domain root
    next to the game at /MMM/: home links every news card to the post's
    own archived URL, releases at /music/ with the /songs/ alias, the
    about biography and the social-links contact page, all with the stage
    photo as a page background behind black-backed paragraphs."""

    BAND_PAGES = {
        "home": "/",
        "music": "/music/",
        "songs": "/songs/",
        "about": "/about/",
        "contact": "/contact/",
    }

    POST_URLS = ["/" + post["url"] for post in NEWS_ITEMS]

    def _page_content(self, page):
        return self.client.get(self.BAND_PAGES[page]).content.decode()

    def _band_urls(self):
        """Every band page: the five sections and each archived news post."""
        return list(self.BAND_PAGES.values()) + self.POST_URLS

    def test_band_routes_resolve_at_the_domain_root(self):
        self.assertEqual(reverse("band_home"), "/")
        self.assertEqual(reverse("band_music"), "/music/")
        self.assertEqual(reverse("band_songs"), "/songs/")
        self.assertEqual(reverse("band_about"), "/about/")
        self.assertEqual(reverse("band_contact"), "/contact/")

    def test_every_band_page_serves_200_with_shared_navigation_and_game_link(self):
        for url in self._band_urls():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            content = response.content.decode()
            for nav_url in ("/", "/music/", "/about/", "/contact/"):
                self.assertIn(f'href="{nav_url}"', content, url)
            self.assertIn('href="/MMM/"', content, url)
            self.assertNotIn('href="/live/"', content, url)
            self.assertNotIn('href="/press-kit/"', content, url)
            self.assertNotIn("wpforms", content, url)
            self.assertNotIn("wp-content", content, url)
            if url != self.BAND_PAGES["contact"]:
                self.assertNotIn('href="/accounts/login/"', content, url)

    def test_songs_alias_serves_the_releases_page(self):
        for url in (self.BAND_PAGES["music"], self.BAND_PAGES["songs"]):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            content = response.content.decode()
            self.assertIn("Answer", content)
            self.assertIn("The Stoic", content)
            self.assertIn("https://open.spotify.com/artist/7FQFAibyxDa9kBjFjSgYpH", content)

    def test_every_archived_post_serves_its_own_page_from_its_home_news_card(self):
        home = self._page_content("home")
        for post in NEWS_ITEMS:
            post_url = "/" + post["url"]
            self.assertEqual(reverse(post["urlName"]), post_url, post["title"])
            self.assertIn(f'href="{post_url}"', home, post["title"])
            response = self.client.get(post_url)
            self.assertEqual(response.status_code, 200, post["title"])
            content = response.content.decode()
            self.assertIn(post["title"], content, post["title"])
            self.assertIn(post["date"], content, post["title"])
            self.assertIn(post["categories"][0], content, post["title"])

    def test_post_pages_hold_the_text_the_snapshots_preserved(self):
        post_texts = {
            "band_post_noorderlicht": (
                "Join us for a vibrant mash-up of music and visual art!",
                "the debut event of Beats &amp; Bites Production",
                "Our last concert was in Leiden",
                "https://noorderlichtcafe.nl/beats-bites/",
                "https://www.patreon.com/user?u=142072920",
                "we’ll send you a download link ourselves if you include your email.",
            ),
            "band_post_juvenile": (
                "calls for infantile behaviour",
                "did we mention the track will feature a glockenspiel?",
                "The whole world is a playground",
            ),
            "band_post_new_recordings": (
                "About two weeks ago we recorded two brand new songs!",
            ),
            "band_post_januari_the_27th": (
                "Curious what kind of song it will be?",
                "performing the song live at Stukafest Delft last year",
                "https://open.spotify.com/playlist/4w7Wlfpb9mmfsSikOs5oN1",
                "https://www.instagram.com/p/Cb8E0CXDxV1/",
            ),
            "band_post_collywobbles": (
                "Get ready to relax and let the day slide away with our new song!",
                "‘A Portrait of the Artist as Young Man’",
                "which is of course a pretext to skip class",
            ),
            "band_post_mary": (
                "a mysterious feeling of sickness and a call for help to a divine mother figure",
                "made by Floris Springintveld",
            ),
            "band_post_shop_window": (
                "At May the 7th we played at the shop window of the Vintage Department Store in Leiden.",
            ),
            "band_post_a_drink": (
                "Best enjoyed in a dark and quiet room.",
            ),
            "band_post_new_studio_session": (
                "recording studio Peggy 51",
            ),
            "band_post_first_music_video": (
                "made in association with student of Grafisch Lyceum Utrecht",
            ),
            "band_post_leidscement": (
                "An interview by Elly Jousma about our first live experience and more.",
                "https://leidscement.nl/podiumkunsten/painted-pillars-van-studentenkamer-naar-de-studio/",
            ),
            "band_post_second_single": (
                "Check out ‘Lovely’ on Spotify and other streaming services.",
            ),
            "band_post_stukafest": (
                "Our debut live performance at Stukafest Leiden was a blast!",
                "Photo by Brian Mul/ Video’s by Stephanie Esajas",
            ),
            "band_post_mare": (
                "Our first interview!",
                "https://www.mareonline.nl/cultuur/de-leden-van-studentenband-painted-pillars-tasten-af-hoe-groot-ze-mogen-dromen/",
            ),
            "band_post_debut_single": (
                "Check out our debut single on Spotify and other streaming services",
            ),
        }
        for url_name, phrases in post_texts.items():
            content = self.client.get(reverse(url_name)).content.decode()
            for phrase in phrases:
                self.assertIn(phrase, content, url_name)
        for_a_while = self.client.get(reverse("band_post_for_a_while")).content.decode()
        self.assertIn("‘For A While’ is out now!", for_a_while)
        self.assertNotIn("bandPostParagraph", for_a_while)

    def test_home_shows_the_listen_cta_and_links_every_archived_news_card(self):
        content = self._page_content("home")
        self.assertIn("Listen to us here!", content)
        self.assertIn('href="/music/"', content)
        self.assertIn("News", content)
        self.assertIn("Upcoming concert at Noorderlicht in Amsterdam", content)
        self.assertIn("A celebration of childishness", content)
        self.assertIn("New studio session", content)
        self.assertIn("We rocked the shop window!", content)
        self.assertIn("Our first music video!", content)
        self.assertIn("Our first interview!", content)
        self.assertIn("band/news/pay.jpg", content)
        self.assertIn("band/news/collywobbles.jpg", content)
        self.assertIn("band/news/a-drink.jpg", content)
        self.assertIn("band/news/first-music-video.jpg", content)
        self.assertIn("band/news/leidscement.png", content)
        self.assertIn("band/news/second-single.jpg", content)
        self.assertIn("band/news/mare.png", content)

    def test_the_stage_photo_is_a_page_background_and_paragraphs_get_black_backings(self):
        home = self._page_content("home")
        self.assertNotIn("bandHeroPhoto", home)
        self.assertNotIn("stage-photo", home)
        with open(os.path.join(STATIC_TEST_DIR, "band.css")) as style_file:
            band_css = style_file.read()
        self.assertNotIn("bandHeroPhoto", band_css)
        self.assertRegex(band_css, r"body::before\s*\{[^}]*url\(\"band/stage-photo.jpg\"\)")
        self.assertRegex(band_css, r"\.bandContent p,\s*\.bandContent li\s*\{[^}]*background-color: var\(--band-background\)")

    def test_music_links_streaming_platforms_and_lists_archived_releases(self):
        content = self._page_content("music")
        self.assertIn("https://open.spotify.com/artist/7FQFAibyxDa9kBjFjSgYpH", content)
        self.assertIn(
            "https://www.youtube.com/watch?v=HDyESqUPBmc&amp;list=PLKC6VD0RhYE4csTWJnUeiLe-R7hJwy6Dj",
            content,
        )
        self.assertIn("https://music.apple.com/gb/artist/painted-pillars/1603642369", content)
        for release_name in (
            "Answer", "Catastrophe", "Bell", "Pay", "Collywobbles",
            "Mary", "A Drink", "For A While", "Lovely", "The Stoic",
        ):
            self.assertIn(release_name, content)
            self.assertIn("https://open.spotify.com/track/", content)

    def test_about_shows_the_archived_band_bio_and_member_descriptions(self):
        content = self._page_content("about")
        self.assertIn("radical eclecticism", content)
        self.assertIn("Pop music as it is meant to be.", content)
        self.assertIn("band/band-photo.jpg", content)
        self.assertIn("Eric Faassen", content)
        self.assertIn("singer and guitarist", content)
        self.assertIn("Rob Müller", content)
        self.assertIn("bassist, cover art painter", content)
        self.assertIn("Lucas Willemsens", content)
        self.assertIn("drummer, poet and computer whisperer", content)

    def test_contact_offers_social_links_without_a_submission_form(self):
        content = self._page_content("contact")
        self.assertIn("https://www.instagram.com/paintedpillars/", content)
        self.assertIn("https://open.spotify.com/artist/7FQFAibyxDa9kBjFjSgYpH", content)
        self.assertIn("https://www.youtube.com/channel/UCPLO8M2TtIZi3aUkXG3psrg", content)
        self.assertIn("https://music.apple.com/gb/artist/painted-pillars/1603642369", content)
        self.assertNotIn("<form", content)
        self.assertNotIn("<input", content)

    def test_band_styling_and_assets_are_served_from_the_local_static_files(self):
        for url in self._band_urls():
            self.assertIn('href="/static/band.css"', self.client.get(url).content.decode(), url)
        for asset in (
            "band.css",
            "band/logo-tile.png",
            "band/logo-header.png",
            "band/stage-photo.jpg",
            "band/band-photo.jpg",
            "band/fonts/lobster.woff2",
            "band/fonts/special-elite.woff2",
            "band/spotify.svg",
            "band/youtube.svg",
            "band/apple-music.svg",
            "band/news/pay.jpg",
            "band/news/collywobbles.jpg",
            "band/news/shop-window.jpg",
            "band/news/a-drink.jpg",
            "band/news/studio-session.jpg",
            "band/news/for-a-while.jpg",
            "band/news/first-music-video.jpg",
            "band/news/leidscement.png",
            "band/news/second-single.jpg",
            "band/news/mare.png",
        ):
            self.assertIsNotNone(finders.find(asset), asset)

    def test_the_game_keeps_working_under_the_mmm_mount_next_to_the_band_site(self):
        self.assertEqual(reverse("MMM:home"), "/MMM/")
        response = self.client.get(reverse("MMM:titlePage"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Magical Masters")


def _link_account(email, player_name):
    """Run the controlled account-to-player link operation the way the
    operator does, and return what it reported."""
    output = StringIO()
    call_command("link_account", email, player_name, stdout=output)
    return output.getvalue()


class AccountRoutesTests(TestCase):
    """The allauth account routes are served at the domain root next to the
    band site and the game at /MMM/: the login page offers Google sign-in,
    and local signups and password logins stay off."""

    def test_account_routes_resolve_at_the_domain_root(self):
        self.assertEqual(reverse("account_login"), "/accounts/login/")

    def test_the_login_page_offers_the_google_provider(self):
        response = self.client.get(reverse("account_login"))
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/accounts/google/login/', response.content.decode())

    def test_local_signup_and_password_routes_stay_off(self):
        for url in ("/accounts/signup/", "/accounts/password/change/"):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_the_game_and_the_band_site_keep_their_routes_next_to_the_accounts(self):
        self.assertEqual(reverse("band_home"), "/")
        self.assertEqual(reverse("MMM:home"), "/MMM/")
        self.assertEqual(self.client.get(reverse("MMM:titlePage")).status_code, 200)


class AccountPlayerLinkingTests(TestCase):
    """The one-to-one link between an authenticated account and a player is
    established only by the controlled linking operation: it refuses
    accounts that never signed in and players that do not exist, creates
    neither, and never lets either side of the link be taken twice."""

    def setUp(self):
        self.admin = _verified_account("paintedpillars", ADMIN_ACCOUNT_EMAIL)
        self.lucas = Player.objects.create(name="Lucas")

    def test_the_operation_links_a_signed_in_account_to_an_existing_player(self):
        output = _link_account(ADMIN_ACCOUNT_EMAIL, "lucas")

        self.assertIn("Lucas", output)
        self.lucas.refresh_from_db()
        self.assertEqual(self.lucas.account, self.admin)
        self.assertEqual(self.admin.player, self.lucas)

    def test_the_operation_matches_email_and_player_name_case_insensitively(self):
        _link_account("PAINTEDpillars@GMAIL.com", "lucas")
        self.lucas.refresh_from_db()
        self.assertEqual(self.lucas.account, self.admin)

    def test_linking_an_existing_link_again_reports_it_and_changes_nothing(self):
        _link_account(ADMIN_ACCOUNT_EMAIL, "lucas")
        output = _link_account(ADMIN_ACCOUNT_EMAIL, "Lucas")

        self.assertIn("already linked", output)
        self.assertEqual(Player.objects.filter(name="Lucas").count(), 1)

    def test_an_account_that_never_signed_in_cannot_claim_a_player(self):
        with self.assertRaises(CommandError):
            _link_account("stranger@gmail.com", "lucas")
        self.assertEqual(get_user_model().objects.count(), 1)
        self.lucas.refresh_from_db()
        self.assertIsNone(self.lucas.account)

    def test_an_unknown_player_is_never_created(self):
        with self.assertRaises(CommandError):
            _link_account(ADMIN_ACCOUNT_EMAIL, "Nobody")
        self.assertFalse(Player.objects.exclude(id=self.lucas.id).exists())

    def test_a_linked_player_cannot_be_linked_to_another_account(self):
        _link_account(ADMIN_ACCOUNT_EMAIL, "lucas")
        _verified_account("someone.else", "someone.else@gmail.com")

        with self.assertRaises(CommandError):
            _link_account("someone.else@gmail.com", "Lucas")
        self.lucas.refresh_from_db()
        self.assertEqual(self.lucas.account, self.admin)

    def test_a_linked_account_cannot_be_linked_to_another_player(self):
        _link_account(ADMIN_ACCOUNT_EMAIL, "lucas")
        ruben = Player.objects.create(name="Ruben")

        with self.assertRaises(CommandError):
            _link_account(ADMIN_ACCOUNT_EMAIL, "Ruben")
        ruben.refresh_from_db()
        self.assertIsNone(ruben.account)
        self.lucas.refresh_from_db()
        self.assertEqual(self.lucas.account, self.admin)

    def test_the_database_rejects_a_second_player_on_one_account(self):
        _link_account(ADMIN_ACCOUNT_EMAIL, "lucas")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Player.objects.create(name="Annabel", account=self.admin)
        self.assertEqual(Player.objects.filter(account=self.admin).count(), 1)


class AdminAccessTests(TestCase):
    """Only the account with the verified designated admin email may enter
    the game's admin pages: anonymous visitors are sent to the login first,
    any other signed-in account is denied on the server, and the admin entry
    stays out of every navigation that account cannot use."""

    def _admin_link(self):
        return f'href="{reverse("MMM:index")}"'

    def test_anonymous_admin_visits_are_sent_to_the_login(self):
        self.assertRedirects(
            self.client.get(reverse("MMM:index")),
            f"{reverse('account_login')}?next={reverse('MMM:index')}",
        )

    def test_any_other_signed_in_account_is_denied(self):
        self.client.force_login(_verified_account("someone.else", "someone.else@gmail.com"))
        self.assertEqual(self.client.get(reverse("MMM:index")).status_code, 403)

    def test_an_unverified_copy_of_the_admin_email_is_denied(self):
        copycat = get_user_model().objects.create_user(
            username="copycat", email=ADMIN_ACCOUNT_EMAIL
        )
        EmailAddress.objects.create(
            user=copycat, email=ADMIN_ACCOUNT_EMAIL, verified=False, primary=True
        )
        self.client.force_login(copycat)
        self.assertEqual(self.client.get(reverse("MMM:index")).status_code, 403)

    def test_the_verified_admin_account_is_granted(self):
        self.client.force_login(_verified_account("paintedpillars", ADMIN_ACCOUNT_EMAIL))
        self.assertEqual(self.client.get(reverse("MMM:index")).status_code, 200)

    def test_the_band_navigation_admin_entry_appears_only_for_the_admin(self):
        band_pages = (reverse("band_home"), reverse("band_music"), reverse("band_about"))
        for page_url in band_pages:
            self.assertNotIn(self._admin_link(), self.client.get(page_url).content.decode())

        self.client.force_login(_verified_account("someone.else", "someone.else@gmail.com"))
        for page_url in band_pages:
            self.assertNotIn(self._admin_link(), self.client.get(page_url).content.decode())
        self.client.logout()

        self.client.force_login(_verified_account("paintedpillars", ADMIN_ACCOUNT_EMAIL))
        for page_url in band_pages:
            self.assertIn(self._admin_link(), self.client.get(page_url).content.decode())

    def test_the_demo_menu_admin_entry_appears_only_for_the_admin(self):
        settings_page = reverse("MMM:demoSettings")
        self.assertNotIn(self._admin_link(), self.client.get(settings_page).content.decode())

        self.client.force_login(_verified_account("someone.else", "someone.else@gmail.com"))
        self.assertNotIn(self._admin_link(), self.client.get(settings_page).content.decode())
        self.client.logout()

        self.client.force_login(_verified_account("paintedpillars", ADMIN_ACCOUNT_EMAIL))
        self.assertIn(self._admin_link(), self.client.get(settings_page).content.decode())

    def test_the_band_navigation_has_no_sign_in_entry(self):
        for page_url in (reverse("band_home"), reverse("band_music"), reverse("band_about")):
            content = self.client.get(page_url).content.decode()
            self.assertNotIn(reverse("account_login"), content)

    def test_the_contact_page_links_anonymous_visitors_to_the_login(self):
        contact = self.client.get(reverse("band_contact"))
        self.assertEqual(contact.status_code, 200)
        content = contact.content.decode()
        self.assertIn(f'href="{reverse("account_login")}"', content)
        self.assertEqual(self.client.get(reverse("account_login")).status_code, 200)

    def test_the_contact_page_sign_in_link_stays_away_from_signed_in_accounts(self):
        self.client.force_login(_verified_account("paintedpillars", ADMIN_ACCOUNT_EMAIL))
        contact = self.client.get(reverse("band_contact"))
        self.assertNotIn(f'href="{reverse("account_login")}"', contact.content.decode())


class LogoutEntryTests(TestCase):
    """The allauth logout entry appears only for signed-in accounts: the
    shared band navigation offers it on every band page, the game's
    settings page offers it below the demo preferences, and posting it
    ends the session and returns to the band home page."""

    def _band_page_urls(self):
        """Every band page sharing the navigation: the five sections and
        each archived news post."""
        section_urls = [
            reverse(name)
            for name in ("band_home", "band_music", "band_songs", "band_about", "band_contact")
        ]
        return section_urls + ["/" + post["url"] for post in NEWS_ITEMS]

    def _logout_form_action(self):
        return f'action="{reverse("account_logout")}"'

    def test_the_shared_band_navigation_offers_logout_only_to_signed_in_accounts(self):
        for page_url in self._band_page_urls():
            self.assertNotIn(
                reverse("account_logout"), self.client.get(page_url).content.decode(), page_url
            )

        self.client.force_login(_verified_account("someone.else", "someone.else@gmail.com"))
        for page_url in self._band_page_urls():
            content = self.client.get(page_url).content.decode()
            self.assertIn(self._logout_form_action(), content, page_url)
            self.assertIn('method="post"', content, page_url)
            self.assertIn("Log out", content, page_url)

    def test_the_settings_page_offers_logout_only_to_signed_in_accounts(self):
        settings_url = reverse("MMM:demoSettings")
        anonymous = self.client.get(settings_url).content.decode()
        self.assertNotIn(reverse("account_logout"), anonymous)

        self.client.force_login(_verified_account("someone.else", "someone.else@gmail.com"))
        signed_in = self.client.get(settings_url).content.decode()
        self.assertIn(self._logout_form_action(), signed_in)
        self.assertIn("Log out", signed_in)

    def test_posting_the_logout_entry_ends_the_session_and_returns_to_the_band_home(self):
        self.client.force_login(_verified_account("someone.else", "someone.else@gmail.com"))
        settings_url = reverse("MMM:demoSettings")
        self.assertIn(self._logout_form_action(), self.client.get(settings_url).content.decode())

        self.assertRedirects(self.client.post(reverse("account_logout")), reverse("band_home"))

        self.assertNotIn(
            self._logout_form_action(), self.client.get(settings_url).content.decode()
        )


class GoogleAccountEndToEndTests(TestCase):
    """The end-to-end account story: a visitor follows the sign-in link on
    the contact page, the designated admin's Google account lands in the
    game linked to the existing Lucas player and reaches the admin pages,
    while a different signed-in account is denied there and never even sees
    the admin link."""

    def test_the_designated_admin_signs_in_and_reaches_the_admin_pages(self):
        lucas = Player.objects.create(name="Lucas")

        contact = self.client.get(reverse("band_contact"))
        self.assertIn(f'href="{reverse("account_login")}"', contact.content.decode())
        login_page = self.client.get(reverse("account_login"))
        self.assertEqual(login_page.status_code, 200)
        self.assertIn('href="/accounts/google/login/', login_page.content.decode())

        # The handshake itself runs on Google's pages; what it returns to the
        # site is the account Google verified. The one-time operation then
        # links that account to the existing Lucas player, creating nothing.
        admin = _verified_account("paintedpillars", ADMIN_ACCOUNT_EMAIL)
        link_output = _link_account(ADMIN_ACCOUNT_EMAIL, "lucas")
        self.assertIn("Lucas", link_output)
        lucas.refresh_from_db()
        self.assertEqual(lucas.account, admin)
        self.assertEqual(Player.objects.filter(name="Lucas").count(), 1)

        self.client.force_login(admin)
        home = self.client.get(reverse("band_home"))
        self.assertIn(f'href="{reverse("MMM:index")}"', home.content.decode())
        admin_page = self.client.get(reverse("MMM:index"))
        self.assertEqual(admin_page.status_code, 200)
        self.assertIn("Lucas", admin_page.content.decode())

    def test_a_different_signed_in_account_is_denied_everywhere(self):
        Player.objects.create(name="Lucas")
        _verified_account("paintedpillars", ADMIN_ACCOUNT_EMAIL)
        _link_account(ADMIN_ACCOUNT_EMAIL, "lucas")
        other = _verified_account("someone.else", "someone.else@gmail.com")
        self.client.force_login(other)

        for page_url in (reverse("band_home"), reverse("band_contact")):
            content = self.client.get(page_url).content.decode()
            self.assertNotIn(f'href="{reverse("MMM:index")}"', content)
        admin_page = self.client.get(reverse("MMM:index"))
        self.assertEqual(admin_page.status_code, 403)
        self.assertNotIn("Lucas", admin_page.content.decode())



def _run_node_harness(harness, label):
    """Execute a generated node harness and return its stdout, skipping when node is absent."""
    import os
    import subprocess
    import tempfile
    from unittest import SkipTest

    try:
        node_binary = subprocess.run(
            ['node', '--version'],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise SkipTest(f'node binary unavailable; skipping {label}')
    if node_binary.returncode != 0:
        raise SkipTest(f'node binary unavailable; skipping {label}')

    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
        handle.write(harness)
        temp_path = handle.name
    try:
        completed = subprocess.run(['node', temp_path], capture_output=True, text=True, check=False)
    finally:
        os.unlink(temp_path)
    if completed.returncode != 0:
        raise AssertionError(
            f'{label} failed:\n'
            f'stdout={completed.stdout}\nstderr={completed.stderr}'
        )
    return completed.stdout


def _read_static_asset(file_name):
    import os

    static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
    with open(os.path.join(static_dir, file_name)) as static_file:
        return static_file.read()


class BoardViewportShortcutUnitTests(TestCase):
    """Zoom/viewport fit and end-turn release-key contracts on the board page."""

    def test_end_turn_hold_release_contract(self):
        drag_js = _read_static_asset('cardDragDrop.js')

        harness = FAKE_ELEMENT_DATASET_CORE + r"""
const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const basicMat = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(basicMat);
const playerBoard = new FakeElement('li', 'playerBoard');
basicMat.appendChild(playerBoard);
const deckHand = new FakeElement('div', 'deckHand handContainer');
basicMat.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const endTurnForm = new FakeElement('form', 'cardActionForm');
handScroll.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) { return body.querySelector(selector); },
    querySelectorAll(selector) { return body.querySelectorAll(selector); },
    getElementById(id) {
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) { (documentListeners[event] ??= []).push(handler); },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    body,
    activeElement: null,
};
const turnLimits = new FakeElement('div');
turnLimits.id = 'turnLimits';
turnLimits.dataset = {
    intCount: '2', spdCount: '0', tactics: '1',
    drawn: '0', played: '0', flipped: '0',
    focusedHandCard: '1',
    drawBlockedTitle: 'draw blocked',
    playBlockedTitle: 'play blocked',
    flipBlockedTitle: 'flip blocked',
};
fakeDocument.getElementById = (id) => {
    if (id === 'turnLimits') return turnLimits;
    return descendantsInOrder(body).find((el) => el.id === id) || null;
};
for (const el of [body, playerScreen, playerBoard, endTurnForm, endTurnButton]) {
    el.focus = () => { fakeDocument.activeElement = el; };
}

global.document = fakeDocument;
const holdTimers = [];
let nextTimerId = 1;
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    location: { pathname: '/MMM/game/1/board/1/' },
    setTimeout(callback) {
        const id = nextTimerId++;
        holdTimers.push({ id, callback });
        return id;
    },
    clearTimeout(id) {
        const index = holdTimers.findIndex((task) => task.id === id);
        if (index !== -1) holdTimers.splice(index, 1);
    },
};
global.CSS = { escape: (value) => String(value) };
global.Element = function Element() {};
global.MutationObserver = function () { this.observe = () => {}; this.disconnect = () => {}; };

const endTurnSubmits = { count: 0 };
endTurnButton.click = () => { endTurnSubmits.count += 1; };

eval(__DRAG_JS__);
(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const keyupHandlers = documentListeners['keyup'] ?? [];
const pressKey = (key, options = {}) => {
    let prevented = false;
    const event = {
        key,
        repeat: options.repeat ?? false,
        target: options.target ?? fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const releaseKey = (key, options = {}) => {
    let prevented = false;
    const event = {
        key,
        repeat: false,
        target: options.target ?? fakeDocument.activeElement,
        preventDefault() { prevented = true; },
    };
    keyupHandlers.forEach((entry) => entry(event));
    return prevented;
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};
const holdLoading = () => endTurnButton.classList.contains('shortcut-hold-loading');
const submits = () => endTurnSubmits.count;
const queuedTimers = () => holdTimers.length;
const flushTimers = () => {
    for (const task of holdTimers.splice(0)) task.callback();
};

fakeDocument.activeElement = endTurnButton;

assert('Space hold starts like the e shortcut',
    pressKey(' ') && holdLoading() && endTurnButton.getAttribute('aria-busy') === 'true' &&
    submits() === 0 && queuedTimers() === 1);
assert('releasing Space before loading completes cancels without submitting',
    releaseKey(' ') && !holdLoading() && endTurnButton.getAttribute('aria-busy') === null &&
    queuedTimers() === 0 && submits() === 0);
flushTimers();
assert('the released Space hold stays silent', submits() === 0);

assert('Enter hold starts like the e shortcut', pressKey('Enter') && holdLoading() && submits() === 0);
assert('releasing Enter before loading completes cancels without submitting',
    releaseKey('Enter') && !holdLoading() && queuedTimers() === 0 && submits() === 0);

assert('the e shortcut still starts its hold', pressKey('e') && holdLoading() && submits() === 0);
assert('releasing e before loading completes cancels', releaseKey('e') && !holdLoading() && submits() === 0);

assert('Space hold submits once when it completes', pressKey(' ') && holdLoading());
flushTimers();
assert('the completed Space hold submitted exactly once', submits() === 1 && !holdLoading());
assert('releasing Space after the submit only resets the protected hold',
    releaseKey(' ') && queuedTimers() === 0 && submits() === 1);

assert('Enter hold completes and submits once too', pressKey('Enter') && holdLoading());
flushTimers();
assert('the completed Enter hold submitted exactly once', submits() === 2 && queuedTimers() === 0);
assert('releasing Enter resets the protected hold', releaseKey('Enter') && queuedTimers() === 0);

assert('repeating Space presses never schedule a second hold',
    pressKey(' ') && pressKey(' ', { repeat: true }) && queuedTimers() === 1);
releaseKey(' ');
assert('repeating Enter presses never schedule a second hold',
    pressKey('Enter', { repeat: true }) && queuedTimers() === 0);

assert('a plain Space keyup without a held activation stays unhandled (draw click stays native)',
    !releaseKey(' '));
assert('a plain Enter keyup without a held activation stays unhandled', !releaseKey('Enter'));

console.log('end turn release keys ok');
""".replace('__DRAG_JS__', repr(drag_js))

        self.assertIn('end turn release keys ok', _run_node_harness(
            harness, 'end-turn release-key hold rehearsal'))

    def test_loading_phases_suppress_key_release_end_turn_submits(self):
        drag_js = _read_static_asset('cardDragDrop.js')
        loading_js = _read_static_asset('loadingAnimations.js')

        for board_phase in ('playerMoves', 'enemy', 'player'):
            harness = FAKE_ELEMENT_DATASET_CORE + r"""
const documentListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const basicMat = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(basicMat);
const playerBoard = new FakeElement('li', 'playerBoard');
basicMat.appendChild(playerBoard);
const deckHand = new FakeElement('div', 'deckHand handContainer');
basicMat.appendChild(deckHand);
const handScroll = new FakeElement('div', 'hand-scroll');
deckHand.appendChild(handScroll);
const endTurnForm = new FakeElement('form', 'cardActionForm');
handScroll.appendChild(endTurnForm);
const endTurnButton = new FakeElement('button', 'end-turn');
endTurnForm.appendChild(endTurnButton);

const phase = '__BOARD_PHASE__';
const turnPhaseEl = new FakeElement('div');
turnPhaseEl.setAttribute('id', 'turnPhase');
turnPhaseEl.setAttribute('data-phase', phase);
turnPhaseEl.dataset = { phase };
body.appendChild(turnPhaseEl);
const boardNext = new FakeElement('div');
boardNext.setAttribute('id', 'boardNext');
boardNext.setAttribute('data-next-url', '/MMM/game/1/board/1/');
body.appendChild(boardNext);

const fakeDocument = {
    documentElement: { contains: () => true },
    querySelector(selector) { return body.querySelector(selector); },
    querySelectorAll(selector) { return body.querySelectorAll(selector); },
    getElementsByClassName(className) {
        const names = String(className).split(/\s+/).filter(Boolean);
        return descendantsInOrder(body).filter((el) =>
            names.every((name) => el.classList && el.classList.contains(name)));
    },
    getElementById(id) {
        for (const el of descendantsInOrder(body)) {
            if (el.id === id) return el;
        }
        return null;
    },
    createElement: (tag) => new FakeElement(tag),
    createElementNS: () => new FakeElement('svg'),
    addEventListener(event, handler) { (documentListeners[event] ??= []).push(handler); },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    hidden: false,
    visibilityState: 'visible',
    readyState: 'complete',
    body,
    activeElement: null,
};
for (const el of [body, playerScreen, playerBoard, deckHand, endTurnForm, endTurnButton]) {
    el.focus = () => { fakeDocument.activeElement = el; };
}

global.document = fakeDocument;
const loadingTimers = [];
global.window = {
    addEventListener() {},
    removeEventListener() {},
    cardDragDrop: null,
    loadingAnimations: null,
    location: { pathname: '/MMM/game/1/board/1/' },
    scrollTo() {},
    setTimeout(callback) { loadingTimers.push(callback); return loadingTimers.length; },
    clearTimeout() {},
};
global.CSS = { escape: (value) => String(value) };
global.Element = function Element() {};
global.MutationObserver = function () { this.observe = () => {}; this.disconnect = () => {}; };
global.requestAnimationFrame = (callback) => 1;

const endTurnSubmits = { count: 0 };
endTurnButton.click = () => { endTurnSubmits.count += 1; };

eval(__DRAG_JS__);
eval(__LOADING_JS__);
(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const system = global.window.cardDragDrop;
if (!system) throw new Error('cardDragDrop not instantiated');
const loading = global.window.loadingAnimations;
if (!loading) throw new Error('loadingAnimations not instantiated');

const keyboardHandlers = documentListeners['keydown'] ?? [];
const keyupHandlers = documentListeners['keyup'] ?? [];
const pressKey = (key, options = {}) => {
    let prevented = false;
    const event = {
        key,
        repeat: options.repeat ?? false,
        target: options.target ?? fakeDocument.activeElement,
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault() { prevented = true; },
    };
    keyboardHandlers.forEach((entry) => entry(event));
    return prevented;
};
const releaseKey = (key, options = {}) => {
    let prevented = false;
    const event = {
        key,
        repeat: false,
        target: options.target ?? fakeDocument.activeElement,
        preventDefault() { prevented = true; },
    };
    keyupHandlers.forEach((entry) => entry(event));
    return prevented;
};
const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};
const holdLoading = () => endTurnButton.classList.contains('shortcut-hold-loading');
const submits = () => endTurnSubmits.count;
const guard = loading._endTurnGuard;

fakeDocument.activeElement = endTurnButton;

if (phase === 'playerMoves' || phase === 'enemy') {
    assert(`the ${phase} phase keeps the loading end turn guard armed`, guard.active === true);
    assert(`Enter on the focused end turn is suppressed during ${phase}`,
        pressKey('Enter') && submits() === 0 && !holdLoading());
    assert(`repeating Enter during ${phase} stays suppressed`,
        pressKey('Enter', { repeat: true }) && submits() === 0);
    assert(`Space on the focused end turn is suppressed during ${phase}`,
        pressKey(' ') && submits() === 0 && !holdLoading());
    assert(`releasing Enter during ${phase} cannot end the turn`,
        releaseKey('Enter') && submits() === 0);
    assert(`releasing Space during ${phase} cannot end the turn`,
        releaseKey(' ') && submits() === 0);
    assert(`the non-activation e key release stays untouched during ${phase}`, !releaseKey('e'));
    assert(`Space elsewhere during ${phase} is not captured by the guard`,
        (fakeDocument.activeElement = deckHand, !pressKey(' ')));
    fakeDocument.activeElement = endTurnButton;
} else {
    assert('the plain player phase leaves the loading end turn guard off', guard.active === false);
    assert('Enter on the focused end turn starts the hold during the player phase',
        pressKey('Enter') && holdLoading() && submits() === 0);
    assert('releasing Enter before loading completes cancels the hold',
        releaseKey('Enter') && !holdLoading() && submits() === 0);
}

console.log('loading end turn guard ok');
""".replace('__BOARD_PHASE__', board_phase).replace('__DRAG_JS__', repr(drag_js)).replace(
                '__LOADING_JS__', repr(loading_js))

            self.assertIn('loading end turn guard ok', _run_node_harness(
                harness, f'loading end-turn guard ({board_phase})'))

    def test_viewport_fit_stages_zoom_compact_and_collapse_the_enemy_board(self):
        stacking_js = _read_static_asset('laneStacking.js')

        harness = r"""
const matchPart = (el, part) => {
    if (!el || !el.tagName) return false;
    const tagMatch = part.match(/^[a-zA-Z][\w-]*/);
    if (tagMatch && el.tagName.toLowerCase() !== tagMatch[0].toLowerCase()) return false;
    const idMatch = part.match(/#([\w-]+)/);
    if (idMatch && (el.id || '') !== idMatch[1]) return false;
    for (const cls of part.match(/\.([\w-]+)/g) || []) {
        if (!el.classList || !el.classList.contains(cls.slice(1))) return false;
    }
    const attrRe = /\[([\w-]+)(?:="([^"]*)")?\]/g;
    let match;
    while ((match = attrRe.exec(part))) {
        const value = el.getAttribute ? el.getAttribute(match[1]) : null;
        if (match[2] === undefined) {
            if (value === null) return false;
        } else if (String(value) !== match[2]) return false;
    }
    const notRe = /:not\(\.([\w-]+)\)/g;
    while ((match = notRe.exec(part))) {
        if (el.classList && el.classList.contains(match[1])) return false;
    }
    if (part.replace(/:not\([^)]*\)/g, '').includes(':')) return false;
    return true;
};
const matchChainFrom = (el, tokens) => {
    const last = tokens[tokens.length - 1];
    if (!matchPart(el, last.part)) return false;
    if (tokens.length === 1) return true;
    const rest = tokens.slice(0, -1);
    if (last.combinator === '>') {
        return Boolean(el.parentNode) && matchChainFrom(el.parentNode, rest);
    }
    let node = el.parentNode;
    while (node) {
        if (matchChainFrom(node, rest)) return true;
        node = node.parentNode;
    }
    return false;
};
const tokenizeChain = (chain) => {
    const tokens = [];
    const re = /(\s*>\s*|\s+)?([^>\s]+)/g;
    let match;
    while ((match = re.exec(chain)) !== null) {
        let combinator = null;
        if (match[1] && match[1].includes('>')) combinator = '>';
        else if (match[1] && match[1].trim() !== '') combinator = ' ';
        tokens.push({ part: match[2], combinator });
    }
    if (tokens.length > 0 && tokens[0].part === ':scope') {
        const [head, ...rest] = tokens;
        rest[0].combinator = '>';
        return rest;
    }
    return tokens;
};
const descendantsInOrder = (root) => {
    const result = [];
    const stack = [...root.children];
    while (stack.length) {
        const node = stack.shift();
        result.push(node);
        stack.unshift(...node.children);
    }
    return result;
};

class FakeElement {
    constructor(tag, className = '') {
        this.tagName = String(tag).toUpperCase();
        this.classes = new Set(String(className).split(/\s+/).filter(Boolean));
        this.attributes = new Map();
        this.dataset = {};
        this.children = [];
        this.parentNode = null;
        this.id = '';
        this.title = '';
        this.clientWidth = 100;
        this.eventHandlers = {};
        const self = this;
        this.classList = {
            add: (...names) => names.forEach((name) => this.classes.add(name)),
            remove: (...names) => names.forEach((name) => this.classes.delete(name)),
            contains: (name) => this.classes.has(name),
        };
        this.style = {
            setProperty: () => {},
            getPropertyValue: () => '',
            getPropertyPriority: () => '',
            removeProperty: () => {},
        };
        this.getBoundingClientRect = () => ({
            left: 0,
            top: 0,
            width: 100,
            height: fakeLayout.heightOf(self),
        });
    }
    get className() { return [...this.classes].join(' '); }
    set className(value) {
        this.classes = new Set(String(value).split(/\s+/).filter(Boolean));
    }
    get offsetWidth() { return 60; }
    matches(selector) {
        return String(selector).split(',').some((part) => part.trim() &&
            matchChainFrom(this, tokenizeChain(part.trim())));
    }
    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches(selector)) return node;
            node = node.parentNode;
        }
        return null;
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
    querySelectorAll(selector) {
        const alternatives = String(selector).split(',').map((part) => tokenizeChain(part.trim()));
        return descendantsInOrder(this).filter((candidate) =>
            alternatives.some((tokens) => matchChainFrom(candidate, tokens)));
    }
    appendChild(child) {
        if (child.parentNode) {
            const index = child.parentNode.children.indexOf(child);
            if (index !== -1) child.parentNode.children.splice(index, 1);
        }
        this.children.push(child);
        child.parentNode = this;
        return child;
    }
    insertBefore(newNode, reference) {
        if (newNode.parentNode) {
            const index = newNode.parentNode.children.indexOf(newNode);
            if (index !== -1) newNode.parentNode.children.splice(index, 1);
        }
        let index = reference ? this.children.indexOf(reference) : this.children.length;
        if (index === -1) index = this.children.length;
        this.children.splice(index, 0, newNode);
        newNode.parentNode = this;
        return newNode;
    }
    setAttribute(name, value) {
        this.attributes.set(name, String(value));
        if (name === 'id') this.id = String(value);
        if (name === 'title') this.title = String(value);
        if (/^[a-zA-Z][\w-]*$/.test(name)) this[name] = String(value);
    }
    getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
    removeAttribute(name) { this.attributes.delete(name); }
    addEventListener(name, handler) { (this.eventHandlers[name] ??= []).push(handler); }
    removeEventListener(name, handler) {
        this.eventHandlers[name] = (this.eventHandlers[name] ?? []).filter((h) => h !== handler);
    }
}

const fakeLayout = {
    viewport: 900,
    zoneHeights: new Map(),
    compactShrink: new Map(),
    heightOf(element) {
        const stored = this.zoneHeights.get(element) ?? 0;
        if (stored === 0) return 0;
        if (element.classList.contains('enemy-board-fit-compact')) {
            return this.compactShrink.get(element) ?? stored;
        }
        return stored;
    },
};

const documentListeners = {};
const windowListeners = {};
const body = new FakeElement('body');
const playerScreen = new FakeElement('div', 'playerScreen');
body.appendChild(playerScreen);
const playersHeader = new FakeElement('div', 'players');
playerScreen.appendChild(playersHeader);
const enemyZone = new FakeElement('ul', 'enemyBoards basic-mat table');
playerScreen.appendChild(enemyZone);
const enemyBoard = new FakeElement('li', 'enemyBoard');
enemyZone.appendChild(enemyBoard);
enemyBoard.appendChild(new FakeElement('h2'));
const enemyDeckHand = new FakeElement('div', 'enemyDeckHand');
enemyBoard.appendChild(enemyDeckHand);
const enemyLanes = new FakeElement('ul', 'lanes');
enemyBoard.appendChild(enemyLanes);
const enemyLane = new FakeElement('li', 'lane Intelligence');
enemyLane.clientWidth = 30;
enemyLanes.appendChild(enemyLane);
const enemyCardRow = new FakeElement('ul', 'cardRow');
enemyCardRow.setAttribute('title', 'cards');
enemyLane.appendChild(enemyCardRow);
for (let index = 0; index < 3; index++) {
    enemyCardRow.appendChild(new FakeElement('li', 'cardContainer'));
}
const playerMat = new FakeElement('ul', 'basic-mat table');
playerScreen.appendChild(playerMat);
const playerBoard = new FakeElement('li', 'playerBoard');
playerMat.appendChild(playerBoard);
const playerLanes = new FakeElement('ul', 'lanes');
playerBoard.appendChild(playerLanes);
const playerLane = new FakeElement('li', 'lane Resolve');
playerLane.clientWidth = 30;
playerLanes.appendChild(playerLane);
const playerCardRow = new FakeElement('ul', 'cardRow');
playerCardRow.setAttribute('title', 'cards');
playerLane.appendChild(playerCardRow);
for (let index = 0; index < 3; index++) {
    playerCardRow.appendChild(new FakeElement('li', 'cardContainer'));
}
const deckHand = new FakeElement('div', 'deckHand');
playerScreen.appendChild(deckHand);

fakeLayout.zoneHeights.set(playersHeader, 120);
fakeLayout.zoneHeights.set(enemyZone, 200);
fakeLayout.compactShrink.set(enemyZone, 140);
fakeLayout.zoneHeights.set(playerBoard, 250);
fakeLayout.zoneHeights.set(deckHand, 150);

const fakeDocument = {
    createElement: (tag) => new FakeElement(tag),
    documentElement: { contains: () => true, clientHeight: 900 },
    querySelector(selector) { return body.querySelector(selector); },
    querySelectorAll(selector) { return body.querySelectorAll(selector); },
    getComputedStyle: () => ({ fontSize: '10px' }),
    addEventListener(event, handler) { (documentListeners[event] ??= []).push(handler); },
    removeEventListener(event, handler) {
        documentListeners[event] = (documentListeners[event] ?? []).filter((h) => h !== handler);
    },
    readyState: 'complete',
    body,
    hidden: false,
    visibilityState: 'visible',
    activeElement: null,
};

global.document = fakeDocument;
global.getComputedStyle = fakeDocument.getComputedStyle;
const pendingTimers = [];
let nextTimerId = 1;
global.window = {
    addEventListener(event, handler) { (windowListeners[event] ??= []).push(handler); },
    removeEventListener() {},
    innerHeight: 900,
    laneCardStacking: null,
    boardViewportFit: null,
};
global.setTimeout = (callback) => {
    pendingTimers.push({ id: nextTimerId, callback });
    return nextTimerId++;
};
global.clearTimeout = (id) => {
    const index = pendingTimers.findIndex((task) => task.id === id);
    if (index !== -1) pendingTimers.splice(index, 1);
};

eval(__STACKING_JS__);
(documentListeners['DOMContentLoaded'] || []).forEach((entry) => entry());
const stacking = global.window.laneCardStacking;
const fit = global.window.boardViewportFit;
if (!stacking || !fit) throw new Error('lane stacking or viewport fit not instantiated');

const assert = (label, condition) => {
    if (!condition) throw new Error('FAILED: ' + label);
    console.log('ok: ' + label);
};
const flushTimers = () => {
    for (const task of pendingTimers.splice(0)) task.callback();
};
const applyResize = () => {
    for (const handler of windowListeners['resize'] ?? []) handler();
    flushTimers();
};
const setViewport = (height) => {
    fakeLayout.viewport = height;
    global.window.innerHeight = height;
    global.document.documentElement.clientHeight = height;
};
const enemyCollapsed = () => enemyBoard.classList.contains('enemy-board-fit-hidden');
const compactActive = () => enemyZone.classList.contains('enemy-board-fit-compact');
const splitRows = (row) => row.parentNode.querySelectorAll('ul.cardRow.overflow-row').length;

assert('both boards overflow-row split through the shared reflow',
    splitRows(enemyCardRow) === 2 && splitRows(playerCardRow) === 2);
assert('a roomy viewport keeps the enemy board fully rendered',
    !enemyCollapsed() && !compactActive());

flushTimers();
assert('loading settle rechecks the fit without new stages',
    !enemyCollapsed() && !compactActive());

setViewport(900);
applyResize();
assert('a very long board stays untouched above the compact threshold',
    !enemyCollapsed() && !compactActive());

setViewport(760);
applyResize();
assert('the confident fit keeps every enemy board at the first compact stage',
    !enemyCollapsed() && !compactActive());

setViewport(700);
applyResize();
assert('zooming changes the enemy board by compacting it while the player stays intact',
    compactActive() && !enemyCollapsed());
assert('the player board never receives a compact or hidden fit class',
    !playerBoard.classList.contains('enemy-board-fit-compact') &&
    !playerBoard.classList.contains('enemy-board-fit-hidden'));

setViewport(560);
applyResize();
assert('when the compact board still overlaps the player zone it collapses completely',
    enemyCollapsed() && !compactActive());
assert('the collapsed enemy zone keeps its list while each board hides fully',
    enemyZone.children.length === 1 && enemyZone.children[0] === enemyBoard &&
    enemyBoard.parentNode === enemyZone);

assert('re-applying the fit gives the same overlap decision', (fit.apply(), enemyCollapsed()));

setViewport(900);
applyResize();
assert('zooming back out restores the complete enemy board',
    !enemyCollapsed() && !compactActive());

console.log('board viewport fit ok');
""".replace('__STACKING_JS__', repr(stacking_js))

        self.assertIn('board viewport fit ok', _run_node_harness(
            harness, 'board viewport fit rehearsal'))

    def test_viewport_and_release_shortcut_source_contract(self):
        drag_js = _read_static_asset('cardDragDrop.js')
        drag_css = _read_static_asset('cardDragDrop.css')
        loading_js = _read_static_asset('loadingAnimations.js')
        stacking_js = _read_static_asset('laneStacking.js')

        self.assertIn('_isEndTurnActivationKey(event) {', drag_js)
        self.assertIn("event.key === ' ' ||", drag_js)
        self.assertIn("event.key === 'Spacebar'", drag_js)
        release_method = drag_js[
            drag_js.index('    onKeyboardKeyUp(event) {'):
            drag_js.index('    _submitHeldEndTurn() {')
        ]
        self.assertIn('this._isEndTurnReleaseKey(event)', release_method)
        self.assertIn('this.endTurnHold.release()', release_method)
        self.assertIn('this._isDrawKey(event) && this.drawHold.release()', release_method)
        self.assertIn(
            'return this._isEndTurnKey(event) || this._isEndTurnActivationKey(event);',
            drag_js,
        )

        self.assertIn('class LoadingEndTurnGuard', loading_js)
        self.assertIn("document.addEventListener('keyup', this.keyupHandler, true)", loading_js)
        guard_code = loading_js[
            loading_js.index('class LoadingEndTurnGuard'):
            loading_js.index('class loadingAnimationsSystem')
        ]
        self.assertIn("'.playerScreen .end-turn'", guard_code)
        guard_run = loading_js[
            loading_js.index("        if (phase === 'playerMoves' || phase === 'enemy'"):
            loading_js.index("        if (phase === 'player') {")
        ]
        self.assertIn('this._endTurnGuard.activate()', guard_run)
        self.assertIn('this._endTurnGuard.deactivate()', guard_run)

        self.assertIn(
            "'.playerBoard .lane, ul.enemyBoards li.enemyBoard ul.lanes li.lane'",
            stacking_js,
        )
        self.assertIn('class BoardViewportFit', stacking_js)
        self.assertIn('SMALL_VIEWPORT_MAX_HEIGHT = 768', stacking_js)
        self.assertIn("COMPACT_CLASS = 'enemy-board-fit-compact'", stacking_js)
        self.assertIn("OVERLAP_HIDDEN_CLASS = 'enemy-board-fit-hidden'", stacking_js)
        self.assertIn('collapseEnemyBoards()', stacking_js)
        apply_code = stacking_js[
            stacking_js.index('    apply() {'):stacking_js.index('    revealEnemyBoards() {')
        ]
        self.assertIn('enemyZone.classList.add(BoardViewportFit.COMPACT_CLASS)', apply_code)
        self.assertLess(
            apply_code.index('enemyZone.classList.add(BoardViewportFit.COMPACT_CLASS)'),
            apply_code.index('this.collapseEnemyBoards()'),
            'compaction must be tried before complete enemy boards are hidden',
        )

        self.assertIn('.shortcut-hold-loading {', drag_css)
        self.assertIn('@keyframes shortcutHoldProgress', drag_css)


class BoardViewportShortcutEndToEndTests(BattleBoardFixture):
    """End turn across loading phases keeps the deferred bot flow reachable and shipped."""

    def test_board_page_ships_viewport_fit_and_release_shortcut_assets(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        scripts = re.findall(r'<script[^>]*src="[^"]*?/static/([a-zA-Z0-9._-]+)"', html)
        links = re.findall(r'<link[^>]*href="[^"]*?/static/([a-zA-Z0-9._-]+)"', html)
        referenced_assets = sorted(set(scripts + links))
        missing = [name for name in referenced_assets if finders.find(name) is None]
        self.assertEqual(missing, [], f"Board references missing static assets: {missing}")

        asset_markers = {
            'cardDragDrop.css': ['shortcut-hold-loading', 'shortcutHoldProgress'],
            'laneStacking.js': ['class BoardViewportFit', 'SMALL_VIEWPORT_MAX_HEIGHT = 768'],
            'loadingAnimations.js': ['class LoadingEndTurnGuard', "phase === 'playerMoves'"],
            'cardDragDrop.js': ['_isEndTurnReleaseKey', 'ShortcutHoldAction'],
        }
        for asset, markers in asset_markers.items():
            self.assertIn(asset, referenced_assets)
            asset_path = finders.find(asset)
            self.assertIsNotNone(asset_path)
            with open(asset_path) as asset_file:
                asset_content = asset_file.read()
            for marker in markers:
                self.assertIn(marker, asset_content)

    def test_end_turn_release_flow_keeps_deferred_bot_once_and_reachable_button(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.get(board_url)
        plain_content = response.content.decode()
        self.assertNotIn('id="turnPhase"', plain_content)
        self.assertContains(response, 'class="end-turn"')
        self.assertRegex(plain_content, r'<button[^>]*class="end-turn"[^>]*autofocus')

        response = self.client.post(end_turn_url, {"action": "end_turn"})
        self.assertEqual(response.status_code, 200)
        moved_content = response.content.decode()
        self.assertNotContains(response, "Action error")
        self.assertIn('data-phase="playerMoves"', moved_content)
        self.assertContains(response, 'class="end-turn"')

        self.game.refresh_from_db()
        bot_lane_before = GameCard.objects.filter(
            game_id=self.game.id,
            user_id=self.bot_participant.id,
            state__lane__gt=0,
        ).count()

        response = self.client.get(board_url)
        enemy_content = response.content.decode()
        self.assertIn('data-phase="enemy"', enemy_content)
        self.assertNotRegex(
            enemy_content,
            r'<button[^>]*class="end-turn"[^>]*autofocus',
        )

        response = self.client.get(board_url)
        player_content = response.content.decode()
        self.assertIn('data-phase="player"', player_content)
        self.assertRegex(player_content, r'<button[^>]*class="end-turn"[^>]*autofocus')

        self.game.refresh_from_db()
        self.assertEqual(self.game.roundNumber, 2)
        bot_lane_after = GameCard.objects.filter(
            game_id=self.game.id,
            user_id=self.bot_participant.id,
            state__lane__gt=0,
        ).count()
        self.assertGreater(bot_lane_after, bot_lane_before)

        settled_content = self.client.get(board_url).content.decode()
        self.assertNotIn('id="turnPhase"', settled_content)
        self.assertRegex(settled_content, r'<button[^>]*class="end-turn"[^>]*autofocus')
        self.assertEqual(Game.objects.get(pk=self.game.id).roundNumber, 2)


class SettingsDeploymentEnvironmentTests(TestCase):
    """mysite settings take their deployment values from MMM_* environment
    variables and keep the local development defaults when those are unset."""

    deployment_environment = {
        "MMM_SECRET_KEY": "settings-test-secret-key",
        "MMM_DEBUG": "false",
        "MMM_ALLOWED_HOSTS": "pr-12.paintedpillars.com,127.0.0.1,localhost",
        "MMM_CSRF_TRUSTED_ORIGINS": "https://pr-12.paintedpillars.com",
        "MMM_SECURE_COOKIES": "true",
        "MMM_DB_PATH": "/tmp/opencode/settings-tests-pr-12.sqlite3",
        "MMM_GOOGLE_CLIENT_ID": "settings-test-google-client-id",
        "MMM_GOOGLE_CLIENT_SECRET": "settings-test-google-client-secret",
        "MMM_ADMIN_EMAIL": "bandadmin@example.com",
        "MMM_ACCOUNT_HTTP_PROTOCOL": "http",
    }
    development_secret_key = 'django-insecure-+40#iiit+*fsij6s#-+8r)#==w-y$@daw)jf%a&dcanwfwj&ly'

    def reload_settings(self, environment):
        with mock.patch.dict(os.environ, environment, clear=True):
            return importlib.reload(mysite.settings)

    def test_deployment_values_come_from_the_environment(self):
        settings_module = self.reload_settings(self.deployment_environment)

        self.assertEqual(settings_module.SECRET_KEY, "settings-test-secret-key")
        self.assertFalse(settings_module.DEBUG)
        self.assertEqual(settings_module.ALLOWED_HOSTS, [
            "pr-12.paintedpillars.com", "127.0.0.1", "localhost",
        ])
        self.assertEqual(settings_module.CSRF_TRUSTED_ORIGINS, [
            "https://pr-12.paintedpillars.com",
        ])
        self.assertTrue(settings_module.SESSION_COOKIE_SECURE)
        self.assertTrue(settings_module.CSRF_COOKIE_SECURE)
        self.assertEqual(
            Path(settings_module.DATABASES["default"]["NAME"]).as_posix(),
            "/tmp/opencode/settings-tests-pr-12.sqlite3",
        )
        self.assertFalse(hasattr(settings_module, "SESSION_COOKIE_DOMAIN"))
        google_app = settings_module.SOCIALACCOUNT_PROVIDERS["google"]["APP"]
        self.assertEqual(google_app["client_id"], "settings-test-google-client-id")
        self.assertEqual(google_app["secret"], "settings-test-google-client-secret")
        self.assertEqual(settings_module.ADMIN_EMAIL, "bandadmin@example.com")
        self.assertEqual(settings_module.ACCOUNT_DEFAULT_HTTP_PROTOCOL, "http")

    def test_local_development_defaults_without_environment(self):
        settings_module = self.reload_settings({})

        self.assertEqual(settings_module.SECRET_KEY, self.development_secret_key)
        self.assertTrue(settings_module.DEBUG)
        self.assertEqual(settings_module.ALLOWED_HOSTS, [])
        self.assertEqual(settings_module.CSRF_TRUSTED_ORIGINS, [])
        self.assertFalse(settings_module.SESSION_COOKIE_SECURE)
        self.assertFalse(settings_module.CSRF_COOKIE_SECURE)
        self.assertEqual(
            settings_module.DATABASES["default"]["NAME"],
            settings_module.BASE_DIR / "db.sqlite3",
        )
        self.assertFalse(hasattr(settings_module, "SESSION_COOKIE_DOMAIN"))
        google_app = settings_module.SOCIALACCOUNT_PROVIDERS["google"]["APP"]
        self.assertEqual(google_app["client_id"], "")
        self.assertEqual(google_app["secret"], "")
        self.assertEqual(settings_module.ADMIN_EMAIL, "paintedpillars@gmail.com")
        self.assertEqual(settings_module.ACCOUNT_DEFAULT_HTTP_PROTOCOL, "https")

    def test_empty_environment_values_fall_back_to_the_defaults(self):
        settings_module = self.reload_settings(
            {name: "" for name in self.deployment_environment}
        )

        self.assertEqual(settings_module.SECRET_KEY, self.development_secret_key)
        self.assertTrue(settings_module.DEBUG)
        self.assertEqual(settings_module.ALLOWED_HOSTS, [])
        self.assertEqual(
            settings_module.DATABASES["default"]["NAME"],
            settings_module.BASE_DIR / "db.sqlite3",
        )
        google_app = settings_module.SOCIALACCOUNT_PROVIDERS["google"]["APP"]
        self.assertEqual(google_app["client_id"], "")
        self.assertEqual(settings_module.ADMIN_EMAIL, "paintedpillars@gmail.com")
        self.assertEqual(settings_module.ACCOUNT_DEFAULT_HTTP_PROTOCOL, "https")

    def tearDown(self):
        self.reload_settings({})


class SessionCookieHostScopeTests(TestCase):
    """Session cookies stay host-only, so a PR environment never shares a
    cookie scope with production or with another PR environment."""

    def test_title_page_sets_a_host_only_session_cookie(self):
        self.assertIsNone(settings.SESSION_COOKIE_DOMAIN)

        response = self.client.get(reverse("MMM:titlePage"))

        session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(session_cookie["domain"], "")
        self.assertTrue(session_cookie.value)
