"""Kerntests van Bezetting Teams: laden, opslaan, controle na opslaan, controlegetal, schoonmaken van verwijderde namen, de checks.
Gebruik: python3 kern.py <pad naar index.html>   (Playwright + een nagebootste GitHub; geen echte GitHub nodig)"""
import base64, datetime as dt, hashlib, importlib.util, json, os, re, sys, time
from playwright.sync_api import sync_playwright
os.environ.setdefault("GITHUB_TOKEN", "x"); os.environ.setdefault("GITHUB_REPOSITORY", "buas-it/teamplanning-ict")
sp = importlib.util.spec_from_file_location("ond", os.path.join(os.path.dirname(os.path.abspath(__file__)), "onderhoud.py")); OND = importlib.util.module_from_spec(sp); sp.loader.exec_module(OND)
HTML = open(sys.argv[1], encoding="utf-8").read(); UIT = []
def check(naam, ok, detail=""):
    UIT.append(("PASS  " if ok else "FAIL  ") + naam + ("" if ok else "   -> " + str(detail)[:600])); print(UIT[-1], flush=True)
PAGE = "https://buas-it.github.io/teamplanning-ict/"; API = re.compile(r"^https://api\.github\.com/repos/buas-it/teamplanning-ict/contents/([^?]*)(\?.*)?$")
TEAM = ["Wim", "Wouter", "Annies", "Bas", "Bram", "Marco", "Hans", "Sercan", "Ted", "Sam"]; DG = ["MA", "DI", "WO", "DO", "VR"]
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET,PUT,POST,DELETE,PATCH,HEAD,OPTIONS"}
class Repo:
    def __init__(self): self.f = {}; self.puts = []; self.hook = None; self.tamper = None; self.na_put = False
    def sha(self, p): return hashlib.sha1(self.f[p].encode()).hexdigest()
def handler_voor(R):
    def h(route, request):
        u, m = request.url, request.method
        if m == "OPTIONS": return route.fulfill(status=204, headers=CORS, body="")
        if u.rstrip("/") == PAGE.rstrip("/"): return route.fulfill(status=200, content_type="text/html", body=HTML)
        if u.startswith(PAGE + "index.html?klok="): return route.fulfill(status=200, headers={"Date": __import__("email.utils").utils.formatdate(time.time(), usegmt=True)}, body="")
        mm = API.match(u)
        if mm:
            pad = mm.group(1)
            if m == "GET":
                if pad in R.f:
                    t = R.f[pad]
                    if pad == "state.json" and R.tamper == "weeg" and R.na_put: s = json.loads(t); [s["store"].pop(k) for k in sorted(s["store"])[-1:]]; t = json.dumps(s)
                    return route.fulfill(status=200, headers=CORS, content_type="application/json", body=json.dumps({"sha": R.sha(pad), "encoding": "base64", "content": base64.b64encode(t.encode()).decode(), "name": pad.split("/")[-1], "path": pad}))
                kids = sorted({k[len(pad) + 1:].split("/")[0] for k in R.f if k.startswith(pad + "/")})
                if kids: return route.fulfill(status=200, headers=CORS, content_type="application/json", body=json.dumps([{"name": n, "path": pad + "/" + n, "sha": R.sha(pad + "/" + n), "type": "file"} for n in kids]))
                return route.fulfill(status=404, headers=CORS, content_type="application/json", body="{}")
            body = request.post_data_json or {}
            if m == "PUT":
                if R.hook and pad == "state.json": hk, R.hook = R.hook, None; hk()
                bestaat = pad in R.f
                if bestaat and not body.get("sha"): return route.fulfill(status=422, headers=CORS, content_type="application/json", body=json.dumps({"message": "sha wasn't supplied"}))
                if bestaat and body["sha"] != R.sha(pad): return route.fulfill(status=409, headers=CORS, content_type="application/json", body=json.dumps({"message": "does not match"}))
                R.f[pad] = base64.b64decode(body["content"]).decode(); R.puts.append(pad)
                if pad == "state.json": R.na_put = True
                return route.fulfill(status=200 if bestaat else 201, headers=CORS, content_type="application/json", body=json.dumps({"content": {"sha": R.sha(pad)}, "commit": {"sha": "abc"}}))
            if m == "DELETE":
                if pad not in R.f: return route.fulfill(status=404, headers=CORS, content_type="application/json", body="{}")
                if body.get("sha") != R.sha(pad): return route.fulfill(status=409, headers=CORS, content_type="application/json", body=json.dumps({"message": "does not match"}))
                del R.f[pad]; return route.fulfill(status=200, headers=CORS, content_type="application/json", body="{}")
        return route.fulfill(status=404, headers=CORS, content_type="application/json", body="{}")
    return h
