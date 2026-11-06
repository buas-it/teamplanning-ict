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
    def __init__(self): self.f = {}; self.puts = []; self.hook = None; self.tamper = None; self.na_put = False; self.msgs = []; self.dispatches = []; self.dispatch_status = 204
    def sha(self, p): return hashlib.sha1(self.f[p].encode()).hexdigest()
def handler_voor(R):
    def h(route, request):
        u, m = request.url, request.method
        if m == "OPTIONS": return route.fulfill(status=204, headers=CORS, body="")
        if u.rstrip("/") == PAGE.rstrip("/"): return route.fulfill(status=200, content_type="text/html", body=HTML)
        if u.startswith(PAGE + "index.html?klok="): return route.fulfill(status=200, headers={"Date": __import__("email.utils").utils.formatdate(time.time(), usegmt=True)}, body="")
        if u == "https://api.github.com/repos/buas-it/teamplanning-ict/dispatches" and m == "POST":   # een melding aan de server (logboek)
            if R.dispatch_status == 204: R.dispatches.append(request.post_data_json)
            return route.fulfill(status=R.dispatch_status, headers=CORS, content_type="application/json", body="" if R.dispatch_status == 204 else "{}")
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
                R.f[pad] = base64.b64decode(body["content"]).decode(); R.puts.append(pad); R.msgs.append((pad, body.get("message", "")))
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
    check("K2 een wijziging wordt opgeslagen: de cel staat op GitHub, het controlegetal is met 1 opgehoogd en klopt, de handmatige markering staat erbij, en de controle na het opslaan slaat geen alarm en de pagina maakt zelf geen backup (dat doet de server)", t["store"]["2026-W43"]["Wim"]["MA"] == ["vrij"] and t["integriteit"]["n"] == n0 + 1 and OND.stempel_status(t) == "ok" and "Wim-MA" in t["manuallyEdited"]["2026-W43"] and not p.evaluate(BANNER, "verify-banner") and not any(x.startswith("backups/") for x in R.puts), json.dumps([t["integriteit"], t["store"]["2026-W43"]["Wim"]["MA"], R.puts]))
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
    check("K7 staan de verwijderde namen op GitHub, dan zijn ze direct uit de pagina weg (team en scherm), maar de pagina schrijft GitHub niet zelf schoon: dat doet de server (op GitHub staan ze dus nog tot de volgende serverronde)", "Dave" not in s["team"] and "Dave" not in s["tekst"] and "state.json" not in R.puts and "Dave" in json.dumps(t), json.dumps([s["team"], R.puts, "Dave" in json.dumps(t)])); b.close()
    # K8 de server heeft oude weken verwijderd: de pagina ruimt ze op en zet ze niet terug
    weken = tuple(f"2026-W{i:02d}" for i in range(20, 50)); R = nieuw(planning(weken=weken)); b, p, fouten = open_pagina(pw, R)
    s = json.loads(R.f["state.json"]); [s["store"].pop(f"2026-W{i:02d}") for i in range(20, 32)]; OND.stempel(s, s); s["integriteit"]["door"] = "Server (onderhoud)"; R.f["state.json"] = json.dumps(s)
    oud_voor = p.evaluate("Object.keys(store).filter(w => w < '2026-W32').length"); p.evaluate("syncNu()"); p.wait_for_timeout(3500); oud_na = p.evaluate("Object.keys(store).filter(w => w < '2026-W32').length")
    p.evaluate(EDIT, ["2026-W43", "Wim", "MA", ["vrij"]]); p.wait_for_timeout(3500); t = staat(R)
    check("K8 heeft de server oude weken verwijderd, dan ruimt de pagina ze bij de eerstvolgende synchronisatie uit zijn geheugen, een wijziging erna zet ze niet terug op GitHub en de controle na het opslaan slaat geen alarm", oud_voor > 0 and oud_na == 0 and min(t["store"]) == "2026-W32" and t["store"]["2026-W43"]["Wim"]["MA"] == ["vrij"] and not p.evaluate(BANNER, "verify-banner"), json.dumps([oud_voor, oud_na, min(t["store"])])); b.close()
    # K9 de pagina controleert alleen nog zichzelf: 15 controles (de liveness van de server en wat aan dit apparaat hangt)
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R); ids = p.evaluate("CHECKS.map(c => c.id)")
    check("K9 de pagina heeft nog maar 7 eigen controles (de liveness van de server, dit scherm, de versie, de klok, fouten in de pagina, het geheugen en de logboekwachtrij van dit apparaat); alles wat de planning, accounts, backups, logboek, het token, de verplichte vrije dagen, de verjaardagen en het controlegetal betreft doet de server", sorted(ids) == sorted(["serveronderhoud", "scherm", "versie", "klok", "fouten", "opslag", "audit"]), json.dumps(ids))
    # K10 lokaal herstel
    p.evaluate("HEALTH.lastSync = Date.now() - 400000"); n_put = len(R.puts); p.evaluate("runChecks({ zwaar: true, repair: true })"); p.wait_for_timeout(3000)
    r = json.loads(p.evaluate("JSON.stringify(Object.fromEntries(CHECKS.map(c => [c.id, CHECK_RESULT[c.id] ? [CHECK_RESULT[c.id].s, CHECK_RESULT[c.id].t, !!(CHECK_RESULT[c.id].hersteld && CHECK_RESULT[c.id].hersteld.gelukt)] : null])))"))
    check("K10 wat lokaal is, herstelt de pagina nog wel zelf: een achterstand in de synchronisatie wordt ververst en de check meldt 'automatisch hersteld'; er wordt niets aan de planning, backups of accounts geschreven", r["scherm"][0] == "ok" and r["scherm"][2] and [x for x in R.puts[n_put:] if not x.startswith("audit/")] == [], json.dumps([r["scherm"], R.puts[n_put:]]))
    check("K11 elke eigen controle heeft een resultaat en er zijn geen fouten in de pagina", all(v is not None for v in r.values()) and not fouten, json.dumps([[k for k, v in r.items() if v is None], fouten[:1]])); b.close()
    # K14 de server heeft nog nooit gedraaid
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R)
    v = p.evaluate("(async () => { canSeeInfo = () => true; await laadServerStatus(); showChecksWindow(); const o = document.getElementById('checks-overlay'); const srv = o ? [...o.querySelectorAll('[data-bron=server]')].map(e => [e.dataset.check, e.dataset.status, e.innerText.slice(0, 120)]) : null; return { srv, so: (await CHECKS.find(c => c.id === 'serveronderhoud').run()) }; })()")
    check("K14 heeft de server nog nooit gedraaid (geen statusbestand), dan toont het venster een rode regel 'de server heeft nog nooit gedraaid' en de check 'Serveronderhoud' staat op fout", v["srv"] and v["srv"][0][1] == "fout" and "nog nooit gedraaid" in v["srv"][0][2] and v["so"]["s"] == "fout", json.dumps(v)[:400]); b.close()
    # K13 het venster toont de uitslag van de server en de controles van dit apparaat
    R = nieuw(planning()); sha_nu = None
    status = {"v": 1, "t": "2026-10-19T09:20:00.000Z", "droog": False, "acties": [], "problemen": [], "meldingen": [], "state_sha": "x", "checks": [
        {"id": "weken", "groep": 1, "naam": "Aantal weken in de planning", "s": "ok", "t": "58 weken, 2026-W36 t/m 2027-W52"},
        {"id": "groups", "groep": 2, "naam": "Administrators", "s": "let", "t": "maar één Administrator (Hans)"},
        {"id": "backups", "groep": 3, "naam": "Backups aanwezig", "s": "fout", "t": "er zijn geen backups"},
        {"id": "wachtwoorden", "groep": 2, "naam": "Eigen wachtwoorden", "s": "info", "t": "nog het startwachtwoord: Wim"},
        {"id": "serveronderhoud", "groep": 3, "naam": "Serveronderhoud (taak op GitHub)", "s": "ok", "t": "de server draait"}]}
    R.f["onderhoud.json"] = json.dumps(status); b, p, fouten = open_pagina(pw, R)
    v = p.evaluate("(async () => { canSeeInfo = () => true; await laadServerStatus(); showChecksWindow(); const o = document.getElementById('checks-overlay'); if(!o) return null; const rij = e => [e.dataset.check, e.dataset.status, e.dataset.bron]; return { srv: [...o.querySelectorAll('[data-bron=server]')].map(rij), app: o.querySelectorAll('[data-bron=apparaat]').length, vakjes: o.querySelectorAll('.ck-box').length, rijen: o.querySelectorAll('[data-check]').length, koppen: [...o.querySelectorAll('div')].filter(d => d.style.letterSpacing === '1px').map(d => d.textContent), n: CHECKS.length }; })()")
    check("K13 het Checks-venster toont de uitslag van de server (met zijn kleuren: in orde, let op, fout, info; de eigen liveness-check van de server staat er niet dubbel in) en de eigen controles van dit apparaat, elk met een aanvinkvakje, in vijf groepen waarvan er vier 'gemeten door de server' en een 'gemeten door dit apparaat' heet", v and sorted(x[0] + ":" + x[1] for x in v["srv"]) == sorted(["srv_weken:ok", "srv_groups:let", "srv_backups:fout", "srv_wachtwoorden:info"]) and v["app"] == v["n"] and v["rijen"] == len(v["srv"]) + v["n"] and v["vakjes"] == v["rijen"] + 1 and len(v["koppen"]) == 5 and sum("gemeten door de server" in k for k in v["koppen"]) == 4 and "gemeten door dit apparaat" in v["koppen"][4], json.dumps(v)[:500]); b.close()
    # K15 de liveness van de server
    def so(minuten, sha="x", **extra):
        s = dict(status); s["t"] = (dt.datetime(2026, 10, 19, 9, 30, tzinfo=dt.timezone.utc) - dt.timedelta(minutes=minuten)).strftime("%Y-%m-%dT%H:%M:%S.000Z"); s["state_sha"] = sha; s.update(extra); return s
    for naam, s, verwacht, zoek in (("de server zag de huidige planning (state_sha gelijk), laatste ronde 10 uur geleden", "GELIJK", "ok", "huidige planning gezien"), ("er staat een probleem in de laatste ronde", None, "fout", "meldde een probleem")):
        R = nieuw(planning()); b, p, fouten = open_pagina(pw, R); sha_nu = p.evaluate("ghSha"); st_ = so(600, sha_nu if s == "GELIJK" else "x", **({} if s == "GELIJK" else {"problemen": ["het controlegetal klopt niet"]})); R.f["onderhoud.json"] = json.dumps(st_)
        res = p.evaluate("(async () => await CHECKS.find(c => c.id === 'serveronderhoud').run())()")
        check(f"K15{verwacht[0]} de check 'Serveronderhoud': {naam}", res["s"] == verwacht and zoek in res["t"], json.dumps(res)); b.close()

