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
    def __init__(self): self.f = {}; self.puts = []; self.hook = None; self.tamper = None; self.na_put = False; self.msgs = []; self.dispatches = []; self.dispatch_status = 204; self.klok_extra = 0; self.klok_stuk = False; self.klok_fake = None; self.klok_real0 = 0
    def sha(self, p): return hashlib.sha1(self.f[p].encode()).hexdigest()
def handler_voor(R):
    def h(route, request):
        u, m = request.url, request.method
        if m == "OPTIONS": return route.fulfill(status=204, headers=CORS, body="")
        if u.rstrip("/") == PAGE.rstrip("/"): return route.fulfill(status=200, content_type="text/html", body=HTML)
        if u.startswith(PAGE + "index.html?klok="):   # de servertijd van GitHub Pages: gelijk aan de nagebootste klok van het apparaat plus R.klok_extra seconden
            if R.klok_stuk: return route.fulfill(status=404, body="")
            nu_s = (R.klok_fake + (time.time() - R.klok_real0) if R.klok_fake is not None else time.time()) + R.klok_extra
            return route.fulfill(status=200, headers={"Date": __import__("email.utils").utils.formatdate(int(nu_s), usegmt=True)}, body="")
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
def open_pagina(pw, R, klok_extra=None, breedte=1200, klok_stuk=False, tijdzone="UTC", start=None, init_script=None):
    if klok_extra is not None: R.klok_extra = klok_extra
    R.klok_stuk = klok_stuk; start = start or dt.datetime(2026, 10, 19, 9, 30, tzinfo=dt.timezone.utc)
    b = pw.chromium.launch(); ctx = b.new_context(viewport={"width": breedte, "height": 1300}, timezone_id=tijdzone)
    if init_script: ctx.add_init_script(init_script)
    ctx.route("**/*", handler_voor(R)); p = ctx.new_page(); fouten = []; p.on("pageerror", lambda e: fouten.append(str(e)[:140]))
    p.clock.install(time=start); R.klok_fake = start.timestamp(); R.klok_real0 = time.time(); p.goto(PAGE); p.wait_for_timeout(4500); return b, p, fouten
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
    check("K9 de pagina heeft nog maar 8 eigen controles (de liveness van de server, dit scherm, de reactietijd van GitHub op dit apparaat, de versie, de klok, fouten in de pagina, het geheugen en de logboekwachtrij van dit apparaat); alles wat de planning, accounts, backups, logboek, het token, de verplichte vrije dagen, de verjaardagen en het controlegetal betreft doet de server", sorted(ids) == sorted(["serveronderhoud", "scherm", "ghtijd", "versie", "klok", "fouten", "opslag", "audit"]), json.dumps(ids))
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
with sync_playwright() as pw:
    # K22 de tijd van de server linksboven, in Nederlandse tijd
    JS_KLOK = "(() => { const c = document.getElementById('srv-clock'), b = document.getElementById('who-btn'), h = document.querySelector('.header h1'), r = c.getBoundingClientRect(), br = b.getBoundingClientRect(); return { t: c.textContent, fs: getComputedStyle(c).fontSize, bfs: getComputedStyle(b).fontSize, kl: getComputedStyle(c).color, hk: getComputedStyle(h).color, l: r.left, tp: r.top, cy: r.top + r.height / 2, by: br.top + br.height / 2, title: c.title, op: c.style.opacity }; })()"
    INLOG = "document.documentElement.classList.remove('tp-gated'); currentIdentity = makeIdentity('Hans', 'MacBook', ''); showLockIndicator();"
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=3600); p.evaluate(INLOG); p.wait_for_timeout(600); i1 = p.evaluate(JS_KLOK); p.wait_for_timeout(2300); t2 = p.evaluate("document.getElementById('srv-clock').textContent")
    check("K22 linksboven staat een klok die doorloopt: in dezelfde lettergrootte als 'Ingelogd als' (12 px), in dezelfde kleur als de titel (wit), linksboven in beeld, en hij verspringt elke seconde", re.match(r"^\d\d:\d\d:\d\d$", i1["t"]) and i1["fs"] == i1["bfs"] == "12px" and i1["kl"] == i1["hk"] and i1["l"] < 40 and i1["tp"] < 40 and t2 != i1["t"], json.dumps([i1, t2])[:400])
    check("K22b de klok toont de tijd van de SERVER in Nederlandse tijd: loopt de server 1 uur voor op het apparaat (apparaat 09:30 UTC, server 10:30 UTC) dan staat er 12:3x (zomertijd, UTC+2) en niet de tijd van het apparaat; de uitleg (bij het aanwijzen) noemt de bron, de nauwkeurigheid, het verschil met het apparaat en de datum", i1["t"].startswith("12:3") and "Tijd van de server (GitHub)" in i1["title"] and "ongeveer 1 s nauwkeurig" in i1["title"] and "Dit apparaat loopt 1 u achter" in i1["title"] and "maandag 19 oktober 2026" in i1["title"] and i1["op"] == "", json.dumps(i1)[:400]); b.close()
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_stuk=True); p.evaluate(INLOG); p.wait_for_timeout(600); i3 = p.evaluate(JS_KLOK)
    check("K22c kan de tijd van de server niet worden gemeten, dan toont de klok de tijd van het apparaat (in Nederlandse tijd), gedempt, met de uitleg dat de servertijd niet beschikbaar is", i3["t"].startswith("11:3") and i3["op"] == "0.45" and "niet beschikbaar" in i3["title"], json.dumps(i3)[:300]); b.close()
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0, breedte=390); p.evaluate(INLOG); p.wait_for_timeout(600); i4 = p.evaluate(JS_KLOK)
    check("K22d op een smal scherm (telefoon) staat de klok links op dezelfde hoogte als 'Ingelogd als' (hooguit 3 pixels verschil in het midden) en blijft links in beeld", abs(i4["cy"] - i4["by"]) <= 3 and i4["l"] < 40 and i4["fs"] == "12px" and not fouten, json.dumps([i4, fouten[:1]])[:300]); b.close()
