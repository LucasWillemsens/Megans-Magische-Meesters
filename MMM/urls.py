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

from . import api_views
from . import views

app_name = "MMM"
urlpatterns = [
    path("admin/", views.index, name="index"),
    path("admin/", views.index, name="cards"),
    path("admin/", views.index, name="players"),

    path("", views.home, name="home"),
    path("title/", views.titlePage, name="titlePage"),
    path("play/", views.play, name="play"),
    path("deck/", views.deckPage, name="deckPage"),
    path("deck/team/", views.pickDeckTeam, name="pickDeckTeam"),
    path("deck/name/", views.renameDeckPlayer, name="renameDeckPlayer"),
    path("settings/", views.demoSettings, name="demoSettings"),
    path("settings/zoom/", views.toggleCardZoom, name="toggleCardZoom"),

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
    path("game/<int:game_id>/board/<int:player_id>/action/", views.boardAction, name="boardAction"),
    path("game/<int:game_id>/result/<int:player_id>/", views.viewResult, name="viewResult"),

    path("api/schema/", api_views.openapi_schema, name="apiSchema"),
    path("api/docs/", api_views.swagger_ui, name="apiSwaggerUI"),
    path("api/games/reset/", api_views.api_reset_games, name="apiResetGames"),
    path("api/games/<int:game_id>/board/<int:player_id>/", api_views.api_board_state, name="apiBoardState"),
    path("api/games/<int:game_id>/board/<int:player_id>/play/", api_views.api_play_cards, name="apiPlayCardsAction"),
    path("api/games/<int:game_id>/board/<int:player_id>/draw/", api_views.api_draw_card, name="apiDrawCardAction"),
    path("api/games/<int:game_id>/board/<int:player_id>/end-turn/", api_views.api_end_turn, name="apiEndTurnAction"),
]