def planning(weken=("2026-W43", "2026-W44"), n=4, extra=None, stempel=True):
    s = {"team": list(TEAM), "store": {w: {p: {d: ["kantoor"] for d in DG} for p in TEAM} for w in weken}, "template": {p: {d: ["kantoor"] for d in DG} for p in TEAM}, "manuallyEdited": {}, "hidden": []}
    if extra: extra(s)
    if stempel: OND.stempel(s, {"integriteit": {"n": n - 1, "bev": 0}}); s["integriteit"]["t"] = "2026-10-19T08:00:00.000Z"; s["integriteit"]["door"] = "Hans"
    return s
def nieuw(s):
    R = Repo(); R.f["state.json"] = json.dumps(s); R.f["users.json"] = json.dumps({"v": 1, "users": {}}); R.f["groups.json"] = json.dumps({"v": 1, "administrators": ["Hans", "Monitor"]}); return R
def open_pagina(pw, R):
    b = pw.chromium.launch(); ctx = b.new_context(viewport={"width": 1200, "height": 1300}, timezone_id="UTC"); ctx.route("**/*", handler_voor(R)); p = ctx.new_page(); fouten = []; p.on("pageerror", lambda e: fouten.append(str(e)[:140]))
    p.clock.install(time=dt.datetime(2026, 10, 19, 9, 30, tzinfo=dt.timezone.utc)); p.goto(PAGE); p.wait_for_timeout(4500); return b, p, fouten
