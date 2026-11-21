"""Root URL configuration for mysite.

The Painted Pillars band site owns the domain root (/, /music/, /songs/,
/about/, /contact/ and every archived news post's historical path),
allauth owns the account routes below /accounts/, and the game
application owns every route below /MMM/.
"""
from django.urls import include, path

from MMM import band_views

urlpatterns = [
    path("", band_views.band_home, name="band_home"),
    path("music/", band_views.band_music, name="band_music"),
    path("songs/", band_views.band_music, name="band_songs"),
    path("about/", band_views.band_about, name="band_about"),
    path("contact/", band_views.band_contact, name="band_contact"),
    *band_views.band_post_urlpatterns(),
    path("accounts/", include("allauth.urls")),
    path("MMM/", include("MMM.urls")),
]
