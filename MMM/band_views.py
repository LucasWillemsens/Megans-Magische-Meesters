"""Views serving the archived Painted Pillars band site at the domain root.

The page content below is copied from the Wayback Machine snapshots of
paintedpillars.com (home, about, music, songs and contact, 2022-2025):
the band biography, the member descriptions from the band's own press
kit, the news feed, the release list and the streaming/social links.
"""
from django.shortcuts import render

BAND_BIO = (
    "What can be said about Painted Pillars? Their music should speak for "
    "itself! Their style is no style. Their story is any story. What sets them "
    "apart from other bands is their adherence to a radical eclecticism: their "
    "focus is on writing the best possible songs without worrying about genre "
    "or style. With a diverse set of inspirations ranging from the most "
    "abrasive punk to the most light hearted pop, the three band members "
    "organically create their own vision of what constitutes a good song. Pop "
    "music as it is meant to be."
)

BAND_MEMBERS = (
    ("Eric Faassen", "singer and guitarist, glorious king of neurotics and full-time philosopher against his own will."),
    ("Rob Müller", "bassist, cover art painter, motorcycle daredevil and mechanical engineer."),
    ("Lucas Willemsens", "drummer, poet and computer whisperer."),
)

SPOTIFY_ARTIST_URL = "https://open.spotify.com/artist/7FQFAibyxDa9kBjFjSgYpH"
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/channel/UCPLO8M2TtIZi3aUkXG3psrg"
YOUTUBE_PLAYLIST_URL = "https://www.youtube.com/watch?v=HDyESqUPBmc&list=PLKC6VD0RhYE4csTWJnUeiLe-R7hJwy6Dj&index=1"
APPLE_MUSIC_URL = "https://music.apple.com/gb/artist/painted-pillars/1603642369"
INSTAGRAM_URL = "https://www.instagram.com/paintedpillars/"

STREAMING_LINKS = (
    ("Spotify", SPOTIFY_ARTIST_URL, "band/spotify.svg"),
    ("YouTube", YOUTUBE_PLAYLIST_URL, "band/youtube.svg"),
    ("Apple Music", APPLE_MUSIC_URL, "band/apple-music.svg"),
)

CONTACT_LINKS = (
    ("Instagram", INSTAGRAM_URL),
    ("Spotify", SPOTIFY_ARTIST_URL),
    ("YouTube", YOUTUBE_CHANNEL_URL),
    ("Apple Music", APPLE_MUSIC_URL),
)

RELEASES = (
    ("Answer", "https://open.spotify.com/track/6zfO2eMK6JqzJlxIMBQVkJ"),
    ("Catastrophe", "https://open.spotify.com/track/39rv48igm6vqk4ChzYCciU"),
    ("Bell", "https://open.spotify.com/track/4tJRLpey0kiOLEXK0hrRw3"),
    ("Pay", "https://open.spotify.com/track/0YkSjhJYL4ZlaJyXeshQjR"),
    ("Collywobbles", "https://open.spotify.com/track/5z63z5Qj00zQxXppxJ6iqL"),
    ("Mary", "https://open.spotify.com/track/0pF6R1wiXmgRTO2ykxwB4Q"),
    ("A Drink", "https://open.spotify.com/track/29lp4uhldWkoGpxr09wHbr"),
    ("For A While", "https://open.spotify.com/track/05g6yy1DVw1zOddN4nB8Qz"),
    ("Lovely", "https://open.spotify.com/track/75quWYaAESL54UhEUODtw6"),
    ("The Stoic", "https://open.spotify.com/track/78cvux8yNmKMgcbPs3ypBS"),
)

NEWS_ITEMS = (
    {
        "categories": ("Announcement", "Live performance"),
        "date": "September 15, 2024",
        "title": "Upcoming concert at Noorderlicht in Amsterdam",
        "excerpt": "Join us for a vibrant mash-up of music and visual art! On the 22nd of September from 16:00 o'clock onwards, we're excited to play at the debut event of Beats…",
        "image": None,
    },
    {
        "categories": ("Announcement",),
        "date": "June 29, 2024",
        "title": "A celebration of childishness: 'Juvenile'",
        "excerpt": "On Juli 5th the band will release their anthem of youth called 'Juvenile'. A fierce yet playful track that calls for infantile behaviour. To set the right example, the band…",
        "image": None,
    },
    {
        "categories": ("Studio Session",),
        "date": "July 27, 2023",
        "title": "New recordings",
        "excerpt": "About two weeks ago we recorded two brand new songs!",
        "image": None,
    },
    {
        "categories": ("Announcement",),
        "date": "January 9, 2023",
        "title": "New single release on januari the 27th!",
        "excerpt": "On Januari the 27th, our new single 'Pay' will be available online everywhere. Curious what kind of song it will be? Check out this thematic Spotify playlist!",
        "image": "band/news/pay.jpg",
    },
    {
        "categories": ("Single release",),
        "date": "August 14, 2022",
        "title": "Our summer single 'Collywobbles' is out now!",
        "excerpt": "Get ready to relax and let the day slide away with our new song! This is our summer release: a song with a relaxing and comforting feeling about chilling out,…",
        "image": "band/news/collywobbles.jpg",
    },
    {
        "categories": ("Single release",),
        "date": "June 19, 2022",
        "title": "'Mary' is out now (including an animated music video!)",
        "excerpt": "Our new single 'Mary' is out now on all streaming platforms. It is an energetic and angsty alternative rock song about a mysterious feeling of sickness and a call for…",
        "image": None,
    },
    {
        "categories": ("Live performance",),
        "date": "May 8, 2022",
        "title": "We rocked the shop window!",
        "excerpt": "At May the 7th we played at the shop window of the Vintage Department Store in Leiden.",
        "image": "band/news/shop-window.jpg",
    },
    {
        "categories": ("Single release",),
        "date": "April 30, 2022",
        "title": "'A Drink' is out now!",
        "excerpt": "Available on Spotify and other streaming services. Best enjoyed in a dark and quiet room.",
        "image": "band/news/a-drink.jpg",
    },
    {
        "categories": ("Studio Session",),
        "date": "April 14, 2022",
        "title": "New studio session",
        "excerpt": "We recently did a new studio session recording studio Peggy 51. We had a great time recording two new songs, 'A Drink' and 'Mary'. The first will already be released…",
        "image": "band/news/studio-session.jpg",
    },
    {
        "categories": ("Single release",),
        "date": "March 31, 2022",
        "title": "'For A While' is out now!",
        "excerpt": "",
        "image": "band/news/for-a-while.jpg",
    },
)


def band_home(request):
    return render(request, "MMM/band/home.jinja2", {"newsItems": NEWS_ITEMS})


def band_music(request):
    return render(
        request,
        "MMM/band/music.jinja2",
        {"streamingLinks": STREAMING_LINKS, "releases": RELEASES},
    )


def band_about(request):
    return render(
        request,
        "MMM/band/about.jinja2",
        {"bandBio": BAND_BIO, "bandMembers": BAND_MEMBERS},
    )


def band_contact(request):
    return render(request, "MMM/band/contact.jinja2", {"contactLinks": CONTACT_LINKS})