with sync_playwright() as pw:
    # K16 de pagina maakt na een wijziging geen backup, ook niet na een kwartier, en ruimt geen oude backups of logboekbestanden op, ook niet als de gebruiker Administrator is
    R = nieuw(planning()); R.f["backups/2026-09-01_09-00.json"] = R.f["state.json"]; R.f["audit/2026-09-01.jsonl"] = '{"a":1}\n'; R.f["audit/2026-11-01.jsonl"] = '{"a":1}\n'
    b, p, fouten = open_pagina(pw, R); p.evaluate("canSeeAdmin = () => true"); p.evaluate(EDIT, ["2026-W43", "Wim", "MA", ["vrij"]]); p.wait_for_timeout(2500)
    p.clock.fast_forward(20 * 60 * 1000); p.wait_for_timeout(1500); p.evaluate("syncNu()"); p.clock.fast_forward(7 * 3600 * 1000); p.wait_for_timeout(2500); p.evaluate("syncNu()"); p.wait_for_timeout(2500)
    check("K16 de pagina maakt na een wijziging geen backup (ook niet na 20 minuten) en ruimt geen oude backups of logboekbestanden op (ook niet als de gebruiker Administrator is en er uren voorbij zijn): daar zorgt de server voor; de oude bestanden staan er nog", not any(x.startswith("backups/") for x in R.puts) and "backups/2026-09-01_09-00.json" in R.f and "audit/2026-09-01.jsonl" in R.f and not fouten, json.dumps([[x for x in R.puts if x.startswith("backups/")], fouten[:1]])); b.close()
