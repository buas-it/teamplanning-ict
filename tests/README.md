# Tests voor Bezetting Teams

Kerntests (Playwright + een nagebootste GitHub; je hebt geen echte GitHub of token nodig).

    pip install playwright && playwright install chromium
    python3 kern.py index.html        # kerntests: laden, opslaan, controle na opslaan, controlegetal, namen, checks
    python3 tk_klok.py index.html     # klokmeting via de servertijd van GitHub Pages
    python3 tk_acc.py index.html      # tekst van de check 'Accounts'

`index.html` is de pagina van de main-branch. `onderhoud.py` is een kopie van `.github/scripts/onderhoud.py` (main) en wordt door `kern.py`
gebruikt om het controlegetal te berekenen: werk de kopie bij als het script verandert. De tests voor het serveronderhoud zelf (tegen een nagebootste
GitHub-API) zijn niet bewaard en moeten opnieuw worden opgebouwd.
