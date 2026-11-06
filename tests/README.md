# Tests voor Bezetting Teams

Kerntests (Playwright + een nagebootste GitHub; je hebt geen echte GitHub of token nodig).

    pip install playwright && playwright install chromium
    python3 kern.py index.html        # kerntests: laden, opslaan, controle na opslaan, controlegetal, namen, het Checks-venster
    python3 tk_klok.py index.html     # klokmeting via de servertijd van GitHub Pages

    python3 tk_srv.py                 # serveronderhoud (onderhoud.py) tegen een nagebootste GitHub-API: 106 tests, inclusief alle controles die de server doet, de bewaartermijnen, het maken van backups en het schrijven van het logboek van wijzigingen

`index.html` is de pagina van de main-branch. `onderhoud.py` is een kopie van `.github/scripts/onderhoud.py` (main) en wordt door `kern.py`
gebruikt om het controlegetal te berekenen: werk de kopie bij als het script verandert. De tests voor het serveronderhoud zelf (`tk_srv.py`) draaien tegen een nagebootste GitHub-API (geen netwerk nodig) en zijn gecontroleerd met opzettelijke fouten in het script (grens van 40%, controle op het controlegetal, lijst met verwijderde namen, backup vooraf): elk daarvan wordt door de tests gevangen.
