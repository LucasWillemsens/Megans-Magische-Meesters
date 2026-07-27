import json
import re
from http.cookies import SimpleCookie

from django.test import TestCase
from django.urls import reverse

from . import views
from .models import (
    BattleHistory,
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

    def test_end_turn_advances_round_and_bot_plays(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)

        bot_cards_before = GameCard.objects.filter(
            game_id=self.game.id,
            user_id=self.bot_participant.id,
            state__lane__gt=0,
        ).count()

        self.client.post(end_turn_url, {"action": "end_turn"})

        self.game.refresh_from_db()
        bot_cards_after = GameCard.objects.filter(
            game_id=self.game.id,
            user_id=self.bot_participant.id,
            state__lane__gt=0,
        ).count()

        self.assertEqual(self.game.roundNumber, 2)
        self.assertGreater(bot_cards_after, bot_cards_before)

    def test_end_turn_sets_bot_action_cookies_for_viewing_board(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        response = self.client.post(end_turn_url, {"action": "end_turn"})

        bot_cookies = {
            name: morsel for name, morsel in response.cookies.items() if name.isdigit()
        }
        self.assertTrue(bot_cookies)
        for morsel in bot_cookies.values():
            # a browser only returns cookies whose path prefixes the request
            # URL, so bot action cookies must be scoped to the viewing player's
            # board for the enemy animations to render there.
            self.assertEqual(morsel["path"], f"/game/{self.game.id}/board/{self.human.id}/")
            payload = json.loads(morsel.value)
            self.assertIn("laneValue", payload)
            self.assertIn("sourceLane", payload)
            self.assertIn("sourceOrdinal", payload)
            self.assertIn("flipFaceUp", payload)

    def test_board_reload_renders_and_clears_enemy_animations(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        end_turn_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])
        board_url = reverse("MMM:viewBoard", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        end_turn_response = self.client.post(end_turn_url, {"action": "end_turn"})
        bot_cookie_names = [
            name for name in end_turn_response.cookies if name.isdigit()
        ]
        self.assertTrue(bot_cookie_names)

        # the reload after 'end turn' carries the bot cookies back to the
        # viewing player's board, which renders the enemy actions as loading
        # animations with their source lane/ordinal.
        response = self.client.get(board_url)
        self.assertContains(response, 'cardContainer loading')
        self.assertContains(response, 'data-source-lane="-')

        # the loading card's data-source-* must describe where the card came
        # from (the bot drew from the deck: source ordinal 0), not the card's
        # final position in the lane
        loading_tag = re.search(
            r'<li class="cardContainer loading"[^>]*>', response.content.decode()
        )
        self.assertIsNotNone(loading_tag)
        self.assertIn('data-source-lane="-', loading_tag.group(0))
        self.assertIn('data-source-ordinal="0"', loading_tag.group(0))

        # the render clears the bot cookies again (existing clear_cookies flow)
        for name in bot_cookie_names:
            self.assertEqual(response.cookies[name].value, "")
            self.assertEqual(response.cookies[name]["max-age"], 0)

        # the test client keeps deleted cookies as empty values; real browsers
        # drop them, so the next board load lands clean with no animations.
        self.client.cookies = SimpleCookie()
        response = self.client.get(board_url)
        self.assertNotContains(response, "cardContainer loading")

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
        self.assertEqual(content.count("data-card-id="), bot_deck_count + bot_hand_count)

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

        self.client.post(confirm_url)
        # let the bot play a card to a lane so there is an untrusted lane
        # card (the trusted starting card lives in trustedCards, which
        # _update_played_cards deliberately does not animate)
        self.client.post(end_turn_url, {"action": "end_turn"})

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

    def test_bot_cookies_not_consumed_as_player_actions(self):
        confirm_url = reverse("MMM:confirmChallenge", args=[self.game.id, self.human.id])
        action_url = reverse("MMM:boardAction", args=[self.game.id, self.human.id])

        self.client.post(confirm_url)
        self.client.post(action_url, {"action": "end_turn"})

        bot_lane_cards = GameCard.objects.filter(
            game_id=self.game.id,
            user_id=self.bot_participant.id,
            state__lane__gt=0,
        ).count()

        # the next action POST carries the bot cookies along, but playcards()
        # must only ever execute the acting participant's own cookies.
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