with sync_playwright() as pw:
    # K17 de ene controle 'Dit scherm is verbonden en bijgewerkt' (voorheen vier): offline, geen verbinding, alleen lezen, achterstand, in orde
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R)
    def sc(js): return p.evaluate("(async () => { " + js + " return await CHECKS.find(c => c.id === 'scherm').run(); })()")
    gezond = sc("HEALTH.github = 'ok'; HEALTH.lastSync = Date.now() - 20000;"); offline = sc("Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });"); online = sc("Object.defineProperty(navigator, 'onLine', { value: true, configurable: true }); HEALTH.github = 'ok'; HEALTH.lastSync = Date.now() - 20000;")
    geenverb = sc("HEALTH.github = 'fout';"); onbekend = sc("HEALTH.github = 'unknown';"); alleenlezen = sc("HEALTH.github = 'ok'; stateTrusted = false;"); p.evaluate("stateTrusted = true"); achter = sc("HEALTH.github = 'ok'; HEALTH.lastSync = Date.now() - 400000;"); nooit = sc("HEALTH.lastSync = 0;")
    check("K17 de controle 'Dit scherm is verbonden en bijgewerkt' (voorheen vier controles) meldt: in orde met teamleden, weken en laatste synchronisatie; offline = fout; geen verbinding = fout; nog niet gecontroleerd = let op; alleen lezen = fout; synchronisatie meer dan 3 minuten geleden = let op; nog nooit gesynchroniseerd = let op", gezond["s"] == "ok" and "10 teamleden" in gezond["t"] and offline["s"] == "fout" and "offline" in offline["t"] and online["s"] == "ok" and geenverb["s"] == "fout" and onbekend["s"] == "let" and alleenlezen["s"] == "fout" and "alleen lezen" in alleenlezen["t"] and achter["s"] == "let" and nooit["s"] == "let", json.dumps([gezond, offline, geenverb, onbekend, alleenlezen, achter, nooit])[:600]); b.close()
