# 🪄 Megans Magische Meesters

![status](https://img.shields.io/badge/status-experimental-orange)
![python](https://img.shields.io/badge/python-3.x-blue)
![license](https://img.shields.io/badge/license-unlicensed-lightgrey)

> A cozy, deadly card game inspired by D&D — magic, strategy, bluffing and dark rituals.

---

## ✨ At a Glance

- **Project:** A digital card-battle tabletop that tests intelligence, speed, danger and determination.
- **Goal:** Build an approachable web prototype (Django) that scales into tournaments, bot opponents and exportable decks.
- **Repo:** https://github.com/LucasWillemsens/Megans-Magische-Meesters

---

## 🎨 Visual Flair
This README is intentionally playful — expect in-game UI to use "dark arts" book styling, dramatic fonts, a rich color palette, and magical iconography.

---

## 💡 Full Idea (raw)
<details>
<summary>Click to expand the original idea text</summary>

```
Dodelijk kaartspel in D&D om magiegevechten te simuleren.

Het spel moet op een simpele manier je slimheid, voorbereiding en kracht testen.

Om je in te schrijven moet je een bloedritueel uitvoeren. Heruit worden statistieken berekent:

🧮 Slimheid: 						Intelligence, wisdom, proficencies, spells, features
		Weten WAT er is, WAAR je naartoe wil gaan en HOE je het BESTE daar kan komen.
👢	Snelheid: 						Initiative, dexterity, speed.
		Hoeveel VERSCHILLENDE acties je in BEWEGING kan zetten in een KORTE TIJD en hoe DIRECT je op nieuwe ontwikkelingen kan REAGEREN
🩸	Gevaarlijkheid: 				Strength, Dexterity, items, spells, features
		Hoeveel SCHADE je IN STAAT bent aan te richten met alle WAPENS die je in je BESCHIKKING hebt.
❤️ Vastberadenheid: 				Charisma, Hp, resistences
		Hoe LANG het duurt voordat je TOEGEEFT aan iets STERKERS dan je KERNWAARDEN.

Bij het inschrijven komen er allerlei magische symbolen voorbij zweven:
20 Domeinen:


🧿 oog     1. Zahadai, the Shadow, Master of Darkness. Nazernold, the Controller. Zosa, the Sleeper, Mistress of Dreams. Zlangen. psychic damage. vervaagde ruimte. necrotic.
⏳ tijd    2. Kronos, the Infinte, Master of Time. psychic damage. force
⛓️ ketting 3. Atuliku, the Chained, Mistress of Promises. psychic damage. force. blunt. slashing
🗡️ zwaard  4. Hesta, the Hiker, Master of Travel. Nazernold, the Controller. Titanos. slashing piercing blunt
🗝️ sleutel 5. Nazernold, the Controller. Ur, the First, Master of Masters. force.
⚓ anker   6. Cabella, the Current, Mistress of Rivers. Makuvaku, the Wave, Mistress of the Seas. Ebbe & Flôte, the Tides, Masters of Ebb and Flood. Nazernold, the Controller. force. cold
🥊 vuist   7. Gregor, the Warrior, Master of Battle. Giants. bludgeoning. radiant.
🎭 emotie  8. Turpentos, the Traveler, Master of Deceit. Maniaka, the Laughing Man, Master of Madness. psychic. necrotic. 
🎯 doel   9. Khán, the Legend, Master of Adventure. Iamora, the Beloved, Mistress of Love. radiant. slashing. piercing.
🎲 geluk  10. Fata, the Weaver, Mistress of Fate. Hrudrós, the Blessed, Master of Prosperity. force damage. psychic.
🎼 muziek 11. Salanor, the Breeze, Master of Wind. Dyosas, the Muse, Mistress of Art. thunder damage. psychic. radiant.
🐾 beest  12. Sheveth, the Shepard, Master of Animals. Mikoraza, the Creator, Mistress of Horrors. bludgeoning. acid. necrotic.
🌱 natuur 13. Hamaan, the Greenman, Master of the Woods. Vitalos, the Curer, Master of Health. Yavaea, the Beloved, Mistress of Life. Nazernold, the Controller. Allfather. radiant. cure.
🍄 rot    14. Anorak, the Snake, Master of Poison. acid. poison damage.
⚡ bliksem 15. Barúm, the Thunderer, Master of the Storm. lightning damage.
⭐ ster    16. Polaris, the Star, Master of the Stars. force damage.
🔥 vuur    17. Vazar, the Smith, Master of Blacksmithing. Nazernold, the Controller. Dragashu. fire damage. radiant damage.
🌙 maan   18. Luna, the Moonshine, Mistress of the Moon. radiant. psychic. 
❄️ ijs    19. Julabula, the Night Man, Master of Punishment. Nazernold, the Controller. cold damage.
💀 dood   20. Karubrimba, the Destroyer, Master of Death. necrotic damage. force. psychic. poison.


Hier missen: de munt, toverstaf en theepot en ☀️ zon 16. en 🩸 bloed 1. 
Van deze twintig symbolen kiest de nieuwe speler symbolen die hem interesseren.

Hierna is het process voltooid en heeft de speler een virtueel karakter.

De statistieken symboliseren meerdere dingen:
Ze worden gebruikt bij berekeningen van technieken en spreuken.   (stats, maar worden minder belangrijk bij hogere getallen)
Ze stellen een maatstaaf voor andere spelers hoe sterk iemand is. (rank, wordt belangrijker hoe verder je komt. Maar nieuwe spelers?)
Ze geven de mogelijkheid aan een speler voor een champion action. (ult, meer om foutjes recht te trekken dan een bepalende rol spelen)

Bij een gevecht tussen twee spelers worden het aantal gebruikte champion actions van de verliezer
geschonken aan de winnaar.


Ik denk er nu aan dat voor de digitale versie in cartiermobilefree tijdens tournament spellen vastberadenheid bij een karakter staat aangegeven als:
❤️❤️❤️❤️❤️
Of nog meer:
💛💛💛❤️❤️ (8)
Of zelfs:
💛💛💛💛💛(12)
Tot en met:
🧡🧡🧡🧡💛 (19)
Zoals de health bar van chan of memories.
De move take risk verhoogt de inzet van vastberadenheid. 
Dat betekent dat je levens omlaag gaan met het aantal door jou vooraf ingezette levens en dat je aanval van je tegenstander tankt en hem aanvalt.

De snelheid wordt gebruikt aan het begin om te bepalen wie het initiatief ▶️ heeft( degene die zichzelf het hoogste inschat), en wiens aanval dus eerst 
gerevealed wordt al clashen aanvallen uit dezelfde ronde wel, maar het initiatief heeft voordeel. Hierna wisselt het initiatief door naar de volgende speler.
De move interruption ⏩ kan op ieder moment worden gedaan en zorgt dat jouw aanval voorafgaat aan de vijand en dus niet meer zal clashen. 
Net zoals bij vastberadenheid verhoogt het de inzet voor wie de snelste is gebaseerd op de vorig ingezette waarde, alleen hier geldt dat 
het telt voor deze ronde en bovendien blijft de snelheid onbekend tenzij een speler door het spel kan raden wat de huidige waarde is.

Gevaarlijkheid geeft de optie om een intimidatie ❗te doen of een uitdaging ‼️met allebei het geluid van een brul als de kaart gespeeld wordt. 
De bijbehorende aanval doet geen schade en kost je niet het initiatief maar is bedoeld om de vijand af te schrikken of om een kaart te stelen. 
Het idee is dat de vijand het hele gevecht kan opgeven of doorgaat en zijn huidige kaart op het spel zet

Slimheid bepaalt de grootte van je deck en dus hoeveel opties je hebt in een gevecht. Een cover move ♟️  zorgt ervoor dat de speler een extra kaart kan spelen. 
Aan het einde kiest de speler welke die wil inzetten en de andere wordt opgeofferd.

Het is mogelijk om je voor te doen als een hoger niveau op een bepaald gebied. Zo kun je een gevecht bijvoorbeeld starten met meerdere kaarten ook al heb je maar 1 slimheid.
Hierbij leen je als het ware de slimheidspunten en trek je ze ook af van de winst. Dat betekent dat als je wint je op hetzelfde aantal blijft als voor de wedstrijd, 
plus de inzet van de tegenstander, en als je verliest, dan verlies je alle geleende punten plus jouw inzet. Dit kan voor alle stats, alleen houd je altijd 1 over na een gevecht.

Hierdoor kunnen beginners leuke high-stakes spellen doen zonder veel te verliezen en komt er een riskante laag bovenop het spel waarbij je meer recources moet afwegen tegen het risico. 
Ook ontstaan daardoor mindgames met slimheid met spelers die genoeg resources hebben en zich lager voordoen dan ze zijn door met een kleinere hand te spelen. 
Zo kunnen ze ook slimheid winnen, of zelfs bij verlies gratis covers spelen zonder dat de ander weet dat de inzet verlaagd was. 

Hierdoor worden hoog niveau spelers geprikkeld om zichzelf uit te dagen tegen beginners, en aangemoedigd om in dat soort gevechten ook cover moves te gebruiken, 
wat natuurlijk juist riskant is.

Steen papier schaar
❤️ > ❗  want een intimidatie doet geen schade, never punished nadeel van risky spot. Vastberaden kan wel kaart verliezen.
❤️ > ⏩ Want de aanval wordt niet interrupted en vijand mocht sws al eerst, dus dubbelop
♟️  > ❤️ De slimme kan kiezen om te traden 
♟️  > ⏩ Want ook al wordt de slimme geraakt, het ontwijkt de onderbreking en kiest de beste aanval
❗  > ♟️  Als geen van beide kaarten winnen verliest de slimme zelfs twee kaarten, maar kan met winst wel damage doen
⏩ > ❗  want de intimidatie doet ook geen schade en de clash wordt gewoon ontweken. Snelle verliest wel een kaart.

Obscured mode:
Naast de stats kan tijdens een spel ook geld ingezet worden om de stats te symboliseren. 
Bij aanvang wordt de slimheid en de minimale snelheid op tafel ingezet, om jezelf als het ware in te kopen.

Bij een cover move moet je dus van een kaart + inzet in de pot leggen.

Bij de andere: risico, intimidatie of een interruptie zet je alleen de inzet in. 

Bij een succesvolle intimidatie gaat de vijandige kaart naar de pot.
in obscured mode speel je dus met geld, en in honest mode speel je vooral om de stats
beginners hebben het dus zwaar, voor hen is ieder statpoint veel waard en die zullen ze daarom minder snel inzetten. 
Dit maakt high level games interesting omdat daar iedere beurt wel een special move wordt gedaan


Bij deze schaduw ets (shadow etch) wordt met een object zoals een doodskist iets in complete schaduw gehuld waarna het op alle denkbare wijzen wordt verdraaid. Alle ambities die heeft en herinneringen en gedachten die men erover heeft als zij de kist aanraken worden er met geweld uitgegutst. Stapsgewijs, als in een in schaduwen gedrukte linosnede wordt het binnenste uitgehold tot er alleen nog diep zwarte contouren over zijn.
ipv twee kaarten trekken bij een start zijn er ook vaste kaarten die tellen als inleg die horizontaal liggen. Die worden nooit weggeshuffled en bij iedere shuffle draai je een nieuwe open kaart horizontaal
gevaarlijkheid actie vereist een niet vaste vastberadenheid, die wordt tijdens de aanval horizontaal gedraaid, waarna je pas shuffled

Vastberadenheid actie is nu juist dat je voor het shufflen nog een kaart moet vastzetten
Hinderlaag is de enige manier om kaarten direct uit je hand te spelen en gaat 2x zo snel als dmv snelheid, maar snelheid is de enige manier om dat te doen voordat je een actie doet
Alleen de eerste en laatste eigenschappen hebben acties met keuzes: slimheid en vastberadenheid. De andere: snelheid en gevaarlijkheid, moet je daarom kundig voor een wenselijke uitkomst. Voor snelheid moet je alle kaarten goed in de gaten hebben en voor gevaarlijkheid vooral genoeg vastberadenheid hebben
Bij ontsnapping steel je een actieve kaart van de ander. Bij bezwijken krijgt de ander alle ingezette kaarten. Als beide partijen een vastberadenheid actie deden maar zonder losse kaart is het gelijkspel. Bij een gelijkspel verliest niemand kaarten.

Dus met slimheid en vastberadenheid heb je een keuze tijdens de actie, en bij snelheid en gevaarlijkheid kan je winnen
```

</details>

---

## 🗺 Roadmap & Open TODOS (cleaned up)

This is a curated, grouped version of your todo list — organised so it's clear what's left and roughly how long things might take.

- **Immediate (1–2 days)**
  - [ ] Battle pages (2 days)
  - [ ] Prototype testing with Annabel

- **Challenges & Matchflow**
  - [ ] Implement challenge flow: send / cancel / accept
  - [ ] Draft deck flow
  - [ ] Debug first-draw from deck (prevent duplicates, multiple confirms, conceal sensitive actions)

- **Deck / Game Pages**
  - [ ] Deck page: default order, images, name & description
  - [ ] Game page: image, name & description
  - [ ] History pages

- **UX / Interaction**
  - [ ] Clickable full cards
  - [ ] Clickable account avatar → account actions
  - [ ] Logo + navigation to homepage
  - [ ] Improve colours ("dark arts" book theme), favicon, page title

- **Data / Tools**
  - [ ] Import / export data (decks, cards)
  - [ ] Easy card creation UI: assign symbols, image, bot-assignment

- **Testing / Deploy**
  - [ ] Step 5: testing and automation (2 hours)
  - [ ] Deploy / make a Pillards version

- **Polish & Feedback**
  - [ ] Collect feedback and iterate

---

## ✅ Suggested First Steps (for contributors)

1. Clone the repo

```bash
git clone git@github.com:LucasWillemsens/Megans-Magische-Meesters.git
cd Megans-Magische-Meesters/djangosite/djangotutorial
python -m venv .venv
source .venv/bin/activate  # or `.\\.venv\\Scripts\\activate` on Windows
pip install -r requirements.txt  # if present
```

2. Run the Django dev server (if using the included project)

```bash
python manage.py migrate
python manage.py runserver
```

---

## 🧭 Project Vision (short)

Make a game that's easy to learn, hard to master, and full of theatrical moments — players bluff, risk, and outplay each other with stat-driven mechanics inspired by D&D.

We've started with a Django prototype; the goal is rapid iteration, playtesting, and then thoughtful automation & deployment.

---

## ✨ Want to help?
- Open an issue describing the feature you want to work on.
- Fork and send a PR for small UI/UX changes (colours, favicon, header). 
- Message me if you'd like to help prototype gameplay with remote playtesting sessions.

---

Made with a bit of dark magic and a lot of coffee ☕

