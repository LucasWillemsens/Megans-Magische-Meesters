import json
import re
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from types import SimpleNamespace
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from . import views
from .models import (
    BattleHistory,
    BattleParticipant,
    Card,
    CardOwnerHistory,
    Deck,
    Game,
    GameCard,
    Player,
)

FAKE_ELEMENT_NAVIGATION_CORE = r'''
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


class BattleFlowTests(TestCase):
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
        hand_cards = re.findall(
            r'<li class="cardContainer [^>]+data-card-id="(\d+)"[^>]*>',
            hand_html,
        )

        self.assertEqual(len(hand_cards), 14)
        self.assertEqual(hand_html.count('name="card_id"'), 14)
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
        self.assertIn("/static/1flubeltje.jpg", content)
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
        self.assertIn(f'href="http://127.0.0.1:8000/card/{generated_card.id}/"', content)
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
        payload = views._parse_play_cookie_value(
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
            for lane in views.contextBoard(
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

        board = views.contextBoard(
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

        views.playcards(
            self.game,
            {
                str(hand_card.id): json.dumps({
                    "laneValue": 4,
                    "sourceLane": 0,
                    "sourceOrdinal": 99,
                    "flipFaceUp": False,
                })
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

        bot_actions, _ = views._run_bot_turn(self.game, self.human.id)

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
        views.intSpecial(self.human_participant, 1, timeline)

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

    def test_draw_renders_drawn_card_loading_from_deck(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        response = self.client.post(draw_url, {"action": "draw"})
        self.assertContains(response, 'cardContainer loading')
        self.assertContains(response, '<div class="card smallCard">')
        self.assertContains(response, "/static/1flubeltje.jpg")
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
        self.assertEqual(
            enemy_deck_hand.group(1).count("data-card-id="),
            bot_deck_count + bot_hand_count,
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

            own_board = views.contextBoard(
                GameCard.objects.filter(game_id=self.game.id),
                self.human_participant.id,
            )
            enemy_board = views.contextBoard(
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
        self.assertNotIn("<button", enemy_section.group(1))

    def test_deck_animation_and_draw_selectors_use_active_deck_only(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'loadingAnimations.js')) as js_file:
            loading_js = js_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()

        self.assertIn('.playerScreen .deckHand .active-deck', loading_js)
        self.assertIn('.enemyDeckHand .active-deck', loading_js)
        self.assertIn('.playerScreen .deckHand .active-deck', drag_js)
        self.assertNotIn(".playerScreen .deckHand .deck')", loading_js)
        self.assertNotIn(".enemyDeckHand .deck')", loading_js)

    def test_end_turn_turn_phase_sequence_across_reloads(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.post(end_turn_url, {"action": "end_turn"})

        self.assertContains(response, 'data-phase="playerMoves"')
        self.assertEqual(response.cookies["turn_phase"].value, "enemy")
        self.assertEqual(
            response.cookies["turn_phase"]["path"],
            f"/game/{self.game.id}/board/{self.human.id}/",
        )

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

        lane_rows = views.contextBoard(
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
        self.assertNotIn("<button", block)
        self.assertNotIn("draggable", block)

        enemy_section = re.search(
            r'<ul class="enemyBoards.*?>(.*?)</ul>\s*<ul class="basic-mat table">',
            content, re.DOTALL
        )
        self.assertIsNotNone(enemy_section)
        self.assertNotIn('tabindex', enemy_section.group(1))
        
        own_board = re.search(
            r'<li class="playerBoard.*?(?=<div class="deckHand">)',
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
            r'<li class="playerBoard.*?(?=<div class="deckHand">)',
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
        self.assertEqual(
            response.cookies["turn_phase"]["path"],
            f"/game/{self.game.id}/board/{self.human.id}/",
        )

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

        # Stage 1 play via cookie (play to lane 4, face-down, no flip)
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

        # Play it face-down to lane 4 (flipFaceUp=false).
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
            '.playerScreen .deckHand .active-deck:not(.blocked) '
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
            '.playerScreen .deckHand .active-deck:not(.blocked) '
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
            '.playerScreen .deckHand .active-deck:not(.blocked) '
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

        stop_block = hover_js[
            hover_js.index('stop() {'):
            hover_js.index('handleMouseMove(event) {')
        ]
        self.assertIn("removeEventListener('mousemove'", stop_block)
        self.assertIn("removeEventListener('mouseleave'", stop_block)
        self.assertIn('this.clearAllHover();', stop_block)
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

    def test_draw_hold_contract_reuses_active_draw_form_and_shared_hold_state(self):
        import os

        static_dir = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static')
        with open(os.path.join(static_dir, 'cardDragDrop.js')) as js_file:
            drag_js = js_file.read()
        with open(os.path.join(static_dir, 'cardDragDrop.css')) as css_file:
            drag_css = css_file.read()

        self.assertIn('this.drawHold = new ShortcutHoldAction();', drag_js)
        self.assertIn("event.key.toLowerCase() === 'd'", drag_js)
        self.assertIn("document.querySelector('.playerScreen .deckHand .active-deck')", drag_js)
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
            r'<li class="playerBoard\s*"[^>]*>.*?</li>\s*</ul>\s*<div class="deckHand">',
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

        lanes_rule = re.search(r'ul\.lanes\s*\{[^}]*\}', cards_css)
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

        deck_hand_rule = re.search(
            r'\.playerScreen\s+\.deckHand\s*\{[^}]*\}', cards_css
        )
        self.assertIsNotNone(deck_hand_rule, ".playerScreen .deckHand rule missing from cards.css")
        deck_hand_body = deck_hand_rule.group(0)
        self.assertIn(
            'margin-top: auto', deck_hand_body,
            ".playerScreen .deckHand must use margin-top: auto to pin itself to the "
            "column bottom regardless of how tall the playerBoard above grows"
        )
        self.assertIn(
            '--hand-row-height', deck_hand_body,
            ".playerScreen .deckHand must declare --hand-row-height so child rows "
            "keep a fixed visible size"
        )

        deck_hand_children_rule = re.search(
            r'\.playerScreen\s+\.deckHand\s*>\s*\.deck\s*,\s*'
            r'\.playerScreen\s+\.deckHand\s*>\s*\.deck-stack\s*,\s*'
            r'\.playerScreen\s+\.deckHand\s*>\s*\.hand\s*,\s*'
            r'\.playerScreen\s+\.deckHand\s*>\s*\.hand-scroll\s*,\s*'
            r'\.playerScreen\s+\.deckHand\s*>\s*\.hand-fan\s*\{[^}]*\}',
            cards_css,
        )
        self.assertIsNotNone(
            deck_hand_children_rule,
            ".playerScreen .deckHand child-row rule missing from cards.css"
        )
        self.assertIn(
            'height: var(--hand-row-height)', deck_hand_children_rule.group(0),
            "deckHand child rows must keep a fixed height of var(--hand-row-height) "
            "so the deck stack / hand fan / end-turn button stay the same visible "
            "size as the playerBoard grows above them"
        )

    def test_deck_draw_animation_does_not_insert_into_deck(self):
        """Deck draws overlay the pile via fixed positioning instead of shifting it."""
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
        self.assertIn('document.body.appendChild', deck_branch)
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
            'this._keyboardSelectionControl._isStagedGhost_Legacy(card)',
            parent_class,
        )
        self.assertIn(
            'this._keyboardSelectionControl._isOrderableKeyboardCard_Legacy(card)',
            parent_class,
        )
        self.assertIn(
            'this._keyboardSelectionControl._isGhostFlipCandidate_Legacy(card)',
            parent_class,
        )
        self.assertIn(
            'this._keyboardSelectionControl._stagedLaneForGhost_Legacy(card)',
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
            r'<li class="playerBoard.*?(?=<div class="deckHand">)',
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
            'this._keyboardSelectionControl._isStagedGhost_Legacy(card)',
            parent_class,
        )
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
            r'<li class="playerBoard.*?(?=<div class="deckHand">)',
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
    location: { pathname: '/game/1/action/' },
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

const flipCardFirst = makeFaceDownFieldCard(561);
const flipCardSecond = makeFaceDownFieldCard(563);
const flipCardUnflipped = makeFaceDownFieldCard(565);
const stagedPlayClone = makeStagedPlayGhost(700);

const deckHand = new FakeElement('div', 'deckHand');
playerScreen.appendChild(deckHand);
const handList = new FakeElement('ul', 'hand');
deckHand.appendChild(handList);
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
        self.assertIn('this.parent._focusArrowTarget(card)', on_focus_in)
        self.assertIn('this._focusArrow.source === card', on_focus_in)
        self.assertIn('this._focusArrow.target === target', on_focus_in)
        self.assertIn('this._focusArrow.arrow.remove()', on_focus_in)
        self.assertIn('this.parent._createFocusArrow(card, target)', on_focus_in)
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
const playerBoard = new FakeElement('div', 'playerBoard');
playerScreen.appendChild(playerBoard);

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

const deckHand = new FakeElement('div', 'deckHand');
playerScreen.appendChild(deckHand);
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
global.window = { addEventListener() {}, removeEventListener() {}, cardDragDrop: null, location: { pathname: '/x/action' } };
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
const playerBoard = new FakeElement('div', 'playerBoard');
playerScreen.appendChild(playerBoard);

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

const deckHand = new FakeElement('div', 'deckHand');
playerScreen.appendChild(deckHand);
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
global.window = { addEventListener() {}, removeEventListener() {}, cardDragDrop: null, location: { pathname: '/x/action' } };
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
const playerBoard = new FakeElement('div', 'playerBoard');
playerScreen.appendChild(playerBoard);

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

const deckHand = new FakeElement('div', 'deckHand');
playerScreen.appendChild(deckHand);
const activeDeck = new FakeElement('ul', 'deck active-deck');
deckHand.appendChild(activeDeck);
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
global.window = { addEventListener() {}, removeEventListener() {}, cardDragDrop: null, location: { pathname: '/x/action' } };
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

const deckHand = new FakeElement('div', 'deckHand');
playerScreen.appendChild(deckHand);
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
global.window = { addEventListener() {}, removeEventListener() {}, cardDragDrop: null, location: { pathname: '/x/action' } };
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
const playerBoard = new FakeElement('div', 'playerBoard');
playerScreen.appendChild(playerBoard);

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

const deckHand = new FakeElement('div', 'deckHand');
playerScreen.appendChild(deckHand);
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
    location: { pathname: '/game/1/board/1/action/' },
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
            '.playerScreen .deckHand .active-deck button.draw',
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
        self.assertIn("region === 'draw' && direction === 'ArrowUp'", navigate_method)
        self.assertIn("region === 'draw' && direction === 'ArrowDown'", navigate_method)
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
        self.assertNotIn("region === 'draw' && direction === 'ArrowLeft'", navigate_method)
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

const deckHand = new FakeElement('div', 'deckHand');
playerScreen.appendChild(deckHand);
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
    location: { pathname: '/game/1/board/1/action/' },
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
            f"/game/{game_id}/{challenger.id}/",
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
            f"/game/{game_id}/{challenger.id}/",
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
            f"/game/{game_id}/{challenger.id}/",
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

        expected_url = f"http://127.0.0.1:8000/game/{game.id}/board/{challenger.id}/"
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
                f'href="http://127.0.0.1:8000/game/{game.id}/board/{challenger.id}/" '
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
        absolute_player_url = f"http://127.0.0.1:8000{player_url}"

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
        self.assertContains(default_response, f'href="{absolute_player_url}"')
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
                f'href="{absolute_player_url}?sort={sort_key}"',
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
            f'href="{absolute_player_url}?sort=name"',
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
        from MMM.views import visSpecial

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
        result = visSpecial(self.human_participant, 5, timeline=timeline)

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
        from MMM.views import intSpecial
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
            intSpecial(self.human_participant, 3, timeline)
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

        rule_match = re.search(r'\.debug-overlay-visible[^{]*\{[^}]*\}', cards_css)
        self.assertIsNotNone(rule_match, "No .debug-overlay-visible CSS rule found")

        rule_body = rule_match.group(0)
        self.assertIn('position: absolute', rule_body)
        self.assertIn('background: white', rule_body)
        self.assertIn('z-index: 3', rule_body)

        for forbidden in ('top:', 'width: ', 'left: ', 'height: '):
            self.assertNotIn(forbidden, rule_body)

    def test_backtick_overlay_targets_exist_in_rendered_board(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        response = self.client.get(reverse("MMM:viewBoard", args=[self.game.id, self.human.id]))
        content = response.content.decode()

        player_section_match = re.search(
            r'<div class="deckHand">\s*(.*?)<div class="deck-stack',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(
            player_section_match,
            "Could not locate <div class=\"deckHand\"> opening in rendered board",
        )
        player_p_match = re.match(
            r'\s*<p[^>]*>([\s\S]*?)</p>',
            player_section_match.group(1),
        )
        self.assertIsNotNone(
            player_p_match,
            "Player deck/hand counter <p> is not the first direct child of "
            "<div class=\"deckHand\">",
        )
        self.assertIn('Deck:', player_p_match.group(1))
        self.assertIn('| Hand:', player_p_match.group(1))

        enemy_section_match = re.search(
            r'<div class="enemyDeckHand">\s*(.*?)<div class="deck-stack enemy-deck-stack"',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(
            enemy_section_match,
            "Could not locate <div class=\"enemyDeckHand\"> opening in rendered board",
        )
        enemy_p_match = re.match(
            r'\s*<p class="cardType"[^>]*>([\s\S]*?)</p>',
            enemy_section_match.group(1),
        )
        self.assertIsNotNone(
            enemy_p_match,
            "Enemy deck/hand counter <p class=\"cardType\"> is not the first direct child of "
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
            r'<p[^>]*>[\s\S]*?Deck:[^<]*\| Hand:[^<]*</p>',
            "Player counter <p> must not be inside <script>, <template>, or hidden <div>",
        )
        self.assertRegex(
            scrubbed,
            r'<p class="cardType"[^>]*>[\s\S]*?Deck:[^<]*\| Hand:[^<]*</p>',
            "Enemy counter <p class=\"cardType\"> must not be inside dev-only blocks",
        )
        for lane_name in ('Intelligence', 'Speed', 'Visciousness', 'Resolve'):
            self.assertRegex(
                scrubbed,
                rf'<p[^>]*>[\s\S]*?\|\s*{lane_name}\s*</p>',
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
        visible_rule = re.search(
            r'\.playerScreen\s+\.deckHand\s*>\s*p\.debug-overlay-visible[^{]*\{[^}]*\}',
            cards_css,
        )
        self.assertIsNotNone(visible_rule, "No <p> debug-overlay-visible CSS rule found")
        body = visible_rule.group(0)
        self.assertIn('position: absolute', body)
        self.assertIn('background: white', body)
        self.assertIn('z-index: 3', body)

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
