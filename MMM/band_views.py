"""Views serving the archived Painted Pillars band site at the domain root.

The page content below is copied from the Wayback Machine snapshots of
paintedpillars.com (home, about, music, songs, contact and every news
post, 2021-2025): the band biography, the member descriptions from the
band's own press kit, the news feed with one page per post at its
archived URL, the release list and the streaming/social links. Post
content holds only the text the snapshots preserved; imagery and embeds
the Wayback Machine never captured is left out.

The contact page is live functionality rather than archived content: it
offers signed-in accounts a mail form whose messages reach the band at
the configured contact address with a copy to the sender's own email.
"""
from django.conf import settings
from django.core.mail import EmailMessage
from django.shortcuts import redirect, render
from django.urls import path, reverse

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

# Every archived news post, newest first. "url" is the post's historical
# path on paintedpillars.com and "urlName" the route name it keeps under
# the rebuilt site. "content" holds the paragraphs the Wayback Machine
# captured, each paragraph as a tuple of (kind, text, linkUrl) runs with
# kind "text", "strong" or "link"; paragraphs whose snapshots preserved
# no text at all stay empty.
NEWS_ITEMS = (
    {
        "categories": ("Announcement", "Live performance"),
        "date": "September 15, 2024",
        "title": "Upcoming concert at Noorderlicht in Amsterdam",
        "excerpt": "Join us for a vibrant mash-up of music and visual art! On the 22nd of September from 16:00 o’clock onwards, we’re excited to play at the debut event of Beats…",
        "image": None,
        "url": "live-performance/upcoming-concert-at-noorderlicht-in-amsterdam/",
        "urlName": "band_post_noorderlicht",
        "content": (
            (("text", "Join us for a vibrant mash-up of music and visual art!", None),),
            (
                ("text", "On the ", None),
                ("strong", "22nd of September", None),
                ("text", " from ", None),
                ("strong", "16:00", None),
                ("text", " o’clock onwards, we’re excited to play at ", None),
                ("link", "the debut event of Beats & Bites Production", "https://noorderlichtcafe.nl/beats-bites/"),
                ("text", "! The tickets are free so if you are available, be sure to come take a look!", None),
            ),
            (("text", "Our last concert was in Leiden, where we played during the opening week of the student year at the Student association “Catena”.", None),),
            (
                ("text", "We also started ", None),
                ("link", "a Patreon account", "https://www.patreon.com/user?u=142072920"),
                ("text", " for those that want to financially support us! Be sure to check it out if you want to ", None),
                ("link", "download our music and videoclips!", "https://www.patreon.com/PaintedPillars/shop/painted-pillars-416752?source=storefront"),
                ("text", " You do need a Paypal account to make it work over there, so we also offer you to ", None),
                ("link", "pay us with a tikkie", "https://diensten.asnbank.nl/online/betaalverzoek/#/v2/c9fbbf29-9714-4541-9a2a-b3c2391eb17f/gi3beXBZQFLtyHh3eZASCNWke1UmDElb"),
                ("text", " and we’ll send you a download link ourselves if you include your email.", None),
            ),
        ),
    },
    {
        "categories": ("Announcement",),
        "date": "June 29, 2024",
        "title": "A celebration of childishness: ‘Juvenile’",
        "excerpt": "On Juli 5th the band will release their anthem of youth called ‘Juvenile’. A fierce yet playful track that calls for infantile behaviour. To set the right example, the band…",
        "image": None,
        "url": "announcement/a-celebration-of-childishness-juvenile/",
        "urlName": "band_post_juvenile",
        "content": (
            (("text", "On Juli 5th the band will release their anthem of youth called ‘Juvenile’. A fierce yet playful track that calls for infantile behaviour. To set the right example, the band has recorded a music video in collaboration with director Robert Zwaan. Stay tuned for the result!", None),),
            (("text", "(Also, did we mention the track will feature a glockenspiel?)", None),),
            (("text", "“Nevermind the poison they call wisdom. It’s not profound. The whole world is a playground… so let’s play some!”", None),),
        ),
    },
    {
        "categories": ("Studio Session",),
        "date": "July 27, 2023",
        "title": "New recordings",
        "excerpt": "About two weeks ago we recorded two brand new songs!",
        "image": None,
        "url": "studio-session/new-recordings/",
        "urlName": "band_post_new_recordings",
        "content": (
            (("text", "About two weeks ago we recorded two brand new songs!", None),),
        ),
    },
    {
        "categories": ("Announcement",),
        "date": "January 9, 2023",
        "title": "New single release on januari the 27th!",
        "excerpt": "On Januari the 27th, our new single ‘Pay’ will be available online everywhere. Curious what kind of song it will be? Check out this thematic Spotify playlist!",
        "image": "band/news/pay.jpg",
        "url": "announcement/new-single-release-on-januari-the-27th/",
        "urlName": "band_post_januari_the_27th",
        "content": (
            (
                ("text", "On Januari the 27th, our new single ‘Pay’ will be available online everywhere. Curious what kind of song it will be? Check out this thematic ", None),
                ("link", "Spotify playlist", "https://open.spotify.com/playlist/4w7Wlfpb9mmfsSikOs5oN1"),
                ("text", "! Still curious? Check out our ", None),
                ("link", "Instagram", "https://www.instagram.com/p/Cb8E0CXDxV1/"),
                ("text", " for a fragment of us performing the song live at Stukafest Delft last year. Be sure to follow us to stay up to date about the upcoming release!", None),
            ),
        ),
    },
    {
        "categories": ("Single release",),
        "date": "August 14, 2022",
        "title": "Our summer single ‘Collywobbles’ is out now!",
        "excerpt": "Get ready to relax and let the day slide away with our new song! This is our summer release: a song with a relaxing and comforting feeling about chilling out,…",
        "image": "band/news/collywobbles.jpg",
        "url": "single-release/our-summer-single-collywobbles-is-out-now/",
        "urlName": "band_post_collywobbles",
        "content": (
            (("text", "Get ready to relax and let the day slide away with our new song!", None),),
            (("text", "This is our summer release: a song with a relaxing and comforting feeling about chilling out, vague uneasiness and spending the day in bed. ‘Collywobbles’ is an obscure word for ‘bellyache’ which I found whilst reading ‘A Portrait of the Artist as Young Man’ by James Joyce. In this scene the protagonist of the story is lying in the infirmary of his boarding school with another boy, who upon asking tells him that he has a case of ‘the collywobbles’, which is of course a pretext to skip class.", None),),
        ),
    },
    {
        "categories": ("Single release",),
        "date": "June 19, 2022",
        "title": "‘Mary’ is out now (including an animated music video!)",
        "excerpt": "Our new single ‘Mary’ is out now on all streaming platforms. It is an energetic and angsty alternative rock song about a mysterious feeling of sickness and a call for…",
        "image": None,
        "url": "single-release/mary-is-out-now-including-an-animated-music-video/",
        "urlName": "band_post_mary",
        "content": (
            (("text", "Our new single ‘Mary’ is out now on all streaming platforms. It is an energetic and angsty alternative rock song about a mysterious feeling of sickness and a call for help to a divine mother figure. Get ready for angelic choirs and a raunchy guitar solo!", None),),
            (("text", "Be sure to also check out the animated music video for it, made by Floris Springintveld.", None),),
        ),
    },
    {
        "categories": ("Live performance",),
        "date": "May 8, 2022",
        "title": "We rocked the shop window!",
        "excerpt": "At May the 7th we played at the shop window of the Vintage Department Store in Leiden.",
        "image": "band/news/shop-window.jpg",
        "url": "live-performance/we-rocked-the-shop-window/",
        "urlName": "band_post_shop_window",
        "content": (
            (("text", "At May the 7th we played at the shop window of the Vintage Department Store in Leiden.", None),),
        ),
    },
    {
        "categories": ("Single release",),
        "date": "April 30, 2022",
        "title": "‘A Drink’ is out now!",
        "excerpt": "Available on Spotify and other streaming services. Best enjoyed in a dark and quiet room.",
        "image": "band/news/a-drink.jpg",
        "url": "single-release/a-drink-is-out-now/",
        "urlName": "band_post_a_drink",
        "content": (
            (("text", "Available on Spotify and other streaming services. Best enjoyed in a dark and quiet room.", None),),
        ),
    },
    {
        "categories": ("Studio Session",),
        "date": "April 14, 2022",
        "title": "New studio session",
        "excerpt": "We recently did a new studio session recording studio Peggy 51. We had a great time recording two new songs, ‘A Drink’ and ‘Mary’. The first will already be released…",
        "image": "band/news/studio-session.jpg",
        "url": "studio-session/new-studio-session/",
        "urlName": "band_post_new_studio_session",
        "content": (
            (("text", "We recently did a new studio session recording studio Peggy 51. We had a great time recording two new songs, ‘A Drink’ and ‘Mary’. The first will already be released by the end of the month, so stay tuned for the results!", None),),
        ),
    },
    {
        "categories": ("Single release",),
        "date": "March 31, 2022",
        "title": "‘For A While’ is out now!",
        "excerpt": "",
        "image": "band/news/for-a-while.jpg",
        "url": "single-release/for-a-while-is-out-now/",
        "urlName": "band_post_for_a_while",
        "content": (),
    },
    {
        "categories": ("Music video",),
        "date": "March 28, 2022",
        "title": "Our first music video!",
        "excerpt": "We are proud to present our first music video for ‘Lovely’, made in association with student of Grafisch Lyceum Utrecht. Many thanks to director Robert Zwaan for his passion and…",
        "image": "band/news/first-music-video.jpg",
        "url": "music-video/our-first-music-video/",
        "urlName": "band_post_first_music_video",
        "content": (
            (("text", "We are proud to present our first music video for ‘Lovely’, made in association with student of Grafisch Lyceum Utrecht. Many thanks to director Robert Zwaan for his passion and energy!", None),),
        ),
    },
    {
        "categories": ("Press release",),
        "date": "March 7, 2022",
        "title": "Interview LeidsCement",
        "excerpt": "An interview by Elly Jousma about our first live experience and more.",
        "image": "band/news/leidscement.png",
        "url": "press-release/interview-leidscement/",
        "urlName": "band_post_leidscement",
        "content": (
            (("text", "An interview by Elly Jousma about our first live experience and more.", None),),
            (("link", "Painted Pillars: van studentenkamer naar de studio.", "https://leidscement.nl/podiumkunsten/painted-pillars-van-studentenkamer-naar-de-studio/"),),
        ),
    },
    {
        "categories": ("Single release",),
        "date": "February 25, 2022",
        "title": "Our second single is out now!",
        "excerpt": "Check out ‘Lovely’ on Spotify and other streaming services.",
        "image": "band/news/second-single.jpg",
        "url": "single-release/our-second-single-is-out-now/",
        "urlName": "band_post_second_single",
        "content": (
            (("text", "Check out ‘Lovely’ on Spotify and other streaming services.", None),),
        ),
    },
    {
        "categories": ("Live performance",),
        "date": "February 20, 2022",
        "title": "Stukafest Leiden",
        "excerpt": "Our debut live performance at Stukafest Leiden was a blast! Many thanks to everyone involved. Photo by Brian Mul/ Video’s by Stephanie Esajas",
        "image": None,
        "url": "live-performance/stukafest-leiden/",
        "urlName": "band_post_stukafest",
        "content": (
            (("text", "Our debut live performance at Stukafest Leiden was a blast! Many thanks to everyone involved.", None),),
            (("text", "Photo by Brian Mul/ Video’s by Stephanie Esajas", None),),
        ),
    },
    {
        "categories": ("Press release",),
        "date": "February 20, 2022",
        "title": "Interview Mare",
        "excerpt": "Our first interview! https://www.mareonline.nl/cultuur/de-leden-van-studentenband-painted-pillars-tasten-af-hoe-groot-ze-mogen-dromen/",
        "image": "band/news/mare.png",
        "url": "press-release/interview-mare/",
        "urlName": "band_post_mare",
        "content": (
            (("text", "Our first interview!", None),),
            (("link", "https://www.mareonline.nl/cultuur/de-leden-van-studentenband-painted-pillars-tasten-af-hoe-groot-ze-mogen-dromen/", "https://www.mareonline.nl/cultuur/de-leden-van-studentenband-painted-pillars-tasten-af-hoe-groot-ze-mogen-dromen/"),),
        ),
    },
    {
        "categories": ("Single release",),
        "date": "January 28, 2022",
        "title": "Our first single is out now!",
        "excerpt": "Check out our debut single on Spotify and other streaming services",
        "image": None,
        "url": "single-release/debut-single/",
        "urlName": "band_post_debut_single",
        "content": (
            (("text", "Check out our debut single on Spotify and other streaming services", None),),
        ),
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
    context = {
        "contactLinks": CONTACT_LINKS,
        "contactFormError": "",
        "contactFormSent": False,
        "contactSubject": "",
        "contactMessage": "",
    }
    if request.method == "POST" and request.user.is_authenticated:
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()
        if not subject or not message:
            context["contactFormError"] = (
                "Please give your message both a subject and a body."
            )
            context["contactSubject"] = subject
            context["contactMessage"] = message
        else:
            EmailMessage(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.CONTACT_EMAIL],
                cc=[request.user.email],
            ).send()
            return redirect(f"{reverse('band_contact')}?sent=1")
    if request.GET.get("sent") == "1":
        context["contactFormSent"] = True
    return render(request, "MMM/band/contact.jinja2", context)


def band_post(request, post):
    return render(request, "MMM/band/post.jinja2", {"post": post})


def band_post_urlpatterns():
    """One root URL per archived post, keeping every historical post link
    of paintedpillars.com working under the rebuilt site."""
    return [
        path(post["url"], band_post, kwargs={"post": post}, name=post["urlName"])
        for post in NEWS_ITEMS
    ]