with sync_playwright() as pw:
    # K23-K28 de tijd van de server is bepalend: vandaag, de week, tijdstempels en de weergave in Nederlandse tijd
    UTC = dt.timezone.utc; WK = "document.querySelector('.day-hd.today-col .day-hd-name') ? document.querySelector('.day-hd.today-col .day-hd-name').textContent + ' ' + document.querySelector('.day-hd.today-col .day-hd-date').textContent : null"
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=-86400, start=dt.datetime(2026, 10, 20, 9, 30, tzinfo=UTC)); p.wait_for_timeout(2500)
    v = p.evaluate("({ vandaag: today.getFullYear() + '-' + (today.getMonth() + 1) + '-' + today.getDate(), kop: " + WK + ", offset: SRV_OFFSET })")
    check("K23 loopt de klok van het apparaat een dag voor (apparaat zegt 20 oktober, de server 19 oktober), dan rekent de pagina met de datum van de server: vandaag is 19 oktober en de kolom van die dag is gemarkeerd als vandaag (maandag, niet dinsdag)", v["vandaag"] == "2026-10-19" and v["kop"] and v["kop"].startswith("MA") or (v["kop"] or "").lower().startswith("ma"), json.dumps(v)); b.close()
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0, tijdzone="Pacific/Auckland", start=dt.datetime(2026, 10, 19, 12, 0, tzinfo=UTC)); p.wait_for_timeout(2500)
    v = p.evaluate("({ vandaag: today.getFullYear() + '-' + (today.getMonth() + 1) + '-' + today.getDate(), uur: nuNL().getHours(), apparaat: new Date().getDate(), loginTijd: loginTijd(Date.UTC(2026, 0, 15, 12, 0, 0)), dagsleutel: nlDagSleutel(Date.UTC(2026, 9, 19, 23, 30, 0)) })")
    check("K24 staat het apparaat in een andere tijdzone (hier Nieuw-Zeeland, waar het al 20 oktober is), dan blijft 'vandaag' de Nederlandse datum (19 oktober, het is 14:00 in Nederland), en tijdstippen worden in Nederlandse tijd getoond (12:00 UTC in januari is 13:00) en dagen in het logboek op de Nederlandse dag (23:30 UTC op 19 oktober is al 20 oktober in Nederland)", v["vandaag"] == "2026-10-19" and v["uur"] == 14 and v["apparaat"] == 20 and v["loginTijd"] == "13:00" and v["dagsleutel"] == "2026-10-20", json.dumps(v)); b.close()
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=3600); p.wait_for_timeout(1500)
    p.evaluate(EDIT, ["2026-W43", "Wim", "MA", ["vrij"]]); p.wait_for_timeout(2500); t_s = staat(R)["integriteit"]["t"]
    p.evaluate("auditEvent('test: servertijd', { anon: true })"); p.wait_for_timeout(1500); ev_t = R.dispatches[-1]["client_payload"]["events"][-1]["t"] if R.dispatches else None
    check("K25 tijdstempels die de pagina vastlegt zijn servertijd: loopt de server een uur voor op het apparaat (apparaat 09:3x UTC, server 10:3x UTC), dan staat in het controlegetal van een opslag en in een gemelde logregel 10:3x UTC, niet de tijd van het apparaat", t_s.startswith("2026-10-19T10:3") and ev_t and ev_t.startswith("2026-10-19T10:3"), json.dumps([t_s, ev_t])); b.close()
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_stuk=True, init_script="localStorage.setItem('tp_srv_offset', '3600000')"); p.wait_for_timeout(1500)
    v = p.evaluate("({ verschil: srvNowMs() - Date.now(), uur: nuNL().getHours(), bewaard: localStorage.getItem('tp_srv_offset') })")
    check("K26 de gemeten afwijking wordt bewaard en gebruikt: ook als de meting nu niet lukt, rekent de pagina vanaf de eerste seconde met de bewaarde afwijking van de vorige keer (hier +1 uur: servertijd 10:30 UTC = 12:30 in Nederland)", abs(v["verschil"] - 3600000) < 2000 and v["uur"] == 12 and v["bewaard"] == "3600000", json.dumps(v)); b.close()
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0); p.wait_for_timeout(2000)
    voor = p.evaluate("today.getDate()"); p.evaluate("SRV_OFFSET = SRV_OFFSET + 86400000; srvDagCheck()"); p.wait_for_timeout(500); na = p.evaluate("today.getDate()"); kop_na = p.evaluate(WK)
    check("K27 wisselt de dag volgens de server (hier: een dag verder), dan wordt 'vandaag' bijgesteld en het scherm opnieuw getekend: de markering staat bij de nieuwe dag", voor == 19 and na == 20 and kop_na and "20" in kop_na and not fouten, json.dumps([voor, na, kop_na, fouten[:1]])); b.close()
with sync_playwright() as pw:
    # K29 de naam van een backup die de pagina maakt (handmatig of vlak voor een terugzetting): datum en tijd in Nederlandse tijd, ook op een apparaat in een andere tijdzone
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0, tijdzone="Asia/Bangkok", start=dt.datetime(2026, 10, 20, 0, 30, tzinfo=dt.timezone.utc)); p.wait_for_timeout(2000)
    n0 = len(R.puts); p.evaluate("maybeBackup(JSON.stringify(serializeState()), { always: true, force: true, label: 'Handmatige backup' })"); p.wait_for_timeout(2500)
    namen = [x for x in R.puts[n0:] if x.startswith("backups/")]
    check("K29 de naam van een backup die de pagina maakt heeft de datum en de tijd in Nederlandse tijd, ook op een apparaat in een andere tijdzone: 00:30 UTC op 20 oktober is 02:30 op 20 oktober in Nederland (zomertijd), terwijl het op dit apparaat (Thailand, UTC+7) 07:30 is en de UTC-datum van de Nederlandse tijd een dag eerder zou zijn", len(namen) == 1 and re.match(r"^backups/2026-10-20_02-3[01]\.json$", namen[0]) and not fouten, json.dumps([namen, fouten[:1]])); b.close()
with sync_playwright() as pw:
    # K30 het logboekvenster kijkt 14 dagen terug, net zo lang als de server de dagbestanden bewaart: bestanden van voor de eerste dag worden niet eens opgehaald, en regels ouder dan 14 dagen (volgens de servertijd) worden niet getoond
    UTC = dt.timezone.utc; R = nieuw(planning())
    def regel(i, tijd): return json.dumps({"v": 1, "eid": "k30-" + str(i), "t": tijd, "user": "Hans", "action": "bezoek", "detail": "test " + str(i), "dev": "x"})
    R.f["audit/2026-11-02.jsonl"] = regel(1, "2026-11-02T10:00:00.000Z") + "\n"; R.f["audit/2026-11-03.jsonl"] = regel(2, "2026-11-03T10:00:00.000Z") + "\n" + regel(3, "2026-11-03T13:00:00.000Z") + "\n"; R.f["audit/2026-11-10.jsonl"] = regel(4, "2026-11-10T09:00:00.000Z") + "\n"
    b, p, fouten = open_pagina(pw, R, klok_extra=0, start=dt.datetime(2026, 11, 17, 12, 0, tzinfo=UTC)); p.evaluate("document.documentElement.classList.remove('tp-gated'); currentIdentity = makeIdentity('Hans', 'MacBook', ''); showLockIndicator();"); p.wait_for_timeout(1500)
    opgehaald = []; p.on("request", lambda rq: opgehaald.append(re.search(r"/contents/audit/([^?]+)", rq.url).group(1)) if re.search(r"/contents/audit/[^?]+\.jsonl", rq.url) else None)
    p.evaluate("() => { showAuditModal(); }"); p.wait_for_timeout(3000); tel = p.evaluate("(document.getElementById('au-count') || {}).textContent || ''")
    check("K30 het logboekvenster kijkt 14 dagen terug (de server bewaart de dagbestanden ook 14 dagen): op 17 november 12:00 wordt het bestand van 2 november niet opgehaald, dat van 3 november en 10 november wel; de regel van 3 november 10:00 (14 dagen en 2 uur geleden) valt buiten het venster, die van 13:00 niet, en de teller zegt 'laatste 14 dagen'", sorted(set(opgehaald)) == ["2026-11-03.jsonl", "2026-11-10.jsonl"] and "van 2 (laatste 14 dagen)" in tel and not fouten, json.dumps([sorted(set(opgehaald)), tel, fouten]))
    p.evaluate("AUDIT_VIEW_DAYS") ; p.evaluate("() => { showStatsWindow(); }"); p.wait_for_timeout(2500); sub = p.evaluate("(document.getElementById('stat-sub') || {}).textContent || ''")
    check("K30b Statistics kijkt ook 14 dagen terug", "laatste 14 dagen" in sub and not fouten, json.dumps([sub, fouten]))
