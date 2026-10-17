SCHEMA_VERSION = "1.0.0"
LANE_RANGE = [1, 2, 3, 4]
REQUEST_PHASES = ["player", "playerMoves", "enemy"]
BOARD_PHASES = ["", "player", "playerMoves", "enemy"]

SCHEMA_PATH = "/api/schema/"
DOCS_PATH = "/api/docs/"
RESET_PATH = "/api/games/reset/"
BOARD_PATH = "/api/games/{gameId}/board/{playerId}/"
PLAY_PATH = "/api/games/{gameId}/board/{playerId}/play/"
DRAW_PATH = "/api/games/{gameId}/board/{playerId}/draw/"
END_TURN_PATH = "/api/games/{gameId}/board/{playerId}/end-turn/"

_JSON_CONTENT = "application/json"
_HTML_CONTENT = "text/html"


def _error_response(description):
    return {
        "description": description,
        "content": {_JSON_CONTENT: {"schema": {"$ref": "#/components/schemas/Error"}}},
    }


def _json_response(schema_name, description):
    return {
        "description": description,
        "content": {_JSON_CONTENT: {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}},
    }


def _staged_plays_body(plays_required):
    plays_property = {
        "type": "array",
        "items": {"$ref": "#/components/schemas/PlayRecord"},
        "description": "Staged plays consumed before the action, one per entry in browser cookie order.",
    }
    if plays_required:
        plays_property["minItems"] = 1
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"plays": plays_property},
    }
    if plays_required:
        schema["required"] = ["plays"]
        schema["description"] = "One or more staged plays, consumed together before the endpoint reports state."
    else:
        schema["description"] = "Empty object for a bare action, or object with plays consumed beforehand, exactly like the browser staged cookies."
    return {
        "required": plays_required,
        "content": {_JSON_CONTENT: {"schema": schema}},
    }


def _phase_parameter():
    return {
        "name": "phase",
        "in": "query",
        "required": False,
        "schema": {"type": "string", "enum": REQUEST_PHASES},
        "description": "Absent or empty is a plain board view. phase=enemy resolves the deferred bot turn once, browser-turn_phase-cookie style.",
    }