with sync_playwright() as pw:
    # K18 de pagina schrijft geen wijzigingsregels meer (dat doet de server) maar geeft de toelichting bij een opslag mee in het commitbericht
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R)
    p.evaluate(EDIT, ["2026-W43", "Wim", "MA", ["vrij"]]); p.wait_for_timeout(2500); m1 = [m for pad, m in R.msgs if pad == "state.json"][-1]
    p.evaluate("auditSetHint('periode: Wim vrij 12-11 t/m 14-11')"); p.evaluate(EDIT, ["2026-W43", "Wim", "DI", ["vrij"]]); p.wait_for_timeout(2500); m2 = [m for pad, m in R.msgs if pad == "state.json"][-1]
    p.evaluate(EDIT, ["2026-W43", "Wim", "WO", ["vrij"]]); p.wait_for_timeout(2500); m3 = [m for pad, m in R.msgs if pad == "state.json"][-1]
    wijz_regels = [pad for pad in R.puts if pad.startswith("audit/") and any('"action":"wijziging"' in R.f.get(pad, "") for _ in [0])]
    check("K18 de pagina schrijft geen wijzigingsregels meer in het logboek (dat doet de server na elke opslag); een gewone opslag heeft het commitbericht 'Update planning', een opslag met een toelichting (hier een Periode) draagt die toelichting in het commitbericht, en die geldt maar voor die ene opslag", m1.startswith("Update planning") and m2.startswith("periode: Wim vrij 12-11 t/m 14-11") and m3.startswith("Update planning") and not wijz_regels and '"action":"wijziging"' not in "".join(v for kk, v in R.f.items() if kk.startswith("audit/")) and not fouten, json.dumps([m1, m2, m3, wijz_regels, fouten[:1]])); b.close()