with sync_playwright() as pw:
    # K31 elke verplichte vrije dag is zichtbaar gekenmerkt: de naam staat boven de dag (🎌) en de vakjes van die dag hebben een tekstballon en schuine strepen; gewone dagen hebben niets
    UTC = dt.timezone.utc; R = nieuw(planning())
    b, p, fouten = open_pagina(pw, R, klok_extra=0, start=dt.datetime(2026, 12, 24, 12, 0, tzinfo=UTC)); p.wait_for_timeout(2500)
    kop = p.evaluate("[...document.querySelectorAll('.day-hd-feest')].map(e => e.textContent)"); n_vak = p.evaluate("document.querySelectorAll('.cell.verplicht').length"); n_dag = p.evaluate("document.querySelectorAll('.day-hd').length"); ballon = p.evaluate("(document.querySelector('.cell.verplicht') || {}).title || ''")
    check("K31 in de weken 52 en 53 van 2026 staat boven elke verplichte vrije dag de naam (Kerstavond, 1e Kerstdag, 4 keer Kerstvakantie, Nieuwjaarsdag), alleen boven die 7 van de 10 dagen; de 70 vakjes van die dagen (10 mensen) hebben het kenmerk en een tekstballon", kop == ["\U0001F38C Kerstavond", "\U0001F38C 1e Kerstdag", "\U0001F38C Kerstvakantie", "\U0001F38C Kerstvakantie", "\U0001F38C Kerstvakantie", "\U0001F38C Kerstvakantie", "\U0001F38C Nieuwjaarsdag"] and n_dag == 10 and n_vak == 70 and ballon.startswith("Verplichte vrije dag: ") and not fouten, json.dumps([kop, n_vak, n_dag, ballon, fouten]))
    sleutels = p.evaluate("({ zonder: [...LOCKED_DAYS].filter(k => !VERPLICHT_NAMEN[k]), teveel: Object.keys(VERPLICHT_NAMEN).filter(k => !LOCKED_DAYS.has(k)), gewoon: verplichtNaam('2026-W45', 'MA') })")
    check("K31b elke sleutel van LOCKED_DAYS heeft een naam en andersom (een nieuwe verplichte vrije dag zonder naam valt op), en een gewone dag geeft geen naam", sleutels == {"zonder": [], "teveel": [], "gewoon": ""}, json.dumps(sleutels))
with sync_playwright() as pw:
    # K32 het venster Geen Beheer geeft bij een opgelegde verplichte vrije dag ook de reden; een gewone dag zonder beheer krijgt geen reden
    UTC = dt.timezone.utc; R = nieuw(planning())
    b, p, fouten = open_pagina(pw, R, klok_extra=0, start=dt.datetime(2026, 12, 21, 12, 0, tzinfo=UTC))
    p.evaluate("document.documentElement.classList.remove('tp-gated'); currentIdentity = makeIdentity('Hans', 'MacBook', ''); showLockIndicator(); TEAM.forEach(n => { store['2026-W52'][n]['WO'] = ['vrij']; });"); p.wait_for_timeout(800)
    p.evaluate("() => { showGeenBeheerModal(); }"); p.wait_for_timeout(800)
    rijen = p.evaluate("[...document.querySelectorAll('.tp-overlay')].pop().innerText.split('\\n').map(s => s.trim()).filter(Boolean)")
    def na(label): i = rijen.index(label); return rijen[i + 1: i + 3]
    ok = True; det = []
    for label, naam in (("Donderdag 24 dec 2026", "Kerstavond"), ("Vrijdag 25 dec 2026", "1e Kerstdag"), ("Maandag 28 dec 2026", "Kerstvakantie"), ("Vrijdag 1 jan 2027", "Nieuwjaarsdag")):
        try: r = na(label); good = len(r) == 2 and "Geen beheer" in r[0] and r[1].endswith("(" + naam + "), voor iedereen opgelegd") and "Reden: verplichte vrije dag" in r[1]
        except ValueError: r = None; good = False
        ok = ok and good; det.append([label, r])
    try: gewoon = na("Woensdag 23 dec 2026")
    except ValueError: gewoon = None
    check("K32 Geen Beheer: bij de 4 opgelegde verplichte vrije dagen (Kerstavond, 1e Kerstdag, Kerstvakantie, Nieuwjaarsdag) staat de reden eronder; een gewone vrije woensdag zonder beheer staat er zonder reden bij", ok and gewoon is not None and "Geen beheer" in gewoon[0] and not any("Reden" in x for x in gewoon[:1]) and p.evaluate("document.querySelectorAll('.gb-reden').length") == 7 and not fouten, json.dumps([det, gewoon, fouten]))