def openapi_schema():
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Megans Magische Meesters game-action API",
            "version": SCHEMA_VERSION,
            "description": (
                "Demo API for the current board actions, resetgames and the OpenAPI docs themselves. "
                "Browser pages and this API share the same game services, so staged plays, turn "
                "limits and the deferred enemy phase behave identically through either entrance. "
                "Everything is usable anonymously by anyone in the demo; there is no authentication."
            ),
        },
        "servers": [{"url": "/", "description": "the demo server"}],
        "tags": [
            {"name": "board", "description": "Player-scoped board actions and board state."},
            {"name": "demo", "description": "Demo-wide helpers that are not tied to one game."},
            {"name": "docs", "description": "Machine readable schema and its Swagger UI."},
        ],
        "paths": {
            SCHEMA_PATH: {
                "get": {
                    "tags": ["docs"],
                    "summary": "Serve the OpenAPI 3 schema",
                    "responses": {
                        "200": {
                            "description": "This schema document, JSON serialized.",
                            "content": {
                                _JSON_CONTENT: {
                                    "schema": {
                                        "type": "object",
                                        "description": "OpenAPI 3.0.3 document with info, tags, paths and schemas.",
                                    }
                                }
                            },
                        }
                    },
                }
            },
            DOCS_PATH: {
                "get": {
                    "tags": ["docs"],
                    "summary": "Serve the Swagger UI page",
                    "responses": {
                        "200": {
                            "description": "Swagger UI HTML matching this schema; request execution (Try it out) runs against this same demo server.",
                            "content": {_HTML_CONTENT: {"schema": {"type": "string"}}},
                        }
                    },
                }
            },
            RESET_PATH: {
                "post": {
                    "tags": ["demo"],
                    "summary": "Reset every demo game",
                    "description": (
                        "Same destructive service as the browser /game/reset/ route: every Game, "
                        "BattleHistory, BattleParticipant, GameCard, CardState and Deck is deleted."
                    ),
                    "responses": {
                        "200": _json_response("ResetResult", "Demo game state removed; removedGames counts the deleted games.")
                    },
                }
            },
            BOARD_PATH: {
                "get": {
                    "tags": ["board"],
                    "summary": "Board state for one participant",
                    "description": (
                        "Reads the served board: deck counts, hand cards, lanes with their play/flip "
                        "records and current turn allowances. With phase=enemy the deferred enemy "
                        "turn resolves before the read, mirroring the browser board reload."
                    ),
                    "parameters": [_phase_parameter()],
                    "responses": {
                        "200": _json_response("BoardState", "Current board with participant, lanes and allowances."),
                        "400": _error_response("Unsupported phase value."),
                        "404": _error_response("No such game or participant."),
                        "409": _error_response("Game has no GameCards yet; confirm the challenge (browser /game/<id>/<player>/confirm) first."),
                    },
                }
            },
            PLAY_PATH: {
                "post": {
                    "tags": ["board actions"],
                    "summary": "Consume staged plays and flips",
                    "description": (
                        "Plays map one-to-one onto the browser staged-play cookies: a face-down board card "
                        "played with flipFaceUp=true is the flip consumption and does not spend a play slot, "
                        "a lane-0 hand card played into laneValue does. Play/flip limits are enforced like "
                        "the browser; a refused play raises HTTP 400 and rolls the request back."
                    ),
                    "requestBody": _staged_plays_body(True),
                    "responses": {
                        "200": _json_response("BoardActionResult", "All plays consumed; plays lists the executed records."),
                        "400": _error_response("Refused payload, unknown card for this participant, or play/flip limit reached; nothing mutated."),
                        "404": _error_response("No such game or participant."),
                    },
                }
            },
            DRAW_PATH: {
                "post": {
                    "tags": ["board actions"],
                    "summary": "Draw one deck card",
                    "description": (
                        "Draws respect the Intelligence draw limit like the browser, and drawing the last deck "
                        "card triggers the special round plus shuffle-back, returning its animation "
                        "timelineSteps. Optional plays are consumed first, mirroring the browser POST."
                    ),
                    "requestBody": _staged_plays_body(False),
                    "responses": {
                        "200": _json_response("BoardActionResult", "Card drawn: plays records the deck-to-hand move, allowances are refreshed."),
                        "400": _error_response("Draw limit reached, deck empty, refused payload or limit-breaking plays; nothing mutated."),
                        "404": _error_response("No such game or participant."),
                    },
                }
            },
            END_TURN_PATH: {
                "post": {
                    "tags": ["board actions"],
                    "summary": "End the participant's turn",
                    "description": (
                        "Resets the drawn/played/flipped counters and defers the enemy bot turn exactly like "
                        "the browser end turn: nothing bot-controlled mutates here, the resolved turn comes "
                        "from the next board-state GET with phase=enemy."
                    ),
                    "requestBody": _staged_plays_body(False),
                    "responses": {
                        "200": _json_response("BoardActionResult", "Turn ended; enemyPhasePending=true until the enemy phase view runs."),
                        "400": _error_response("Refused payload or limit-breaking plays; nothing mutated."),
                        "404": _error_response("No such game or participant."),
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "PlayRecord": {
                    "type": "object",
                    "required": ["cardId", "laneValue"],
                    "additionalProperties": False,
                    "properties": {
                        "cardId": {
                            "type": "integer",
                            "description": "GameCard id to play or flip; must belong to this participant's board in this game.",
                        },
                        "laneValue": {
                            "type": "integer",
                            "enum": LANE_RANGE,
                            "description": "Target lane 1-4 (Intelligence, Speed, Viciousness, Resolve); for hand cards it defaults to the card's type lane when playing without a lane choice.",
                        },
                        "flipFaceUp": {
                            "type": "boolean",
                            "default": False,
                            "description": "Reveal the card face up. For face-down board cards this is the staged flip; for hand cards it plays and flips in one action.",
                        },
                        "sourceLane": {
                            "type": "integer",
                            "nullable": True,
                            "description": "Staged animation source: 0 for hand, >0 for board lanes, negative for deck positions.",
                        },
                        "sourceOrdinal": {
                            "type": "integer",
                            "nullable": True,
                            "description": "Lane/hand ordinal the staged animation starts from.",
                        },
                    },
                },
                "ExecutedPlay": {
                    "type": "object",
                    "description": "One consumed staged play, a draw deck-to-hand record, or a bot turn record on board state reads.",
                    "properties": {
                        "cardId": {"type": "integer"},
                        "participantId": {"type": "integer"},
                        "laneValue": {"type": "integer", "description": "0 for draw records, otherwise the lane the play or flip landed in."},
                        "sourceLane": {"type": "integer", "nullable": True},
                        "sourceOrdinal": {"type": "integer", "nullable": True},
                        "flipFaceUp": {"type": "boolean"},
                    },
                },
                "AnimationStep": {
                    "type": "object",
                    "description": "Browser animation timeline step (special-trigger, card-effect, participant-effect or shuffle-back), passed through from the service unchanged.",
                    "additionalProperties": True,
                },
                "TurnAllowances": {
                    "type": "object",
                    "description": "Turn limits used by the board's staged-action guards.",
                    "properties": {
                        "draws_left": {"type": "integer"},
                        "flips_left": {"type": "integer"},
                        "plays_left": {"type": "integer"},
                        "int_count": {"type": "integer"},
                        "spd_count": {"type": "integer"},
                        "tactics": {"type": "integer"},
                        "drawn": {"type": "integer"},
                        "played": {"type": "integer"},
                        "flipped": {"type": "integer"},
                        "focused_hand_card": {"type": "integer"},
                        "blocked_titles": {
                            "type": "object",
                            "properties": {
                                "draw": {"type": "string"},
                                "play": {"type": "string"},
                                "flip": {"type": "string"},
                            },
                            "description": "Board tooltips the browser template shows when an allowance runs out.",
                        },
                    },
                },
                "LaneCard": {
                    "type": "object",
                    "properties": {
                        "gameCardId": {"type": "integer"},
                        "title": {"type": "string"},
                        "cardType": {"type": "integer", "enum": [0, 1, 2, 3], "description": "Card type 0-3 maps to lanes 1-4 in order."},
                        "lane": {"type": "integer"},
                        "laneOrdinal": {"type": "integer"},
                        "faceDown": {"type": "boolean"},
                        "trusted": {"type": "boolean"},
                    },
                },
                "HandCard": {
                    "type": "object",
                    "properties": {
                        "gameCardId": {"type": "integer"},
                        "title": {"type": "string"},
                        "cardType": {"type": "integer", "enum": [0, 1, 2, 3]},
                        "laneOrdinal": {"type": "integer"},
                        "defaultLaneValue": {"type": "integer", "enum": LANE_RANGE, "description": "cardType+1: the lane the card lands in when the play is staged without an explicit lane target."},
                    },
                },
                "LaneState": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": ["Intelligence", "Speed", "Visciousness", "Resolve"]},
                        "revealedCount": {"type": "integer", "description": "Face-up cards in the lane, trusted cards included."},
                        "cards": {"type": "array", "items": {"$ref": "#/components/schemas/LaneCard"}, "description": "Untrusted lane cards, ordered by lane ordinal."},
                        "trustedCards": {"type": "array", "items": {"$ref": "#/components/schemas/LaneCard"}},
                    },
                },
                "ParticipantState": {
                    "type": "object",
                    "properties": {
                        "participantId": {"type": "integer"},
                        "playerId": {"type": "integer"},
                        "playerName": {"type": "string"},
                        "computerControlled": {"type": "boolean"},
                        "defeated": {"type": "boolean"},
                        "fled": {"type": "boolean"},
                        "deckCount": {"type": "integer"},
                        "handCount": {"type": "integer"},
                        "handCards": {"type": "array", "items": {"$ref": "#/components/schemas/HandCard"}},
                        "allowances": {"$ref": "#/components/schemas/TurnAllowances"},
                        "lanes": {"type": "array", "items": {"$ref": "#/components/schemas/LaneState"}},
                    },
                },
                "BoardState": {
                    "type": "object",
                    "properties": {
                        "gameId": {"type": "integer"},
                        "gameTitle": {"type": "string"},
                        "playerId": {"type": "integer"},
                        "roundNumber": {"type": "integer"},
                        "finished": {"type": "boolean"},
                        "turnPhase": {"type": "string", "enum": BOARD_PHASES, "description": "Phase acted on in this read; '' is a plain board view with no turn sequence running."},
                        "nextTurnPhase": {"type": "string", "enum": BOARD_PHASES, "description": "'player' follows an enemy-phase resolution like the browser turn_phase cookie; '' when no sequence is open."},
                        "botTurnRan": {"type": "boolean"},
                        "botPlays": {"type": "array", "items": {"$ref": "#/components/schemas/ExecutedPlay"}},
                        "viewer": {"$ref": "#/components/schemas/ParticipantState"},
                        "participants": {"type": "array", "items": {"$ref": "#/components/schemas/ParticipantState"}},
                    },
                },
                "BoardActionResult": {
                    "type": "object",
                    "properties": {
                        "gameId": {"type": "integer"},
                        "playerId": {"type": "integer"},
                        "action": {"type": "string", "enum": ["play", "draw", "end_turn"]},
                        "finished": {"type": "boolean"},
                        "roundNumber": {"type": "integer"},
                        "enemyPhasePending": {"type": "boolean", "description": "True after end_turn: the deferred bot turn resolves on the next board-state read with phase=enemy."},
                        "plays": {"type": "array", "items": {"$ref": "#/components/schemas/ExecutedPlay"}},
                        "timelineSteps": {"type": "array", "items": {"$ref": "#/components/schemas/AnimationStep"}},
                        "turnAllowances": {"$ref": "#/components/schemas/TurnAllowances"},
                    },
                },
                "ResetResult": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["reset"]},
                        "removedGames": {"type": "integer", "description": "Games that existed before the reset."},
                    },
                },
                "Error": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {
                        "error": {"type": "string", "description": "Rejection text; HTTP 400 replies always roll back the request before mutating state."}
                    },
                },
            },
        },
    }
