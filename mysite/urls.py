"""Root URL configuration for mysite.

The Painted Pillars band site owns the domain root (/, /music/, /songs/,
/about/ and /contact/) and the game application owns every route below
/MMM/.
"""
from django.urls import include, path

from MMM import band_views

urlpatterns = [
    path("", band_views.band_home, name="band_home"),
    path("music/", band_views.band_music, name="band_music"),
    path("songs/", band_views.band_music, name="band_songs"),
    path("about/", band_views.band_about, name="band_about"),
    path("contact/", band_views.band_contact, name="band_contact"),
    path("MMM/", include("MMM.urls")),
]
