import random

NEW_VISITOR_GREETING = "Welcome, new one."
GENERIC_GREETINGS = [
    "Hello.",
    "Whatsup.",
    "Back again?",
    "The champion has returned.",
]
LOGGED_IN_NAME_GREETINGS = [
    "Welcome back, {name}",
    "How are you, {name}? Well I hope. Anyways.",
    "You again, {name}? A real card player.",
    "Back again, the amazing {name}.",
    "This is your lucky day, {name}, no doubt.",
]


def applicable_title_greetings(player_name):
    greetings = list(GENERIC_GREETINGS)
    if player_name:
        greetings.extend(
            greeting.format(name=player_name)
            for greeting in LOGGED_IN_NAME_GREETINGS
        )
    return greetings


def title_greeting(has_visited, player_name, chooser=random.choice):
    if not has_visited:
        return NEW_VISITOR_GREETING
    return chooser(applicable_title_greetings(player_name))
