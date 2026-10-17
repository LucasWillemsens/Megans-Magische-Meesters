import random

NEW_VISITOR_GREETING = (
    "Welcome on your very first visit! I am Megan and I keep the lanes of "
    "Megans Magische Meesters. Press PLAY and I will start a battle for you."
)
GENERIC_GREETINGS = [
    "Welcome back to Megans Magische Meesters!",
    "Hello again, I am Megan. The decks are shuffled and waiting.",
    "Megan here, another day, another magical battle in the lanes.",
]
LOGGED_IN_NAME_GREETINGS = [
    "Welcome back, {name}! Megan kept a lane open for you.",
    "Good to see you again, {name}. The cards are ready.",
    "{name}, Megan mustered the ramparts for you, press PLAY!",
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
