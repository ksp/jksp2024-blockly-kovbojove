# Blockly hra na JKSP2024

Hra, ve které jednotlivé týmy tvoří pomocí Blockly syntaxe programy pro kovboje
(a jejich střely), kteří se poté všichni utkávají na společné mapě tvořené
čtvercovou sítí (na toroidu, tedy lze přecházet přes hrany dokola).

Celá hra běží v krocích, vždy krok kovbojů následovaný několika kroky střel,
poté opět kovbojové a tak stále dokola. Program pro každého kovboje/střelu vždy
dostane aktuální kontext (může zjišťovat pozice ostatních kovbojů, zlata, …)
a jeho úkolem je vydat jednu instrukci pro aktuální tah. Tím jeho výpočet končí.
Mezi jednotlivými koly není dostupná žádná paměť a program tak počítá každý krok
samostatně – v podstatě je to jen reakční agent, vybírá následující krok na
základě stavu okolí.

Pokud má daný tým více kovbojů nebo střel, tak se stejný program používá pro
každého z nich.

## Spuštění (ve venv)

1. Vytvoření venv (stačí jednou):
   ```sh
   python3 -m venv venv
   . venv/bin/activate
   pip3 install -r requirements.txt
   ```

2. Spuštění:
   ```sh
   . venv/bin/activate
   ./run.py
   ```

Poté je web dostupný na URL (loginy a hesla se definují v souboru `run.py`):

* <http://localhost:5000/> - rozhraní pro týmy
* <http://localhost:5000/org/> - ovládání pro orgy

## Soubory

Hra ukládá několik souborů:

* `data/team_X.json` - soubor odkazující na všechny programy týmu `X`
  a určující, který je z nich je aktivní
* `data/cowboy_X_1234.xml` - soubor s XML zápisem programu pro kovboje týmu `X`
  tak, jak přišel z editoru na frontendu
* `data/bullet_X_1234.xml` - totéž, ale pro střelu týmu `X`
* `save/save_000042_0.json` - uložená hra po vykonání kola daného čísla (první
  číslo je číslem tahu kovbojů, druhé číslo je číslo tahu střel v rámci tohoto
  tahu kovbojů, `0` je tah kovbojů a další čísla jsou tahy střel)

## Architektura

Program je napsaný v Pythonu využívají Flask jako frontend pro web. Hlavní části
jsou:

* **Web** (vše ve složce [`blockly/web`](blockly/web/) + templaty
  v [`templates/`](templates/) a statické soubory ve [`static/`](static/))
* **Definice Blockly bloků** v [`blockly/blocks.py`](blockly/blocks.py)
* **Parsovátko** (na XML, které vypadne z frontendu) v [`blockly/parser.py`](blockly/parser.py)
* **Ukládání a správu programů** přes třídu v [`blockly/team.py`](blockly/team.py)
* **Jádro hry a simulace mapy** v [`blockly/map.py`](blockly/map.py)
* **Herní timer** v [`blockly/game.py`](blockly/game.py), který zajišťuje
  spuštění celé hry

Celý program je napsaný tak, že využívá sdílené paměti mezi vlákny. Musí tedy
běžet v rámci jednoho procesu (pozor při spuštění jinak než přes `run.py`).
