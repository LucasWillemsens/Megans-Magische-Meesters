"""
copied from basic urls.py in mysite dir
URL configuration for mysite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path

from . import views

app_name = "MMM"
urlpatterns = [
    path("", views.index, name="index"),
    path("", views.index, name="cards"),
    path("", views.index, name="players"),

    path("player/<int:player_id>/", views.viewPlayer, name="viewPlayer"),
    # path("<int:player_id>/history/", views.viewPlayerHistory, name="viewPlayerHistory"),
    # path("<int:player_id>/login/", views.loginPlayer, name="loginPlayer"),

    path("card/<int:card_id>/", views.viewCard, name="viewCard"),
    # path("<int:symbol_id>/", views.viewSymbol, name="viewSymbol"),
    # path("<int:card_id>/history/", views.viewCardHistory, name="viewCardHistory"),
    
    path("game/reset/", views.resetGames, name="resetGames"),

    path("game/<int:game_id>/", views.viewGame, name="viewGame"),
    path("game/initialize/", views.initializeGame, name="initializeGame"), #endpoint for submit button
    path("game/create/<int:player_id>/", views.createGame, name="createGame"),
    path("game/<int:game_id>/<int:player_id>/", views.viewGameAsPlayer, name="viewGameAsPlayer"),
    path("game/<int:game_id>/<int:player_id>/confirm", views.confirmChallenge, name="confirmChallenge"),
    path("game/<int:game_id>/board/<int:player_id>/", views.viewBoard, name="viewBoard"),

]