def staat(R): return json.loads(R.f["state.json"])
BANNER = "(id) => !!document.getElementById(id)"
EDIT = "async (a) => { const [wk, p, d, v] = a; store[wk][p][d] = v; (manuallyEdited[wk] || (manuallyEdited[wk] = new Set())).add(p + '-' + d); await saveToGitHub({}); }"
with sync_playwright() as pw:
    # K1 laden
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R); s = p.evaluate("({ vertrouwd: stateTrusted, team: TEAM.slice(), weken: Object.keys(store).length, integriteit: HEALTH.integriteit && HEALTH.integriteit.status })")
    check("K1 de pagina laadt de planning van GitHub: vertrouwd, 10 teamleden en een kloppend controlegetal, zonder fouten en zonder meldingen", s["vertrouwd"] and sorted(s["team"]) == sorted(TEAM) and s["integriteit"] == "ok" and not fouten and not p.evaluate(BANNER, "integriteit-banner") and not p.evaluate(BANNER, "corrupt-banner"), json.dumps([s, fouten[:1]]))
    # K2 opslaan
    n0 = staat(R)["integriteit"]["n"]; p.evaluate(EDIT, ["2026-W43", "Wim", "MA", ["vrij"]]); p.wait_for_timeout(2500); t = staat(R)
    check("K2 een wijziging wordt opgeslagen: de cel staat op GitHub, het controlegetal is met 1 opgehoogd en klopt, de handmatige markering staat erbij, en de controle na het opslaan slaat geen alarm", t["store"]["2026-W43"]["Wim"]["MA"] == ["vrij"] and t["integriteit"]["n"] == n0 + 1 and OND.stempel_status(t) == "ok" and "Wim-MA" in t["manuallyEdited"]["2026-W43"] and not p.evaluate(BANNER, "verify-banner"), json.dumps([t["integriteit"], t["store"]["2026-W43"]["Wim"]["MA"]]))
    # K3 meteen daarna nog een wijziging
    p.evaluate(EDIT, ["2026-W44", "Sam", "DO", ["thuis"]]); p.wait_for_timeout(2500); t = staat(R)
    check("K3 een tweede wijziging erbovenop: beide staan er, het controlegetal telt door (2 opslagen)", t["store"]["2026-W43"]["Wim"]["MA"] == ["vrij"] and t["store"]["2026-W44"]["Sam"]["DO"] == ["thuis"] and t["integriteit"]["n"] == n0 + 2 and OND.stempel_status(t) == "ok", json.dumps([t["integriteit"]])); b.close()
    # K4 gelijktijdig schrijven
    R = nieuw(planning())
    def ander():   # een collega slaat tussendoor iets op
        s = json.loads(R.f["state.json"]); s["store"]["2026-W43"]["Wouter"]["DI"] = ["extern"]; s["manuallyEdited"].setdefault("2026-W43", []).append("Wouter-DI"); OND.stempel(s, s); R.f["state.json"] = json.dumps(s)
    b, p, fouten = open_pagina(pw, R); R.hook = ander; p.evaluate(EDIT, ["2026-W43", "Wim", "MA", ["vrij"]]); p.wait_for_timeout(4000); t = staat(R)
    check("K4 slaat een collega tegelijk iets op (de planning op GitHub is net veranderd), dan overschrijft de pagina dat niet maar voegt er zijn eigen wijziging aan toe: allebei staan er, het controlegetal klopt", t["store"]["2026-W43"]["Wim"]["MA"] == ["vrij"] and t["store"]["2026-W43"]["Wouter"]["DI"] == ["extern"] and OND.stempel_status(t) == "ok" and not p.evaluate(BANNER, "verify-banner"), json.dumps([t["store"]["2026-W43"]["Wim"]["MA"], t["store"]["2026-W43"]["Wouter"]["DI"]])); b.close()
    # K5 teruglezen wijkt af
    R = nieuw(planning()); R.tamper = "weeg"; b, p, fouten = open_pagina(pw, R); p.evaluate(EDIT, ["2026-W43", "Wim", "MA", ["vrij"]]); p.wait_for_timeout(5000); ban = p.evaluate("(() => { const e = document.getElementById('verify-banner'); return e ? e.innerText : null; })()")
    check("K5 klopt het teruglezen na het opslaan niet (hier: een week ontbreekt), dan staat er een rode balk 'De controle na het opslaan klopt niet' en de pagina gaat op slot", ban and "klopt niet" in ban and not p.evaluate("stateTrusted"), json.dumps([(ban or "")[:120]])); b.close()
    # K6 controlegetal klopt niet + bevestigen
    def gewijzigd(s): s["store"]["2026-W43"]["Wim"]["MA"] = ["ziek"]
    sj = planning(); gewijzigd(sj); R = nieuw(sj); b, p, fouten = open_pagina(pw, R)
    voor = p.evaluate(BANNER, "integriteit-banner"); p.evaluate("(async () => { await saveToGitHub({ forceStamp: true }); })()"); p.wait_for_timeout(3500); t = staat(R)
    check("K6 klopt het controlegetal niet (de planning is gewijzigd zonder het bij te werken), dan staat er een rode balk; een Administrator die bevestigt legt het opnieuw vast (bevestigingsteller 1), de planning zelf verandert niet en de balk verdwijnt", voor and OND.stempel_status(t) == "ok" and t["integriteit"]["bev"] == 1 and t["store"]["2026-W43"]["Wim"]["MA"] == ["ziek"] and not p.evaluate(BANNER, "integriteit-banner"), json.dumps([voor, t["integriteit"]])); b.close()
    # K7 verwijderde namen op GitHub
    def vuil(s):
        s["team"] += ["Dave"]; s["template"]["Dave"] = {d: ["kantoor"] for d in DG}
        for w in s["store"].values(): w["Dave"] = {d: ["kantoor"] for d in DG}
    R = nieuw(planning(extra=vuil)); b, p, fouten = open_pagina(pw, R); p.wait_for_timeout(3000); s = p.evaluate("({ team: TEAM.slice(), tekst: document.body.innerText })"); t = staat(R)
    check("K7 staan de verwijderde namen op GitHub, dan zijn ze direct uit de pagina weg (team en scherm) en wordt GitHub zelf hersteld: geen namen meer, kloppend controlegetal", "Dave" not in s["team"] and "Dave" not in s["tekst"] and "Dave" not in json.dumps(t) and OND.stempel_status(t) == "ok", json.dumps([s["team"], "Dave" in json.dumps(t)])); b.close()
    # K8 de server heeft oude weken verwijderd: de pagina ruimt ze op en zet ze niet terug
    weken = tuple(f"2026-W{i:02d}" for i in range(20, 50)); R = nieuw(planning(weken=weken)); b, p, fouten = open_pagina(pw, R)
    s = json.loads(R.f["state.json"]); [s["store"].pop(f"2026-W{i:02d}") for i in range(20, 32)]; OND.stempel(s, s); s["integriteit"]["door"] = "Server (onderhoud)"; R.f["state.json"] = json.dumps(s)
    oud_voor = p.evaluate("Object.keys(store).filter(w => w < '2026-W32').length"); p.evaluate("syncNu()"); p.wait_for_timeout(3500); oud_na = p.evaluate("Object.keys(store).filter(w => w < '2026-W32').length")
    p.evaluate(EDIT, ["2026-W43", "Wim", "MA", ["vrij"]]); p.wait_for_timeout(3500); t = staat(R)
    check("K8 heeft de server oude weken verwijderd, dan ruimt de pagina ze bij de eerstvolgende synchronisatie uit zijn geheugen, een wijziging erna zet ze niet terug op GitHub en de controle na het opslaan slaat geen alarm", oud_voor > 0 and oud_na == 0 and min(t["store"]) == "2026-W32" and t["store"]["2026-W43"]["Wim"]["MA"] == ["vrij"] and not p.evaluate(BANNER, "verify-banner"), json.dumps([oud_voor, oud_na, min(t["store"])])); b.close()
    # K9 de checks: geen schrijfacties, wel uitleg, en lokaal herstel werkt nog
    def rommel(s):
        s["store"]["2026-W43"]["Wim"]["MA"] = ["kantoor", "deel"]; s["manuallyEdited"]["2026-W43"] = ["Wim-MA", "Niemand-MA"]; s["store"]["2026-W43"]["Zed"] = {d: ["kantoor"] for d in DG}
    R = nieuw(planning(extra=rommel)); b, p, fouten = open_pagina(pw, R); voor = dict(R.f); n_put = len(R.puts)
    p.evaluate("HEALTH.lastSync = Date.now() - 400000"); p.evaluate("runChecks({ zwaar: true, repair: true })"); p.wait_for_timeout(3500)
    r = json.loads(p.evaluate("JSON.stringify(Object.fromEntries(CHECKS.map(c => [c.id, CHECK_RESULT[c.id] ? [CHECK_RESULT[c.id].s, CHECK_RESULT[c.id].t, !!(CHECK_RESULT[c.id].hersteld && CHECK_RESULT[c.id].hersteld.gelukt)] : null])))"))
    sk = [k for k, v in r.items() if k in ("statussen", "manueel", "vreemd") and v and v[0] == "let" and "serveronderhoud" in v[1]]
    check("K9 de checks vinden de rommel (onbekende status, verweesde markering, planning van een niet-teamlid) en zeggen dat het serveronderhoud het herstelt, maar de pagina schrijft zelf niets aan de planning, backups of accounts (alleen het logboek mag; planning ongewijzigd)", sorted(sk) == ["manueel", "statussen", "vreemd"] and [x for x in R.puts[n_put:] if not x.startswith("audit/")] == [] and R.f["state.json"] == voor["state.json"], json.dumps([sk, R.puts[n_put:], {k: r[k][:2] for k in ("statussen", "manueel", "vreemd")}]))
    check("K10 wat lokaal is, herstelt de pagina nog wel zelf: een achterstand in de synchronisatie wordt ververst en de check meldt 'automatisch hersteld'", r["sync"][0] == "ok" and r["sync"][2], json.dumps(r["sync"]))
    check("K11 elke check heeft een resultaat (ook de zware) en er zijn geen fouten in de pagina", all(v is not None for v in r.values()) and not fouten, json.dumps([[k for k, v in r.items() if v is None], fouten[:1]])); b.close()