# K12 statische controle op slapende code en op controles die naar de server zijn verhuisd
weg = ["TP_SERVER_ONDERHOUD", "serverModus", "LOKALE_HERSTEL", "SERVER_HERSTELT", "checkSchrijvenMag", "ckMaakBackup", "ckStatusOpschonen", "ckManueelOpschonen", "ckVreemdOpschonen", "ckVerwijderBackups", "ckWachtOpHerstel", "ckWachtOpstaan", "ckOudeWekenVerwijderen", "opts.prune", "opts.opschonen", "auditAppend", "new Date()", "ckBackupLees", "ckManueelTelling", "function ckOudeWeken(", "ckLeesTekst", "auditDiff", "auditAfterSave", "auditRebase", "auditWho", "auditBase", "healRemoved", "auditCleanup", "retryPendingBackup", "Verwijder oude backup", "Backup na bewerken", "Verwijder backups ouder dan 14 dagen"] + [f'{{ id: "{x}"' for x in ("accounts", "backups", "backup_geldig", "backup_actueel", "groups", "weken", "oudeweken", "statussen", "manueel", "vreemd", "namen", "team", "halvedag", "grootte", "logboek", "instellingen", "wachtwoorden", "remote", "uitrol", "rechten", "limiet", "stempel", "verplicht", "verjaardagen", "online", "github", "sync", "geladen")] + ["chkNet"]
aanwezig = {w: HTML.count(w) for w in weg if HTML.count(w)}
print("INFO slapende code of verhuisde controles die nog in de pagina staan:", aanwezig or "geen")
check("K12 er staat geen slapende opruimcode meer in de pagina, geen controle meer die de server doet, en ook geen automatische backups, backup- of logboekopruiming en geen schoonschrijven van verwijderde namen meer (dat doet allemaal de server)", not aanwezig, json.dumps(aanwezig))
with sync_playwright() as pw:
    UTC = dt.timezone.utc
    ADMIN = "currentIdentity = makeIdentity('Hans', 'MacBook', ''); showLockIndicator();"
    def klaar(p): p.evaluate("document.documentElement.classList.remove('tp-gated'); document.querySelectorAll('.tp-overlay[data-gate]').forEach(o => o.remove())")
    # K33 een Administrator maakt een verplichte vrije dag aan: settings.json krijgt de dag (met naam, wie en wanneer), iedereen staat die dag op Vrij, de planning wordt opgeslagen, de dag is gemarkeerd en vergrendeld, en het staat in het logboek
    R = nieuw(planning()); R.f["settings.json"] = json.dumps({"v": 1, "talen": {"Wim": ["nl"]}, "verjaardagen": False})
    b, p, fouten = open_pagina(pw, R, klok_extra=0); klaar(p)
    p.evaluate(ADMIN + " editUnlocked = true;"); p.evaluate("() => { showVerplichtModal(); }"); p.wait_for_timeout(500)
    voor = p.evaluate("!!document.getElementById('vp-datum') && !!document.getElementById('vp-toevoegen')")
    p.fill("#vp-datum", "2026-10-28"); p.fill("#vp-naam", "Bedrijfsuitje"); p.click("#vp-toevoegen"); p.wait_for_timeout(5000)
    st = json.loads(R.f["settings.json"]); rec = (st.get("verplichteDagen") or {}).get("2026-10-28") or {}
    allen_vrij = p.evaluate("TEAM.every(n => store['2026-W44'][n].WO[0] === 'vrij') && store['2026-W44'].Hans.DO[0] === 'kantoor'")
    mem = p.evaluate("[LOCKED_DAYS.has('2026-W44-WO'), verplichtNaam('2026-W44','WO'), TEAM.every(n => store['2026-W44'][n].WO[0] === 'vrij')]")
    lijst = p.evaluate("document.getElementById('vp-lijst').innerText")
    audit = json.dumps(R.dispatches) + " ".join(R.f[x] for x in R.f if x.startswith("audit/"))
    check("K33 Administrator maakt een verplichte vrije dag aan: settings.json bevat de dag met naam, door en op (en laat de overige instellingen staan), iedereen staat die dag meteen op Vrij in deze pagina (andere dagen blijven), de dag staat in LOCKED_DAYS met naam, het scherm toont hem en het logboek heeft een regel", voor and rec.get("naam") == "Bedrijfsuitje" and rec.get("door") == "Hans" and rec.get("op") and st.get("talen") == {"Wim": ["nl"]} and st.get("verjaardagen") is False and allen_vrij and mem == [True, "Bedrijfsuitje", True] and "Bedrijfsuitje" in lijst and "verplichte vrije dag" in audit and not fouten, [voor, rec, allen_vrij, mem, lijst[:80], audit[-300:], fouten])
    # K33b de dag is in de weekweergave gemarkeerd (titel, 🎌 en vergrendeld) en kan niet worden gewijzigd
    p.evaluate("document.querySelectorAll('.vp-overlay').forEach(o => o.remove()); render();"); p.wait_for_timeout(500)
    kop = p.evaluate("[...document.querySelectorAll('.day-hd-feest')].map(x => x.textContent)")
    cel = p.evaluate("document.querySelectorAll('.cell.verplicht').length")
    check("K33b de nieuwe verplichte vrije dag staat met naam boven de dag (🎌 Bedrijfsuitje) en de vakjes zijn gemarkeerd als verplicht", any("Bedrijfsuitje" in x for x in kop) and cel >= len(TEAM), [kop, cel])
    # K33c verwijderen: de dag verdwijnt uit settings.json en uit LOCKED_DAYS; andere instellingen blijven
    p.evaluate("() => { showVerplichtModal(); }"); p.wait_for_timeout(400)
    p.click(".vp-del"); p.wait_for_timeout(3000)
    st2 = json.loads(R.f["settings.json"]); mem2 = p.evaluate("[LOCKED_DAYS.has('2026-W44-WO'), verplichtNaam('2026-W44','WO')]")
    audit2 = json.dumps(R.dispatches) + " ".join(R.f[x] for x in R.f if x.startswith("audit/"))
    check("K33c Administrator verwijdert de zelf aangemaakte dag: weg uit settings.json en uit LOCKED_DAYS (niet meer vergrendeld), de overige instellingen blijven, het logboek noemt het verwijderen", not st2.get("verplichteDagen") and mem2 == [False, ""] and st2.get("talen") == {"Wim": ["nl"]} and "verwijderd" in audit2, [st2, mem2, audit2[-300:]])
    # K33d controles: weekend, verleden, vaste dag, bewerken uit, te ver vooruit
    res = p.evaluate("""async () => { const u = []; editUnlocked = true; for(const [d, n] of [["2026-10-31", "x"], ["2026-10-16", "x"], ["2026-12-24", "x"], ["2029-01-02", "x"], ["", "x"], ["2026-13-45", "x"]]){ u.push((await settingsSetVerplicht(d, n)).error || "geen fout"); } editUnlocked = false; u.push((await settingsSetVerplicht("2026-10-28", "x")).error); editUnlocked = true; currentIdentity = makeIdentity('Bas', 'MacBook', ''); u.push((await settingsSetVerplicht("2026-10-28", "x")).error); return u; }""")
    check("K33d ongeldige aanvragen worden geweigerd met een duidelijke tekst en schrijven niets: weekend, verleden, vaste verplichte dag, meer dan twee jaar vooruit, geen of onmogelijke datum, bewerken uit, geen Administrator", all(x != "geen fout" for x in res) and "weekend" not in res[0] and "werkdag" in res[0] and "verleden" in res[1] and "vaste" in res[2] and "twee jaar" in res[3] and res[6] == "Bewerken staat uit." and "Administrator" in res[7] and not json.loads(R.f["settings.json"]).get("verplichteDagen"), res)
    # K33e een niet-Administrator krijgt het scherm niet te zien
    p.evaluate("document.querySelectorAll('.vp-overlay').forEach(o => o.remove()); currentIdentity = makeIdentity('Bas', 'MacBook', ''); editUnlocked = true; showVerplichtModal();"); p.wait_for_timeout(300)
    geen = p.evaluate("document.querySelectorAll('.vp-overlay').length")
    b.close()
    # K33f een andere pagina (niet-Administrator) laadt een bestaande dag uit settings.json: iedereen op Vrij, naam zichtbaar, Geen Beheer toont de reden; een kwaadaardige naam wordt onschadelijk gemaakt
    R = nieuw(planning()); R.f["settings.json"] = json.dumps({"v": 1, "verplichteDagen": {"2026-10-28": {"naam": "<img src=x onerror=window.PWNED=1>Uitje", "door": "Hans", "op": "2026-10-19T08:00:00.000Z"}, "2026-10-31": {"naam": "weekend"}, "kapot": {"naam": "x"}}})
    b, p, fouten = open_pagina(pw, R, klok_extra=0); klaar(p)
    p.evaluate("currentIdentity = makeIdentity('Bas', 'MacBook', ''); showLockIndicator(); render();"); p.wait_for_timeout(600)
    r = p.evaluate("""() => { const o = {}; o.naam = verplichtNaam('2026-W44','WO'); o.vrij = TEAM.every(n => store['2026-W44'][n].WO[0] === 'vrij'); o.extra = Object.keys(VERPLICHT_EXTRA); o.n = LOCKED_DAYS.size; o.pwn = !!window.PWNED; return o; }""")
    check("K33f een pagina die settings.json met een verplichte vrije dag laadt, zet hem voor iedereen op Vrij; een naam met HTML wordt schoongemaakt (niets wordt uitgevoerd); een weekend of kapotte datum in het bestand wordt genegeerd", "Uitje" in r["naam"] and "<" not in r["naam"] and r["vrij"] and r["extra"] == ["2026-W44-WO"] and r["n"] == 22 + 1 and not r["pwn"] and not fouten, [r, fouten])
    # K33h een andere instelling wijzigen (talen) laat de verplichte vrije dagen staan, in het bestand en in de pagina; het Info-menu heeft het onderdeel voor een Administrator
    res = p.evaluate("""async () => { currentIdentity = makeIdentity('Hans', 'MacBook', ''); editUnlocked = true; const r = await settingsSetTalen('Wim', ['nl', 'tr']); return [r.ok === true, LOCKED_DAYS.has('2026-W44-WO'), Object.keys(VERPLICHT_EXTRA)]; }""")
    st3 = json.loads(R.f["settings.json"])
    check("K33h een andere instelling wijzigen (de talen van Wim) laat de verplichte vrije dag staan: in settings.json en in de pagina", res == [True, True, ["2026-W44-WO"]] and "2026-10-28" in st3.get("verplichteDagen", {}) and sorted(st3.get("talen", {}).get("Wim", [])) == ["nl", "tr"], [res, st3])
    p.evaluate("currentIdentity = makeIdentity('Hans', 'MacBook', '')"); p.evaluate("() => { showVerplichtModal(); }"); p.wait_for_timeout(300)
    html = p.evaluate("document.querySelector('.vp-overlay').innerHTML"); lijst = p.evaluate("document.getElementById('vp-lijst').innerText")
    check("K33g het scherm Verplicht Vrij: een niet-Administrator krijgt het niet te zien; een Administrator ziet vaste en aangemaakte dagen met naam en wie, zonder ingevoegde HTML", geen == 0 and "<img" not in html and "Uitje" in lijst and "door Hans" in lijst and "Kerstavond" in lijst and "vast" in lijst, [geen, lijst[:300]])
    b.close()
    # K33i het onderdeel staat onder Admin (naast Accounts en Boodschap), niet onder Info; een klik opent het scherm
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0); klaar(p)
    p.evaluate("currentIdentity = makeIdentity('Hans', 'MacBook', ''); showLockIndicator(); editUnlocked = true; openWhoMenu();"); p.wait_for_timeout(500)
    voor_klik = p.evaluate("(() => { const x = document.getElementById('menu-verplicht'); return x ? [x.className, x.hidden, x.textContent] : null; })()")
    p.evaluate("document.getElementById('menu-admin').click()"); p.wait_for_timeout(200)
    na_klik = p.evaluate("(() => { const x = document.getElementById('menu-verplicht'), i = document.getElementById('menu-info'); const volgorde = [...document.querySelectorAll('#menu-admin ~ *')].map(e => e.id).filter(Boolean); return [x.hidden, volgorde.indexOf('menu-verplicht') > volgorde.indexOf('menu-backup-terugzetten'), volgorde.indexOf('menu-verplicht') < volgorde.indexOf('menu-info')]; })()")
    p.evaluate("document.getElementById('menu-verplicht').click()"); p.wait_for_timeout(800)
    open_ = p.evaluate("document.querySelectorAll('.vp-overlay').length")
    check("K33i 'Verplicht Vrij' staat in het menu Admin, onder Backup/Restore (verborgen tot Admin openklapt) en opent het scherm", voor_klik and "c-admin" in voor_klik[0] and voor_klik[1] is True and "Verplicht Vrij" in voor_klik[2] and na_klik[:2] == [False, True] and open_ == 1, [voor_klik, na_klik, open_])
    b.close()
    # K33j de oude stand komt terug: wie vóór het aanmaken iets (handmatig) had ingevuld krijgt dat terug, de rest de oorspronkelijke stand; wie intussen iets anders invulde blijft zoals hij is; in settings.json staat de stand voor de server
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0); klaar(p)
    p.evaluate("currentIdentity = makeIdentity('Hans', 'MacBook', ''); showLockIndicator(); editUnlocked = true; store['2026-W44'].Wim.WO = ['thuis']; manuallyEdited['2026-W44'] = new Set(['Wim-WO']); store['2026-W44'].Bas.WO = ['ziek']; (manuallyEdited['2026-W44'] || new Set()).add('Bas-WO');")
    p.evaluate("async () => { await settingsSetVerplicht('2026-10-28', 'Uitje'); }"); p.wait_for_timeout(500)
    rec = (json.loads(R.f["settings.json"]).get("verplichteDagen") or {}).get("2026-10-28", {}); vor = rec.get("vorige", {})
    midden = p.evaluate("TEAM.every(n => store['2026-W44'][n].WO[0] === 'vrij')")
    p.evaluate("store['2026-W44'].Sam.WO = ['thuis']")   # iemand vult intussen iets anders in op de nog verplichte dag is niet mogelijk; dit simuleert een stand die al afwijkt bij het verwijderen
    p.evaluate("async () => { await settingsSetVerplicht('2026-10-28', null); }"); p.wait_for_timeout(500)
    na = p.evaluate("(() => { const w = store['2026-W44']; return { wim: w.Wim.WO, bas: w.Bas.WO, hans: w.Hans.WO, sam: w.Sam.WO, mWim: manuallyEdited['2026-W44'].has('Wim-WO'), mBas: manuallyEdited['2026-W44'].has('Bas-WO'), mHans: manuallyEdited['2026-W44'].has('Hans-WO'), lock: LOCKED_DAYS.has('2026-W44-WO') }; })()")
    st = json.loads(R.f["settings.json"]); tm = (st.get("verplichtTerugzetten") or {}).get("2026-10-28", {})
    check("K33j bij het aanmaken wordt de stand per persoon vastgelegd (Wim thuis handmatig, Bas ziek handmatig, de rest kantoor); bij het verwijderen komt die stand terug in de pagina (ook de markering handmatig ingevuld), wie intussen iets anders had blijft zoals hij is, en settings.json bewaart de stand voor de server (verplichtTerugzetten) zonder de dag nog bij verplichteDagen", midden and vor.get("Wim") == {"s": ["thuis"], "m": True} and vor.get("Bas") == {"s": ["ziek"], "m": True} and vor.get("Hans") == {"s": ["kantoor"], "m": False} and na == {"wim": ["thuis"], "bas": ["ziek"], "hans": ["kantoor"], "sam": ["thuis"], "mWim": True, "mBas": True, "mHans": False, "lock": False} and "2026-10-28" not in (st.get("verplichteDagen") or {}) and tm.get("vorige", {}).get("Wim") == {"s": ["thuis"], "m": True} and tm.get("door") == "Hans", [midden, vor, na, st])
    # K33k opnieuw aanmaken na verwijderen haalt de wachtende terugzetting weg
    p.evaluate("async () => { await settingsSetVerplicht('2026-10-28', 'Opnieuw'); }"); p.wait_for_timeout(500)
    st = json.loads(R.f["settings.json"])
    check("K33k een dag die opnieuw wordt aangemaakt voordat de server de terugzetting deed, krijgt weer een nieuwe stand vastgelegd en de wachtende terugzetting verdwijnt uit settings.json", "verplichtTerugzetten" not in st and "2026-10-28" in st.get("verplichteDagen", {}) and st["verplichteDagen"]["2026-10-28"]["vorige"].get("Wim") == {"s": ["thuis"], "m": True}, st)
    b.close()
    # K34 roosters worden 14 dagen bewaard: na een synchronisatie gaan weken die GitHub niet meer heeft en meer dan 14 dagen voorbij zijn ook uit het geheugen van dit scherm; weken van de laatste 14 dagen blijven
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0); klaar(p)
    res = p.evaluate("""() => { const wk = k => JSON.parse(JSON.stringify(store['2026-W44'])); store['2026-W39'] = wk(); store['2026-W40'] = wk(); store['2026-W41'] = wk(); savePending = false; ghSaving = false; const voor = ['2026-W39', '2026-W40', '2026-W41'].map(w => w in store); ckLokaleOudeWekenWeg({ store: { '2026-W44': store['2026-W44'] } }); return [voor, ['2026-W39', '2026-W40', '2026-W41'].map(w => w in store), ckCutoff().toISOString().slice(0, 10)]; }""")
    check("K34 weken die GitHub niet meer heeft en meer dan 14 dagen voorbij zijn (W39 en W40, eindigt 4 oktober, vóór de grens van 5 oktober) gaan uit het geheugen; W41 (eindigt 11 oktober) blijft; de grens is 14 dagen terug", res[0] == [True, True, True] and res[1] == [False, False, True] and res[2] == "2026-10-05" or res[2] == "2026-10-04", res)
    b.close()
    # K35 reactietijd van GitHub: elk verzoek aan api.github.com wordt gemeten (lezen/schrijven, laatste 20), verzoeken naar andere adressen niet; het Checks-venster beoordeelt het (ok tot gemiddeld 2 s lezen en 4 s schrijven, let op daarboven, fout bij 3 van de laatste 10 mislukt)
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0); klaar(p)
    r1 = p.evaluate("""async () => { const lezen0 = GH_METING.lezen.length, schr0 = GH_METING.schrijven.length;
      await fetch('index.html?x=' + Date.now(), { cache: 'no-store' }).catch(() => {});   // niet GitHub: telt niet mee
      const na_pagina = [GH_METING.lezen.length, GH_METING.schrijven.length];
      await fetch('https://api.github.com/repos/buas-it/teamplanning-ict/contents/settings.json?ref=data', { headers: ckHdr() }).catch(() => {});
      await fetch('https://api.github.com/repos/buas-it/teamplanning-ict/contents/aanzet/meting.txt', { method: 'PUT', headers: ckHdr(), body: JSON.stringify({ message: 'meting', content: btoa('x'), branch: 'data' }) }).catch(() => {});
      return { start: [lezen0, schr0], na_pagina, nu: [GH_METING.lezen.length, GH_METING.schrijven.length], getal: GH_METING.lezen.concat(GH_METING.schrijven).every(x => typeof x === 'number' && x >= 0) }; }""")
    check("K35 verzoeken aan api.github.com worden gemeten (GET onder lezen, PUT onder schrijven, in milliseconden), een verzoek naar de pagina zelf niet; bij het laden zijn er al metingen", r1["start"][0] >= 1 and r1["na_pagina"] == r1["start"] and r1["nu"][0] == r1["start"][0] + 1 and r1["nu"][1] == r1["start"][1] + 1 and r1["getal"], r1)
    r2 = p.evaluate("""() => { const m = (l, s, u) => ({ lezen: l, schrijven: s, uitslag: u }); const o = x => x.s + ' | ' + x.t;
      return [ o(ckGhOordeel(m([300, 500], [900], [true, true, true]))), o(ckGhOordeel(m([2000], [4000], [true]))), o(ckGhOordeel(m([2600, 2000], [], [true, true]))), o(ckGhOordeel(m([100], [5000], [true, true]))), o(ckGhOordeel(m([100], [], [true, false, true, false, false, true]))), o(ckGhOordeel(m([], [], []))), o(ckGhOordeel(m([100], [], [false, false, true, true, true, true, true, true, true, true, true, true, true]))) ]; }""")
    check("K35b de beoordeling: ok (met gemiddelde, laatste, langzaamste en aantal); precies 2 s lezen en 4 s schrijven is nog ok; boven 2 s lezen of 4 s schrijven is let op; 3 mislukt van de laatste 10 is fout; geen metingen is info; oude mislukte verzoeken (buiten de laatste 10) tellen niet", r2[0].startswith("ok | lezen gemiddeld 400 ms (laatste 500, langzaamst 500, 2 metingen); schrijven gemiddeld 900 ms") and r2[1].startswith("ok |") and r2[2].startswith("let | lezen duurt gemiddeld langer dan 2 s") and r2[3].startswith("let | schrijven duurt gemiddeld langer dan 4 s") and r2[4].startswith("fout | 3 van de laatste 6 verzoeken aan GitHub mislukten") and r2[5] == "info | nog geen metingen" and r2[6].startswith("ok |"), r2)
    r3 = p.evaluate("""async () => { const c = CHECKS.find(x => x.id === 'ghtijd'); const r = await c.run(); return [c.groep, c.naam, r.s, r.t]; }""")
    check("K35c het onderdeel 'Reactietijd van GitHub (dit apparaat)' staat in het Checks-venster (groep Dit apparaat en dit scherm) en geeft de metingen van dit scherm", r3[0] == 4 and r3[1] == "Reactietijd van GitHub (dit apparaat)" and r3[2] in ("ok", "let") and "lezen gemiddeld" in r3[3], r3)
    b.close()
    # K36 wachtwoord wijzigen afdwingen voor wie het startwachtwoord gebruikt
    START = "StartWw-12345"
    OVERRIDE = "(() => { hashPassword = async pw => pw === '%s' ? PW_HASH : 'x' + pw.length; })()" % START   # in de test is het startwachtwoord bekend
    def inloggen(p, naam, ww):
        p.wait_for_selector("#pw-user option[value='%s']" % naam, state="attached", timeout=8000); p.select_option("#pw-user", naam); p.fill("#pw-input", ww); p.click("#pw-ok"); p.wait_for_timeout(2500)
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0)
    p.evaluate("localStorage.setItem('tp_unlocked', String(Date.now())); localStorage.setItem('tp_user', JSON.stringify({user: 'Wouter', workstation: 'Windows · Chrome', device: 'abc', id: 'Wouter@abc', info: ''}));"); p.reload(); p.wait_for_timeout(4500)
    r1 = p.evaluate("({ ident: currentIdentity && currentIdentity.user, poort: document.documentElement.classList.contains('tp-gated'), opgeslagen: localStorage.getItem('tp_user') })")
    recH = p.evaluate("async () => await newUserRecord('MijnEigenWw-2026')"); R.f["users.json"] = json.dumps({"v": 1, "users": {"Hans": recH}})
    p.evaluate("localStorage.setItem('tp_unlocked', String(Date.now())); localStorage.setItem('tp_user', JSON.stringify({user: 'Hans', workstation: 'Windows · Chrome', device: 'abc', id: 'Hans@abc', info: '', pw: true}));"); p.reload(); p.wait_for_timeout(4500)
    r2 = p.evaluate("({ ident: currentIdentity && currentIdentity.user, poort: document.documentElement.classList.contains('tp-gated') })")
    check("K36a een oude sessie zonder eigen wachtwoord (van vóór de persoonlijke wachtwoorden) wordt bij het openen van de pagina niet meer hersteld: de toegangspoort staat aan en de sessie is gewist; een sessie met eigen wachtwoord blijft gewoon geldig", r1["ident"] is None and r1["poort"] and r1["opgeslagen"] is None and r2["ident"] == "Hans" and not r2["poort"], json.dumps([r1, r2])); b.close()
    # K36b een bestaand record dat nog het startwachtwoord is: inloggen leidt naar 'Kies je eigen wachtwoord'; het startwachtwoord opnieuw kiezen mag niet; een ander wachtwoord vervangt het record en logt in
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0); p.evaluate(OVERRIDE)
    rec0 = p.evaluate("async () => await newUserRecord('%s')" % START); R.f["users.json"] = json.dumps({"v": 1, "users": {"Wouter": rec0}}); p.evaluate("usersLoad().catch(() => {})")
    inloggen(p, "Wouter", START)
    s1 = p.evaluate("({ stap2: !!document.getElementById('pw-new1'), ident: currentIdentity && currentIdentity.user, intro: (document.getElementById('pw2-intro') || {}).textContent })")
    if p.query_selector("#pw-new1"): p.fill("#pw-new1", START); p.fill("#pw-new2", START); p.click("#pw-ok"); p.wait_for_timeout(1500)
    s2 = p.evaluate("({ fout: (document.getElementById('pw-error') || {}).textContent || '', ident: currentIdentity && currentIdentity.user })"); u2 = json.loads(R.f["users.json"])["users"].get("Wouter", {})
    if p.query_selector("#pw-new1"): p.fill("#pw-new1", "EigenWachtwoord-99"); p.fill("#pw-new2", "EigenWachtwoord-99"); p.click("#pw-ok"); p.wait_for_timeout(3000)
    s3 = p.evaluate("({ ident: currentIdentity && currentIdentity.user, pw: currentIdentity && currentIdentity.pw, poort: document.documentElement.classList.contains('tp-gated') })"); u3 = json.loads(R.f["users.json"])["users"].get("Wouter", rec0)
    ok_nieuw = p.evaluate("async (h) => await verifyUserPw('EigenWachtwoord-99', h)", u3); ok_start = p.evaluate("async (h) => await verifyUserPw('%s', h)" % START, u3)
    check("K36b een record dat nog het startwachtwoord is: na inloggen moet er eerst een eigen wachtwoord worden gekozen (je bent nog niet binnen); het startwachtwoord opnieuw kiezen wordt geweigerd en laat het bestand ongemoeid; een ander wachtwoord vervangt het record en logt in, het startwachtwoord werkt daarna niet meer", s1["stap2"] and s1["ident"] is None and "eerst een eigen wachtwoord" in s1["intro"] and "ander wachtwoord dan het startwachtwoord" in s2["fout"] and s2["ident"] is None and u2["hash"] == rec0["hash"] and s3["ident"] == "Wouter" and s3["pw"] is True and not s3["poort"] and ok_nieuw and not ok_start, json.dumps([s1, s2, s3, ok_nieuw, ok_start])); b.close()
    # K36c een nieuwe gebruiker (nog geen record): startwachtwoord -> kiezen; het startwachtwoord als eigen wachtwoord kiezen mag niet; een eigen wachtwoord maakt een record en logt in
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0); p.evaluate(OVERRIDE)
    inloggen(p, "Wouter", START)
    t1 = p.evaluate("({ stap2: !!document.getElementById('pw-new1'), ident: currentIdentity && currentIdentity.user })")
    if p.query_selector("#pw-new1"): p.fill("#pw-new1", START); p.fill("#pw-new2", START); p.click("#pw-ok"); p.wait_for_timeout(1500)
    t2 = p.evaluate("({ fout: (document.getElementById('pw-error') || {}).textContent || '', ident: currentIdentity && currentIdentity.user })"); geen = "Wouter" not in json.loads(R.f["users.json"])["users"]
    if p.query_selector("#pw-new1"): p.fill("#pw-new1", "EigenWachtwoord-99"); p.fill("#pw-new2", "EigenWachtwoord-99"); p.click("#pw-ok"); p.wait_for_timeout(3000)
    t3 = p.evaluate("currentIdentity && currentIdentity.user"); heeft = "Wouter" in json.loads(R.f["users.json"])["users"]
    check("K36c een gebruiker zonder eigen wachtwoord komt met het startwachtwoord niet verder dan 'Kies je eigen wachtwoord'; het startwachtwoord als eigen wachtwoord wordt geweigerd (geen record aangemaakt); met een eigen wachtwoord ontstaat het record en ben je binnen", t1["stap2"] and t1["ident"] is None and "startwachtwoord" in t2["fout"] and t2["ident"] is None and geen and t3 == "Wouter" and heeft, json.dumps([t1, t2, geen, t3, heeft])); b.close()
    # K36d wie al een eigen wachtwoord heeft logt gewoon in (geen verplichte wijziging); een verkeerd wachtwoord wordt geweigerd; Wachtwoord wijzigen weigert het startwachtwoord als nieuw wachtwoord
    R = nieuw(planning()); b, p, fouten = open_pagina(pw, R, klok_extra=0); p.evaluate(OVERRIDE)
    rec1 = p.evaluate("async () => await newUserRecord('MijnEigenWw-2026')"); R.f["users.json"] = json.dumps({"v": 1, "users": {"Hans": rec1}})
    inloggen(p, "Hans", "fout-wachtwoord1"); d0 = p.evaluate("({ ident: currentIdentity && currentIdentity.user, stap2: !!document.getElementById('pw-new1') })")
    p.fill("#pw-input", "MijnEigenWw-2026"); p.click("#pw-ok"); p.wait_for_timeout(2500); d1 = p.evaluate("({ ident: currentIdentity && currentIdentity.user, stap2: !!document.getElementById('pw-new1') })")
    p.evaluate("showChangePassword()"); p.wait_for_selector("#cp-old", timeout=5000); p.fill("#cp-old", "MijnEigenWw-2026"); p.fill("#cp-new1", START); p.fill("#cp-new2", START); p.click("#cp-ok"); p.wait_for_timeout(1500)
    d2 = p.evaluate("(document.getElementById('cp-err') || {}).textContent || ''"); onveranderd = json.loads(R.f["users.json"])["users"]["Hans"]["hash"] == rec1["hash"]
    check("K36d een eigen wachtwoord logt gewoon in (zonder verplichte wijziging), een fout wachtwoord niet; 'Wachtwoord wijzigen' weigert het startwachtwoord als nieuw wachtwoord en laat het record ongemoeid", d0["ident"] is None and not d0["stap2"] and d1["ident"] == "Hans" and not d1["stap2"] and "startwachtwoord" in d2 and onveranderd, json.dumps([d0, d1, d2, onveranderd])); b.close()
    # K37 de vraag 'Bewerken aanzetten' komt pas als er echt iets wordt gewijzigd, niet bij alleen kijken
    VRAAG = "!!document.getElementById('edit-overlay')"
    def vraag(p): return p.evaluate(VRAAG)
    def beantwoord(p, ja):   # de vraag wegklikken: ja = Bewerken aanzetten, nee = sluiten
        p.wait_for_selector("#edit-overlay", timeout=3000); p.click("#ed-ok" if ja else "#ed-close"); p.wait_for_timeout(900)
    R = nieuw(planning()); R.f["settings.json"] = json.dumps({"v": 1, "talen": {"Wim": ["nl"]}, "verjaardagen": True})
    b, p, fouten = open_pagina(pw, R, klok_extra=0); klaar(p)
    p.evaluate(ADMIN + " editUnlocked = false; showLockIndicator();")
    kijk = {}
    for naam, js, sel in [("verplicht", "showVerplichtModal()", ".vp-overlay"), ("boodschap", "showBoodschapModal()", "#msg-overlay"), ("accounts", "showUsersModal()", "#usr-overlay"), ("periode", "showPeriodeModal()", "#pd-save"), ("standaard", "openStandaard('Wim')", "#tpl-modal"), ("restore", "showRestoreModal()", "#restore-list")]:
        p.evaluate("() => { " + js + "; }"); p.wait_for_timeout(1200)
        kijk[naam] = [vraag(p), p.evaluate("(s) => { const e = document.querySelector(s); return !!e && getComputedStyle(e).display !== 'none'; }", sel)]
        p.evaluate("document.querySelectorAll('.tp-overlay').forEach(o => { if(!o.dataset.gate) o.remove(); }); document.getElementById('tpl-modal').style.display = 'none'")
    check("K37a een Admin-scherm, Periode, Werkweek of de lijst met backups openen is alleen kijken: de pagina toont het scherm en vraagt niet om bewerken aan te zetten", all(v == [False, True] for v in kijk.values()), json.dumps(kijk))
    # K37b het menu: Admin en Backup/Restore uitklappen, en Accounts/Boodschap/Verplicht Vrij kiezen, zonder vraag
    p.evaluate("openWhoMenu()"); p.wait_for_timeout(400); p.evaluate("document.getElementById('menu-admin').click()"); p.wait_for_timeout(200); p.evaluate("document.getElementById('menu-backuprestore').click()"); p.wait_for_timeout(400)
    m1 = p.evaluate("({ vraag: " + VRAAG + ", menu: !!document.getElementById('who-menu'), maken: !document.getElementById('menu-backup-maken').hidden, terug: !document.getElementById('menu-backup-terugzetten').hidden, titel: document.getElementById('menu-accounts').title })")
    check("K37b het menu Admin en het tabblad Backup/Restore klappen open zonder vraag om bewerken aan te zetten (en zonder de tekst 'eerst volgt de vraag')", not m1["vraag"] and m1["menu"] and m1["maken"] and m1["terug"] and "vraag" not in m1["titel"], json.dumps(m1))
    p.evaluate("closeWhoMenu(true)")
    # K37c Verplicht Vrij: Aanmaken vraagt nu pas; Nee = er verandert niets; Ja = de dag wordt aangemaakt
    p.evaluate("() => { showVerplichtModal(); }"); p.wait_for_timeout(600)
    p.fill("#vp-datum", "2026-10-28"); p.fill("#vp-naam", "Bedrijfsuitje"); p.click("#vp-toevoegen"); p.wait_for_timeout(800)
    v1 = vraag(p); beantwoord(p, False)
    n1 = json.loads(R.f["settings.json"]).get("verplichteDagen"); u1 = p.evaluate("editUnlocked")
    p.click("#vp-toevoegen"); p.wait_for_timeout(800); beantwoord(p, True); p.wait_for_timeout(4500)
    n2 = json.loads(R.f["settings.json"]).get("verplichteDagen") or {}; u2 = p.evaluate("editUnlocked")
    check("K37c Verplicht Vrij: bij Aanmaken komt de vraag; sluiten = er wordt niets opgeslagen en bewerken blijft uit; Bewerken aanzetten = de dag wordt aangemaakt", v1 and not n1 and not u1 and "2026-10-28" in n2 and u2, json.dumps([v1, n1, u1, n2, u2]))
    # K37d staat bewerken al aan: geen vraag; gaat het uit terwijl het scherm openstaat, dan blijft het scherm open en volgt de vraag bij de volgende wijziging
    p.evaluate("disableEditing()"); p.wait_for_timeout(400)
    open_na = p.evaluate("document.querySelectorAll('.vp-overlay').length")
    p.evaluate("document.getElementById('vp-lijst').querySelector('.vp-del').click()"); p.wait_for_timeout(800); v3 = vraag(p); beantwoord(p, True); p.wait_for_timeout(3500)
    n3 = json.loads(R.f["settings.json"]).get("verplichteDagen") or {}
    p.evaluate("() => { showVerplichtModal(); }"); p.wait_for_timeout(500); p.fill("#vp-datum", "2026-10-29"); p.fill("#vp-naam", "Studiedag"); p.click("#vp-toevoegen"); p.wait_for_timeout(3500)
    v4 = vraag(p); n4 = json.loads(R.f["settings.json"]).get("verplichteDagen") or {}
    check("K37d gaat bewerken uit terwijl Verplicht Vrij openstaat, dan blijft het scherm open en volgt de vraag bij de volgende wijziging (Verwijderen); staat bewerken aan, dan wordt er niet nog eens gevraagd", open_na == 1 and v3 and not n3 and "2026-10-29" in n4 and not v4, json.dumps([open_na, v3, n3, v4, n4]))
    # K37e Boodschap: een vinkje wijzigen vraagt nu pas; Nee zet het vinkje terug en slaat niets op; Ja slaat het op
    p.evaluate("disableEditing(); document.querySelectorAll('.tp-overlay').forEach(o => { if(!o.dataset.gate) o.remove(); });"); p.evaluate("() => { showBoodschapModal(); }"); p.wait_for_timeout(1500)
    w0 = p.evaluate("document.getElementById('msg-verj').checked"); p.click("#msg-verj"); p.wait_for_timeout(800)
    e1 = vraag(p); beantwoord(p, False); w1 = p.evaluate("document.getElementById('msg-verj').checked"); s1 = json.loads(R.f["settings.json"]).get("verjaardagen")
    p.click("#msg-verj"); p.wait_for_timeout(800); beantwoord(p, True); p.wait_for_timeout(4000); s2 = json.loads(R.f["settings.json"]).get("verjaardagen")
    p.evaluate("disableEditing()"); p.wait_for_timeout(500); nog_open = p.evaluate("!!document.getElementById('msg-overlay')")
    check("K37e Boodschap: een vinkje wijzigen vraagt om bewerken aan te zetten; sluiten = het vinkje springt terug en er wordt niets opgeslagen; aanzetten = de wijziging wordt opgeslagen; zet bewerken daarna uit, dan blijft het scherm open (kijken kan altijd)", w0 is True and e1 and w1 is True and s1 is True and s2 is False and nog_open, json.dumps([w0, e1, w1, s1, s2, nog_open]))
    # K37f Accounts: een wachtwoord resetten vraagt nu pas (niet bij het openen of bij het kijken naar een account)
    rec = p.evaluate("async () => await newUserRecord('MijnEigenWw-2026')"); R.f["users.json"] = json.dumps({"v": 1, "users": {"Wim": rec}})
    p.evaluate("disableEditing(); document.querySelectorAll('.tp-overlay').forEach(o => { if(!o.dataset.gate) o.remove(); }); window.confirm = () => true;"); p.evaluate("() => { showUsersModal(); }"); p.wait_for_timeout(1500)
    a0 = vraag(p); p.evaluate("document.querySelector('.usr-naam[role=button]') && [...document.querySelectorAll('.usr-naam')].find(x => x.textContent.startsWith('Wim')).click()"); p.wait_for_timeout(1200); a1 = vraag(p)
    p.click("#usr-reset"); p.wait_for_timeout(900); a2 = vraag(p); beantwoord(p, False); rec_na_nee = "Wim" in json.loads(R.f["users.json"])["users"]
    check("K37f Accounts: openen en het account van een collega bekijken vraagt niets; Wachtwoord resetten vraagt om bewerken aan te zetten en doet bij sluiten niets", not a0 and not a1 and a2 and rec_na_nee, json.dumps([a0, a1, a2, rec_na_nee])); b.close()
print(f"\nklaar: {sum(1 for r in UIT if r.startswith('PASS'))} geslaagd, {sum(1 for r in UIT if r.startswith('FAIL'))} gefaald")