with sync_playwright() as pw:
    # K19-K21 bezoeken en inloggen: de pagina meldt ze aan de server (repository_dispatch) en schrijft het logboek niet meer zelf
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R)
    p.evaluate("auditEvent('test: site geopend', { anon: true })"); p.wait_for_timeout(1500)
    w = R.dispatches[0] if R.dispatches else None; q = p.evaluate("auditQueue.length")
    check("K19 een bezoek of inlog wordt aan de server gemeld: een aanvraag 'logboek' met de regel (regel-id, soort, tijdstip van het apparaat, gebruiker, apparaat), de wachtrij is daarna leeg en de pagina schrijft zelf niets in het logboek", w and w["event_type"] == "logboek" and len(w["client_payload"]["events"]) == 1 and w["client_payload"]["events"][0]["action"] == "test: site geopend" and w["client_payload"]["events"][0]["eid"] and w["client_payload"]["events"][0]["anon"] is True and "t" in w["client_payload"]["events"][0] and q == 0 and not [x for x in R.puts if x.startswith("audit/")], json.dumps([w, q, [x for x in R.puts if x.startswith("audit/")]])[:400])
    R.dispatch_status = 500; p.evaluate("auditEvent('test: tweede bezoek', { anon: true })"); p.wait_for_timeout(1500); q_fout = p.evaluate("auditQueue.length"); ok_fout = p.evaluate("auditLastOk")
    R.dispatch_status = 204; p.evaluate("auditFlush()"); p.wait_for_timeout(1500); q_ok = p.evaluate("auditQueue.length"); w2 = [e for d_ in R.dispatches for e in d_["client_payload"]["events"] if e["action"] == "test: tweede bezoek"]
    check("K20 komt de melding niet aan (GitHub geeft een fout), dan blijft hij in de wachtrij van het apparaat staan (de stip wordt rood) en wordt hij bij de volgende poging alsnog verstuurd, met dezelfde regel-id: er gaat niets verloren", q_fout == 1 and ok_fout is False and q_ok == 0 and len(w2) == 1, json.dumps([q_fout, ok_fout, q_ok, len(w2)]))
    p.evaluate("for(let i = 0; i < 45; i++) auditQueue.push({ v: 1, eid: 'batch-' + String(i).padStart(3, '0') + '-xxxx', t: new Date().toISOString(), user: 'Hans', ws: '', device: '', id: '', wsinfo: '', action: 'site geopend', n: 0, trunc: false, changes: [] }); auditFlush()"); p.wait_for_timeout(2500)
    groottes = [len(d_["client_payload"]["events"]) for d_ in R.dispatches[-3:]]
    check("K21 een lange wachtrij gaat in aanvragen van hooguit 20 regels, in volgorde: 45 regels worden 20, 20 en 5", groottes == [20, 20, 5] and p.evaluate("auditQueue.length") == 0 and not fouten, json.dumps([groottes, p.evaluate("auditQueue.length"), fouten[:1]])); b.close()
# K12 statische controle op slapende code en op controles die naar de server zijn verhuisd
weg = ["TP_SERVER_ONDERHOUD", "serverModus", "LOKALE_HERSTEL", "SERVER_HERSTELT", "checkSchrijvenMag", "ckMaakBackup", "ckStatusOpschonen", "ckManueelOpschonen", "ckVreemdOpschonen", "ckVerwijderBackups", "ckWachtOpHerstel", "ckWachtOpstaan", "ckOudeWekenVerwijderen", "opts.prune", "opts.opschonen", "auditAppend", "ckBackupLees", "ckManueelTelling", "function ckOudeWeken(", "ckLeesTekst", "auditDiff", "auditAfterSave", "auditRebase", "auditWho", "auditBase", "healRemoved", "auditCleanup", "retryPendingBackup", "Verwijder oude backup", "Backup na bewerken", "Verwijder backups ouder dan 14 dagen"] + [f'{{ id: "{x}"' for x in ("accounts", "backups", "backup_geldig", "backup_actueel", "groups", "weken", "oudeweken", "statussen", "manueel", "vreemd", "namen", "team", "halvedag", "grootte", "logboek", "instellingen", "wachtwoorden", "remote", "uitrol", "rechten", "limiet", "stempel", "verplicht", "verjaardagen", "online", "github", "sync", "geladen")] + ["chkNet"]
aanwezig = {w: HTML.count(w) for w in weg if HTML.count(w)}
print("INFO slapende code of verhuisde controles die nog in de pagina staan:", aanwezig or "geen")
check("K12 er staat geen slapende opruimcode meer in de pagina, geen controle meer die de server doet, en ook geen automatische backups, backup- of logboekopruiming en geen schoonschrijven van verwijderde namen meer (dat doet allemaal de server)", not aanwezig, json.dumps(aanwezig))
print(f"\nklaar: {sum(1 for r in UIT if r.startswith('PASS'))} geslaagd, {sum(1 for r in UIT if r.startswith('FAIL'))} gefaald")