with sync_playwright() as pw:
    # K13 het Checks-venster opent en toont alle checks met een vakje (direct na het openen bekeken: zonder ingelogde gebruiker ruimt de pagina vensters kort daarna weer op)
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R)
    v = p.evaluate("(() => { canSeeInfo = () => true; showChecksWindow(); const o = document.getElementById('checks-overlay'); return o ? { rijen: o.querySelectorAll('[data-check]').length, vakjes: o.querySelectorAll('.ck-box').length, n: CHECKS.length } : null; })()")
    check("K13 het Checks-venster opent en toont elke check met een eigen aanvinkvakje (plus een groot vakje bij de samenvatting), zonder fouten in de pagina", v and v["rijen"] == v["n"] and v["vakjes"] == v["n"] + 1 and not fouten, json.dumps([v, fouten[:1]])); b.close()
# K12 statische controle op slapende code
weg = ["TP_SERVER_ONDERHOUD", "serverModus", "LOKALE_HERSTEL", "SERVER_HERSTELT", "checkSchrijvenMag", "ckMaakBackup", "ckStatusOpschonen", "ckManueelOpschonen", "ckVreemdOpschonen", "ckVerwijderBackups", "ckWachtOpHerstel", "ckWachtOpstaan", "ckOudeWekenVerwijderen", "opts.prune", "opts.opschonen"]
aanwezig = {w: HTML.count(w) for w in weg if HTML.count(w)}
print("INFO slapende code die nog in de pagina staat:", aanwezig or "geen")
check("K12 er staat geen slapende opruimcode meer in de pagina (geen testvlag, geen herstelfuncties voor backups, planning of oude weken, geen prune/opschonen-opties bij het opslaan)", not aanwezig, json.dumps(aanwezig))
print(f"\nklaar: {sum(1 for r in UIT if r.startswith('PASS'))} geslaagd, {sum(1 for r in UIT if r.startswith('FAIL'))} gefaald")
