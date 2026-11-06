import json, sys, time, email.utils
from playwright.sync_api import sync_playwright
HTML = open(sys.argv[1], encoding="utf-8").read(); UIT = []
def check(naam, ok, detail=""):
    UIT.append(("PASS  " if ok else "FAIL  ") + naam + ("" if ok else "   -> " + str(detail)[:600])); print(UIT[-1], flush=True)
S = {"offset_s": 0, "age": None, "date": True, "rate": False}
def datum(secs): return email.utils.formatdate(int(secs), usegmt=True)
def handler(route, request):
    u = request.url
    if u.startswith("https://buas-it.github.io/teamplanning-ict/index.html?klok="):
        h = {"Content-Type": "text/html", "Cache-Control": "no-store"}
        if S["date"]: h["Date"] = datum(time.time() + S["offset_s"] - (S["age"] or 0))
        if S["age"] is not None: h["Age"] = str(S["age"])
        return route.fulfill(status=200, headers=h, body="")
    if u.rstrip("/") == "https://buas-it.github.io/teamplanning-ict": return route.fulfill(status=200, content_type="text/html", body=HTML)
    if u.startswith("https://api.github.com/rate_limit") and S["rate"]:
        reset = int(time.time() + 1800); return route.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"}, body=json.dumps({"resources": {"core": {"reset": reset}}}))
    return route.fulfill(status=404, content_type="application/json", headers={"access-control-allow-origin": "*"}, body="{}")
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = b.new_context(viewport={"width": 900, "height": 900}, timezone_id="UTC"); ctx.route("**/*", handler); p = ctx.new_page(); fouten = []; p.on("pageerror", lambda e: fouten.append(str(e)[:120]))
    p.goto("https://buas-it.github.io/teamplanning-ict/"); p.wait_for_timeout(2500)
    def meet(**kw):
        S.update({"offset_s": 0, "age": None, "date": True, "rate": False}); S.update(kw); p.evaluate("CK_KLOK = null"); return p.evaluate("ckKlok()")
    r = meet(); check("KL1 klopt de klok van het apparaat met GitHub, dan staat er 'klopt met GitHub' met het gemeten verschil en de nauwkeurigheid, en de check is in orde (ok)", r["ok"] and not r["onbekend"] and not r.get("grof") and "klopt met GitHub" in r["tekst"] and abs(r["ms"]) < 3000 and "nauwkeurig" in r["tekst"] and "Op hetzelfde moment: GitHub" in r["tekst"] and bool(__import__("re").search(r"GitHub \d\d:\d\d:\d\d, dit apparaat \d\d:\d\d:\d\d", r["tekst"])), json.dumps(r))
    r = meet(offset_s=18 * 60 + 12); check("KL2 loopt het apparaat 18 minuten en 12 seconden achter, dan meet de pagina dat op een paar seconden na (en niet op een halfuur na); de tekst zegt 'loopt 18 min ... achter' en laat de tijd van GitHub en van het apparaat zien, die ongeveer 18 minuten uit elkaar liggen", not r["ok"] and abs(r["ms"] + 1092000) < 3500 and "18 min" in r["tekst"] and "achter" in r["tekst"] and r["githubTijd"] != r["apparaatTijd"], json.dumps(r))
    r = meet(offset_s=-8 * 60 - 20); check("KL3 loopt het apparaat 8 minuten en 20 seconden voor, dan staat er 'voor' met dat verschil en is het een aandachtspunt", not r["ok"] and abs(r["ms"] - 500000) < 3500 and "voor" in r["tekst"] and "8 min" in r["tekst"] and not r["ernstig"], json.dumps(r))
    r = meet(offset_s=45); check("KL4 een verschil van 45 seconden is in orde en wordt wel precies genoemd", r["ok"] and abs(r["ms"] + 45000) < 3500 and "45 s" in r["tekst"] or (r["ok"] and "klopt" in r["tekst"] and abs(r["ms"] + 45000) < 3500), json.dumps(r))
    r = meet(offset_s=6 * 60); check("KL5 een verschil van 6 minuten is niet meer in orde (grens: 5 minuten)", not r["ok"] and abs(r["ms"] + 360000) < 3500, json.dumps(r))
    r = meet(age=120); check("KL6 komt het antwoord uit de cache van GitHub (Age: 120 seconden), dan telt die leeftijd mee, en de klok die klopt blijft 'klopt'", r["ok"] and abs(r["ms"]) < 3500, json.dumps(r))
    r = meet(date=False, rate=True); check("KL7 is er geen servertijd in het antwoord (bijvoorbeeld een lokaal bestand), dan valt de pagina terug op een grove schatting via de API en zegt dat ook ('grove schatting')", r["ok"] and r.get("grof") and "grove schatting" in r["tekst"], json.dumps(r))
    r = meet(date=False, rate=False); check("KL8 is er helemaal geen tijd van GitHub te krijgen, dan zegt de pagina dat het niet vast te stellen is (geen alarm, geen onjuiste claim)", r["onbekend"] and not r["ok"], json.dumps(r))
    tekst = lambda **kw: (meet(**kw), p.evaluate("(async () => { const c = CHECKS.find(c => c.id === 'klok'); return await c.run(); })()"))[1]
    c = tekst(); check("KL9 de check 'Klok van dit apparaat' staat bij een kloppende klok in orde", c["s"] == "ok" and "klopt met GitHub" in c["t"] and "dit apparaat" in c["t"], json.dumps(c))
    c = tekst(offset_s=18 * 60 + 12); check("KL10 loopt de klok een kwartier of meer achter, dan is de check 'let op' met uitleg wat te doen (datum en tijd op automatisch) en de tekst over oude roosters is weg", c["s"] == "let" and "automatisch" in c["t"] and "achter" in c["t"] and "roosters" not in c["t"] and ".:" not in c["t"] and c["t"].count(". Zet de datum") == 1, json.dumps(c))
    f = p.evaluate("[ckVerschilTekst(0), ckVerschilTekst(45000), ckVerschilTekst(1092000), ckVerschilTekst(-3661000), ckVerschilTekst(90061000)]"); check("KL11 de opmaak van het verschil is leesbaar: 0 s, 45 s, 18 min 12 s, 1 u 1 min, 1 d 1 u 1 min", f == ["0 s", "45 s", "18 min 12 s", "1 u 1 min", "1 d 1 u 1 min"], json.dumps(f))
    r = meet(offset_s=3 * 60 + 20); check("KL14 een verschil van 3 min 20 s (het geval van de gebruiker) is in orde: de klok van een apparaat is niet meer leidend, alleen 'vandaag', verjaardagsmeldingen en halve dagen hangen er nog aan; het verschil wordt wel precies genoemd", r["ok"] and not r["onbekend"] and "3 min 20 s" in r["tekst"] and "klopt met GitHub" in r["tekst"], json.dumps(r))
    r = meet(offset_s=26 * 3600); c26 = p.evaluate("(async () => await CHECKS.find(c => c.id === 'klok').run())()"); check("KL15 een verschil van meer dan een dag is een fout (dan klopt 'vandaag' niet meer), tussen 5 minuten en een dag een aandachtspunt", not r["ok"] and r["ernstig"] and c26["s"] == "fout", json.dumps([r, c26])[:300])
    S.update({"offset_s": 0, "age": None, "date": True, "rate": False}); p.evaluate("CK_KLOK = null"); p.evaluate("runChecks({ zwaar: true, repair: false })"); p.wait_for_timeout(1500); k = p.evaluate("CHECK_RESULT.klok"); n = p.evaluate("Object.keys(CHECK_RESULT).length")
    check("KL12 een hele check-ronde (alle checks, ook de zware) draait nog zonder fout met de nieuwe klokmeting, en de klokcheck staat in de resultaten", k and k["s"] == "ok" and n == p.evaluate("CHECKS.length"), json.dumps([k, n]))
    check("KL13 geen fouten in de pagina", not fouten, str(fouten[:2])); b.close()
print(f"\nklaar: {sum(1 for r in UIT if r.startswith('PASS'))} geslaagd, {sum(1 for r in UIT if r.startswith('FAIL'))} gefaald")
