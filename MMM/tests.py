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

    def test_hand_fans_preserve_order_and_repeat_every_thirteen_cards(self):
        self.client.post(reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id]))
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        for hand_count, expected_fan_sizes in (
            (13, [13]),
            (14, [13, 1]),
            (26, [13, 13]),
            (27, [13, 13, 1]),
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

        self.assertEqual([fan.count("cardContainer") for fan in fan_matches], [13, 1])
        for fan in fan_matches:
            self.assertEqual(fan.count("blocked"), fan.count("cardContainer"))
            self.assertEqual(
                len(re.findall(r'<li class="cardContainer[^>]*draggable="false"', fan)),
                fan.count("cardContainer"),
            )

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

        # Draw limit per turn is based on stats (intCount+1), so draw in
        # multiple rounds.  The important assertion is that no duplicates
        # ever appear in the hand.
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

        # the board GET carrying the enemy phase runs the bots exactly once
        self.client.get(board_url)
        self.game.refresh_from_db()
        after = bot_state()
        self.assertGreater(after["lane"], before["lane"])
        self.assertEqual(self.game.roundNumber, 2)

        # the phase cookie is single-use: further GETs never re-run the bots
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

        # the reload after 'end turn' carries the enemy phase, runs the bots
        # and renders their moves as loading animations with the source
        # lane/ordinal the cards came from
        response = self.client.get(board_url)
        self.assertContains(response, 'data-phase="enemy"')
        self.assertContains(response, 'cardContainer loading')

        # the loading card's data-source-* must describe where the card came
        # from (the bot drew from the deck: source ordinal 0), not the card's
        # final position in the lane
        loading_tag = re.search(
            r'<li class="cardContainer loading"[^>]*>', response.content.decode()
        )
        self.assertIsNotNone(loading_tag)
        self.assertIn('data-source-lane="-', loading_tag.group(0))
        self.assertIn('data-source-ordinal="0"', loading_tag.group(0))

        # the next board load lands clean with no animations
        self.client.cookies = SimpleCookie()
        response = self.client.get(board_url)
        self.assertNotContains(response, "cardContainer loading")

    def test_draw_renders_drawn_card_loading_from_deck(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        draw_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        # the player's draw is recorded server-side as a play, so the action
        # response itself renders the drawn hand card as a loading animation
        # (mirroring the bot draw flow, no cookie round-trip)
        response = self.client.post(draw_url, {"action": "draw"})
        self.assertContains(response, 'cardContainer loading')
        self.assertContains(response, 'class="cardActionButton')
        self.assertContains(response, "/static/1flubeltje.jpg")
        self.assertContains(response, 'data-source-lane="-')

        # the loading card's data-source-* must describe where the card came
        # from (the top of the deck: negative source lane, deck ordinal 0),
        # not the card's final position in the hand
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

        self.assertContains(response, 'class="cardActionButton')
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

        # the draw play is server-recorded, not cookie-staged: the response
        # sets no digit-named cookie for the drawn card (cookies are only for
        # cross-request plays, but the draw animates on this very response)
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
                r'<div class="deck-stack own-deck-stack">(.*?)<div class="hand-scroll"[^>]*>',
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
                    self.assertIn("inert", indicator)
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

        # the end_turn POST render plays the player's own moves and signals the
        # enemy phase to the next render via the turn phase cookie
        self.assertContains(response, 'data-phase="playerMoves"')
        self.assertEqual(response.cookies["turn_phase"].value, "enemy")
        self.assertEqual(
            response.cookies["turn_phase"]["path"],
            f"/game/{self.game.id}/board/{self.human.id}/",
        )

        # the reload renders the enemy phase and hands the player's own turn
        # marker off to the final reload
        response = self.client.get(board_url)
        self.assertContains(response, 'data-phase="enemy"')
        self.assertEqual(response.cookies["turn_phase"].value, "player")
        # the handoff cookie must survive a real browser: a delete-then-set of
        # the same cookie on one response leaves the delete's Max-Age=0 on the
        # fresh value, and browsers then drop the cookie instantly (the test
        # client ignores expiry, which is why this must be asserted explicitly)
        self.assertEqual(response.cookies["turn_phase"]["max-age"], "")
        self.assertEqual(response.cookies["turn_phase"]["expires"], "")

        # the final reload marks the start of the player's turn and clears the
        # turn phase cookie (clear-after-render, like the play cookies)
        response = self.client.get(board_url)
        self.assertContains(response, 'data-phase="player"')
        self.assertEqual(response.cookies["turn_phase"].value, "")
        self.assertEqual(response.cookies["turn_phase"]["max-age"], 0)

        # the turn sequence is over: the board lands clean afterwards
        self.client.cookies = SimpleCookie()
        response = self.client.get(board_url)
        self.assertNotContains(response, "data-phase=")

    def test_enemy_phase_renders_even_without_bot_actions(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        # leave the bot with nothing to draw and nothing to play
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

        # no bot action cookies, but the turn sequence still runs so the enemy
        # marker always appears at the start of the enemy turn
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

        # Leave exactly one bot card in the deck and give the bot only a
        # Resolve stat.  Its last draw therefore triggers the Resolve special.
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

        # The browser's next reload must be the player's phase, not another
        # enemy-phase render that can show the marker again.
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

        # a drawn enemy card in the hand is marked loading with its deck
        # position as the animation source (negative source lane)
        self.assertEqual(updated[0].cssClass, "loading")
        self.assertEqual(updated[0].state.lane, -2)
        # the source ordinal must land in state.laneOrdinal: that is what the
        # template renders as data-source-ordinal (a throwaway 'ordinal'
        # attribute used to leave the final ordinal in the markup)
        self.assertEqual(updated[0].state.laneOrdinal, 0)

    def test_update_played_cards_marks_source_state(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        # let the bot play a card to a lane so there is an untrusted lane
        # card (the trusted starting card lives in trustedCards, which
        # _update_played_cards deliberately does not animate)
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
        # data-source-* point at the hand the card came from, not at the
        # card's final position in the lane
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

        # a manually staged play cookie naming another participant's card must
        # never be consumed: playcards() only executes the acting
        # participant's own cookies
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

        # both participants start with empty hands (the starting card is
        # played straight to a lane), so no setup is needed here
        self.assertFalse(
            GameCard.objects.filter(game_id=self.game.id, state__lane=0).exists()
        )

        response = self.client.get(board_url)
        content = response.content.decode()

        # the player's own empty hand keeps its empty-hand indicator...
        self.assertEqual(content.count("emptyHand"), 1)

        # ...but an empty enemy hand renders nothing at all
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
        response = self.client.get(board_url)
        content = response.content.decode()

        # the enemy deck/hand is display-only: no forms, buttons or draggable
        # elements (interactivity is also never bound to it in cardDragDrop.js)
        enemy_deck_hand = re.search(
            r'<div class="enemyDeckHand">(.*?)<ul class="lanes">', content, re.DOTALL
        )
        self.assertIsNotNone(enemy_deck_hand)
        block = enemy_deck_hand.group(1)
        self.assertNotIn("<form", block)
        self.assertNotIn("<button", block)
        self.assertNotIn("draggable", block)

        # the player's own controls are untouched (the deck still draws)
        self.assertContains(response, 'class="card back draw"')

    def test_game_ending_end_turn_renders_player_moves_instead_of_redirecting(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        # force the game to be over before the end_turn POST
        self.human_participant.defeated = True
        self.human_participant.save()

        response = self.client.post(end_turn_url, {"action": "end_turn"})

        # the game-ending action renders its own moves instead of
        # short-circuiting to the result page: the turn-phase chain plays out
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-phase="playerMoves"')
        # the playerMoves render always targets the board URL: the final bot
        # moves still have to run and play out in the enemy phase
        self.assertContains(response, f'data-next-url="{board_url}"')
        # boardAction keeps handing "enemy" to the next render even when
        # finished: the enemy phase is where the final bot moves play
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

        # the following board GET carries the enemy phase: the bot turn runs
        # here and the enemy phase still renders (final bot moves + markers),
        # but its navigation target is the result page
        response = self.client.get(board_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-phase="enemy"')
        self.assertContains(response, f'data-next-url="{result_url}"')

        # the phase chain terminates on game end: the turn phase cookie is
        # deleted (empty value, max-age 0) instead of handing off "player" -
        # a finished game never shows the "Your turn" marker
        self.assertEqual(response.cookies["turn_phase"].value, "")
        self.assertEqual(response.cookies["turn_phase"]["max-age"], 0)

        # and with the phase cookie gone, the next plain board visit skips
        # straight to the results
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
        self.assertIn(drawable_draw + ':hover', cards_css)
        self.assertIn(drawable_draw + ':focus-visible', cards_css)
        self.assertIn('transition: transform 0.15s ease-out', cards_css)
        self.assertIn('transform: rotate(', cards_css)

    def test_hand_card_visibility_css_keeps_footer_and_body_separated(self):
        """Hand cards keep readable type labels and leave static symbols above the footer."""
        import os

        css_path = os.path.join(os.path.dirname(__file__), '..', 'var', 'www', 'static', 'cards.css')
        with open(css_path) as css_file:
            cards_css = css_file.read()

        self.assertNotIn('font-size: 7px', cards_css)
        self.assertNotIn('margin-bottom: -2.75rem', cards_css)
        self.assertIn('font-size: 0.65rem', cards_css)
        self.assertIn('line-height: 1.1', cards_css)
        self.assertIn('white-space: nowrap', cards_css)
        self.assertIn('height: var(--hand-row-height)', cards_css)
        self.assertIn('margin-bottom: 0', cards_css)
        self.assertIn('.playingCards .card.smallCard.staticCard .suit::after', cards_css)
        self.assertIn('bottom: 1.25rem', cards_css)

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
        self.assertIn('HAND_FAN_SIZE = 13', loading_js)
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
        self.assertIn("if (key === '0')", drag_js)
        self.assertIn('keyboard-preview', drag_js)
        self.assertIn('clearKeyboardSelection', drag_js)
        self.assertIn('createupdateCookie', drag_js)
        selection_code = drag_js[
            drag_js.index('    selectKeyboardCard(card'):
            drag_js.index('    onCardDragStart(e)')
        ]
        self.assertNotIn('createupdateCookie', selection_code)
        self.assertIn('li.cardContainer.keyboard-selected', drag_css)
        self.assertIn('.hologram.keyboard-preview', drag_css)

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
        self.assertIn('this.staged.plays++;', staging_code)
        self.assertIn('this.applyTurnAffordances();', staging_code)

        keyboard_preview_code = drag_js[
            drag_js.index('        if (keyboardPreview) {', drag_js.index('    _buildPlayHologram(')):
            drag_js.index('        } else {', drag_js.index('    _buildPlayHologram('))
        ]
        self.assertNotIn('onFaceDownCardClick', keyboard_preview_code)
        self.assertIn("hologram.classList.add('keyboard-preview')", drag_js)
        self.assertIn("hologram.classList.add('keyboard-staged')", drag_js)

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

        # In the player lanes section, every hologramRow must appear
        # before the first cardRow of its lane.  Check the raw ordering
        # of hologramRow relative to cardRow within the ownLaneRows loop.
        player_board = re.search(
            r'<li class="playerBoard\s*"[^>]*>.*?</li>\s*</ul>\s*<div class="deckHand">',
            content, re.DOTALL
        )
        self.assertIsNotNone(player_board, "Could not find playerBoard section in rendered HTML")
        pb_html = player_board.group(0)

        # Search for the sequence inside the player board's own lanes:
        #   lane opening -> hologramRow -> cardRow
        # for each of the 4 player lanes.
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

        expected_url = f"http://127.0.0.1:8000/game/{game.id}/{challenger.id}"
        self.assertContains(
            response,
            f'<a class="challenge-card-link" href="{expected_url}" draggable="false">',
        )
        self.assertContains(response, '<li class="challenge-card">')
        self.assertContains(response, '<h3 class="challenge-card-title">Game 1</h3>')
        self.assertContains(response, "lootPile: Loot card")
        self.assertContains(response, "(Started ")
        self.assertContains(response, "Meg")
        self.assertContains(response, "versus")
        self.assertContains(response, "Opponent")

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

        self.assertIn(".challenge-card-link {", style_css)
        self.assertIn("display: block;", style_css)
        self.assertIn(".challenge-card-link:hover", style_css)
        self.assertIn(".challenge-card-link:focus-visible", style_css)
        self.assertIn(".challenge-card-subtitle", style_css)
        self.assertIn("flex-direction: column;", style_css)
        self.assertIn(".challenge-participants", style_css)

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
            f"game/{game.id}/{player.id}",
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
