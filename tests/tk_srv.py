"""Tests van het serveronderhoud (onderhoud.py) tegen een nagebootste GitHub-API. Gebruik: python3 tk_srv.py   (onderhoud.py moet in dezelfde map staan)"""
import base64, hashlib, importlib.util, json, os, re, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
HIER = os.path.dirname(os.path.abspath(__file__)); SCRIPT = os.path.join(HIER, "onderhoud.py")
os.environ.setdefault("ONDERHOUD_NU", "2026-11-04T08:00:00Z")
spec = importlib.util.spec_from_file_location("onderhoud", SCRIPT); OND = importlib.util.module_from_spec(spec); spec.loader.exec_module(OND)
UIT = []
def check(naam, ok, detail=""):
    UIT.append(("PASS  " if ok else "FAIL  ") + naam + ("" if ok else "   -> " + str(detail)[:700])); print(UIT[-1], flush=True)
class Repo:
    def __init__(self): self.reset()
    def reset(self): self.f = {}; self.puts = []; self.dels = []; self.hook = None; self.tamper = None; self.stuk = set(); self.na_toepassen_502 = set(); self.pages = None
    def sha(self, p): return hashlib.sha1(self.f[p].encode()).hexdigest()
    def dir(self, p): return sorted({k[len(p) + 1:].split("/")[0] for k in self.f if k.startswith(p + "/")})
REPO = Repo()
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, obj): b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _pad(self): m = re.match(r"^/repos/[^/]+/[^/]+/contents/(.*)$", urlparse(self.path).path); return m.group(1) if m else None
    def do_GET(self):
        if self.path.startswith("/pages/"):   # een nagebootste GitHub Pages-site
            if REPO.pages is None: return self._j(404, {})
            b = REPO.pages.encode(); self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        p = self._pad(); r = REPO
        if p is None: return self._j(404, {})
        if p in r.f:
            tekst = r.f[p]
            if r.tamper and p == "state.json" and r.tamper["na_put"] and r.tamper["n"] > 0:
                r.tamper["n"] -= 1; s = json.loads(tekst); [s["store"].pop(k) for k in sorted(s["store"])[-1:]]; tekst = json.dumps(s)
            return self._j(200, {"sha": r.sha(p), "content": base64.b64encode(tekst.encode()).decode(), "encoding": "base64", "name": p.split("/")[-1], "path": p})
        kinderen = r.dir(p)
        if kinderen: return self._j(200, [{"name": n, "path": p + "/" + n, "sha": r.sha(p + "/" + n), "type": "file"} for n in kinderen])
        return self._j(404, {"message": "Not Found"})
    def do_PUT(self):
        p = self._pad(); r = REPO; body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if any(p.startswith(s) for s in r.stuk): return self._j(500, {"message": "stuk"})
        if r.hook and p == "state.json": hk, r.hook = r.hook, None; hk()
        bestaat = p in r.f
        if bestaat and not body.get("sha"): return self._j(422, {"message": "sha wasn't supplied"})
        if bestaat and body["sha"] != r.sha(p): return self._j(409, {"message": "does not match"})
        r.f[p] = base64.b64decode(body["content"]).decode(); r.puts.append((p, body.get("message", "")))
        if r.tamper and p == "state.json": r.tamper["na_put"] = True
        if any(p.startswith(x) for x in r.na_toepassen_502):
            r.na_toepassen_502 = {x for x in r.na_toepassen_502 if not p.startswith(x)}; return self._j(502, {"message": "Server Error"})
        return self._j(201 if not bestaat else 200, {"content": {"sha": r.sha(p)}, "commit": {"sha": "c0ffee"}})
    def do_DELETE(self):
        p = self._pad(); r = REPO; body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if p not in r.f: return self._j(404, {})
        if body.get("sha") != r.sha(p): return self._j(409, {"message": "does not match"})
        del r.f[p]; r.dels.append(p); return self._j(200, {})
srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start(); PORT = srv.server_address[1]
def draai(droog=False, nu="2026-11-04T08:00:00Z", extra_env=None):
    env = dict(os.environ, GITHUB_API_URL=f"http://127.0.0.1:{PORT}", GITHUB_REPOSITORY="o/r", GITHUB_TOKEN="t", PAGES_URL=f"http://127.0.0.1:{PORT}/pages/", ONDERHOUD_NU=nu, ONDERHOUD_DROOG="1" if droog else "")
    if extra_env: env.update(extra_env)
    p = subprocess.run([sys.executable, SCRIPT], env=env, capture_output=True, text=True, timeout=150)
    try: uit = json.loads(p.stdout)
    except Exception: uit = {"acties": [], "problemen": ["geen uitvoer: " + p.stdout[-200:] + p.stderr[-300:]], "meldingen": []}
    return p.returncode, uit
TEAM = ["Wim", "Wouter", "Annies", "Bas", "Bram", "Marco", "Hans", "Sercan", "Ted", "Sam"]
def week(): return {p: {d: ["kantoor"] for d in OND.DAGEN} for p in TEAM}
def planning(van=20, tot=49, extra=None, stempel=True, n=4, t="2026-11-04T06:30:00.000Z"):
    s = {"team": list(TEAM), "store": {f"2026-W{i:02d}": week() for i in range(van, tot + 1)}, "template": {p: {d: ["kantoor"] for d in OND.DAGEN} for p in TEAM}, "manuallyEdited": {f"2026-W{i:02d}": ["Wim-MA"] for i in range(van, tot + 1) if i % 5 == 0}, "hidden": []}
    if extra: extra(s)
    if stempel:
        OND.stempel(s, {"integriteit": {"n": n - 1, "bev": 0}}); s["integriteit"]["t"] = t; s["integriteit"]["door"] = "Hans"
    return s
def nieuw(s, goede_backups=6):
    REPO.reset(); REPO.zet = None
    REPO.f["state.json"] = json.dumps(s); REPO.f["users.json"] = json.dumps({"v": 1, "users": {"Hans": {"salt": "x"}, "Bas": {"salt": "y"}}}); REPO.f["groups.json"] = json.dumps({"v": 1, "administrators": ["Hans", "Monitor"]})
    for i in range(goede_backups): REPO.f[f"backups/2026-10-1{i + 1}_09-00.json"] = json.dumps(s)
def st(): return json.loads(REPO.f["state.json"])
def backups(): return sorted(k for k in REPO.f if k.startswith("backups/"))
def nieuwe_backups(): return [b for b in backups() if not re.match(r"^backups/2026-10-1\d_09-00\.json$", b)]
def state_puts(): return [m for p, m in REPO.puts if p == "state.json"]
def audit_tekst(): return " ".join(v for k, v in REPO.f.items() if k.startswith("audit/"))
# ── SV1-3: gezond en statusbestand ────────────────────────────────────────────────────────────
nieuw(planning(36, 52)); rc, u = draai()
check("SV1 een gezonde planning (weken 36 t/m 52, kloppend controlegetal, backup gelijk aan de planning): de server wijzigt niets (geen schrijfactie op de planning, geen nieuwe backup), meldt geen problemen en schrijft alleen het statusbestand", rc == 0 and not state_puts() and len(backups()) == 6 and not u["problemen"] and not u["acties"] and "onderhoud.json" in REPO.f, json.dumps([rc, u, state_puts(), len(backups())]))
sj = json.loads(REPO.f["onderhoud.json"]); n_put = len(REPO.puts); rc, u = draai(nu="2026-11-04T08:20:00Z")
check("SV2 een tweede ronde 20 minuten later zonder nieuws legt geen nieuw statusbestand vast (geen overbodige commits); het statusbestand bevat tijdstip, acties, problemen, meldingen en droog", len(REPO.puts) == n_put and {"t", "acties", "problemen", "meldingen", "droog"} <= set(sj), json.dumps([len(REPO.puts) - n_put, sorted(sj)]))
n_put = len(REPO.puts); rc, u = draai(nu="2026-11-04T09:10:00Z")
check("SV3 na meer dan 55 minuten wordt het statusbestand wel ververst, zodat Info > Checks kan zien dat de server draait", len(REPO.puts) == n_put + 1 and json.loads(REPO.f["onderhoud.json"])["t"].startswith("2026-11-04T09:10"), json.dumps([len(REPO.puts) - n_put, json.loads(REPO.f["onderhoud.json"])["t"]]))
# ── SV4-9: oude weken ─────────────────────────────────────────────────────────────────────────
nieuw(planning(20, 49)); rc, u = draai(); s = st()
check("SV4 weken ouder dan 2 maanden (de server staat op 4 november: t/m week 35) worden verwijderd, per ronde hooguit 40% (12 van de 30: 2026-W20 t/m W31); de recente weken en het team blijven ongemoeid; de Action eindigt zonder fout", rc == 0 and sorted(s["store"]) == [f"2026-W{i:02d}" for i in range(32, 50)] and s["team"] == TEAM and any("12 weken ouder dan 2 maanden" in a for a in u["acties"]), json.dumps([rc, sorted(s["store"])[:2], len(s["store"]), u["acties"]]))
check("SV5 de planning heeft daarna een nieuw kloppend controlegetal (volgnummer 4 naar 5, door 'Server (onderhoud)') en de handmatige markeringen van de verwijderde weken zijn ook weg", OND.stempel_status(s) == "ok" and s["integriteit"]["n"] == 5 and s["integriteit"]["door"].startswith("Server") and all(w >= "2026-W32" for w in s["manuallyEdited"]), json.dumps([s["integriteit"], sorted(s["manuallyEdited"])]))
na = nieuwe_backups()
check("SV6 er zijn twee nieuwe backups: een van de planning van voor het onderhoud (30 weken) en een van erna (18 weken); de namen volgen het patroon van de pagina (JJJJ-MM-DD_UU-MM)", len(na) == 2 and sorted(len(json.loads(REPO.f[b])["store"]) for b in na) == [18, 30] and all(re.match(r"^backups/\d{4}-\d\d-\d\d_\d\d-\d\d\.json$", b) for b in na), json.dumps([na]))
check("SV7 het logboek bevat wat de server deed (gebruiker 'Server') en het statusbestand noemt dat er nog 4 oude weken in de volgende ronde volgen", "onderhoud: 12 weken ouder dan 2 maanden" in audit_tekst() and '"user": "Server"' in audit_tekst() and any("nog 4 oude weken" in m for m in json.loads(REPO.f["onderhoud.json"])["meldingen"]), json.dumps([audit_tekst()[:160], json.loads(REPO.f["onderhoud.json"])["meldingen"]]))
rc, u = draai(nu="2026-11-04T08:40:00Z"); s = st()
check("SV8 de volgende ronde ruimt de laatste 4 oude weken op (W32 t/m W35); daarna begint de planning bij week 36 met 14 weken", sorted(s["store"])[0] == "2026-W36" and len(s["store"]) == 14, json.dumps([sorted(s["store"])[:2], len(s["store"])]))
n_p = len(state_puts()); rc, u = draai(nu="2026-11-04T09:00:00Z")
check("SV9 een ronde zonder oude weken schrijft niets meer naar de planning", len(state_puts()) == n_p and rc == 0, json.dumps([len(state_puts()) - n_p, u]))
# ── SV10-11: schoonmaken ──────────────────────────────────────────────────────────────────────
def vuil(s):
    s["team"] += ["Dave", "Ivor"]; s["hidden"] = ["Frederique"]
    for w in s["store"].values(): w["Dave"] = {d: ["kantoor"] for d in OND.DAGEN}; w["Zed"] = {d: ["kantoor"] for d in OND.DAGEN}
    s["template"]["Ivor"] = {d: ["kantoor"] for d in OND.DAGEN}; s["template"]["Zed"] = {d: ["kantoor"] for d in OND.DAGEN}
    s["store"]["2026-W40"]["Wim"]["MA"] = ["kantoor", "deel"]; s["store"]["2026-W41"]["Bas"]["DI"] = ["deel"]
    s["manuallyEdited"]["2026-W40"] = ["Wim-MA", "Niemand-MA", "Wim-ZO", "Dave-MA"]; s["manuallyEdited"]["2026-W99"] = ["Wim-MA"]
nieuw(planning(36, 52, extra=vuil)); [REPO.f.__setitem__(b, json.dumps(planning(36, 52))) for b in backups()]; REPO.f["users.json"] = json.dumps({"v": 1, "users": {"Hans": {}, "Dave": {}, "Ivor": {}, "Bas": {}, "Zoveel": {}}}); rc, u = draai(); s = st()
check("SV10 de verwijderde namen (Frederique, Ivor, Dave) gaan uit team, verborgen, werkweek, planning en markeringen; planning van een niet-teamlid (Zed) gaat eruit; de onbekende status 'deel' naast een geldige gaat eruit; verweesde markeringen (onbekende persoon, dag of week) gaan eruit", rc == 0 and not any(n in json.dumps(s) for n in ("Frederique", "Ivor", "Dave", "Zed", "Niemand", "W99", "Wim-ZO")) and s["team"] == TEAM and s["store"]["2026-W40"]["Wim"]["MA"] == ["kantoor"] and OND.stempel_status(s) == "ok", json.dumps([rc, u["acties"], s["team"]]))
check("SV11 een cel die alleen uit een onbekende status bestaat wordt niet aangeraakt maar gemeld; het account van een verwijderde naam (Dave, Ivor) is uit users.json, andere accounts blijven, een account buiten het team wordt gemeld", s["store"]["2026-W41"]["Bas"]["DI"] == ["deel"] and any("alleen uit een onbekende status" in m for m in u["meldingen"]) and sorted(json.loads(REPO.f["users.json"])["users"]) == ["Bas", "Hans", "Zoveel"] and any("Zoveel" in m for m in u["meldingen"]), json.dumps([u["meldingen"], sorted(json.loads(REPO.f["users.json"])["users"])]))
# ── SV12-14: controlegetal en onleesbaar ──────────────────────────────────────────────────────
sj = planning(20, 49); OND.stempel(sj, {"integriteit": {"n": 3, "bev": 0}}); sj["store"]["2026-W40"]["Wim"]["MA"] = ["vrij"]; nieuw(sj); voor = REPO.f["state.json"]; rc, u = draai()
check("SV12 klopt het controlegetal van de planning niet (iemand of iets heeft de planning gewijzigd zonder het bij te werken), dan schrijft de server niets (planning, backups en accounts blijven gelijk), meldt een probleem en de Action eindigt met een fout zodat GitHub een melding stuurt", rc == 1 and REPO.f["state.json"] == voor and not state_puts() and len(backups()) == 6 and any("controlegetal" in p for p in u["problemen"]), json.dumps([rc, u["problemen"], state_puts()]))
nieuw(planning(20, 49)); REPO.f["state.json"] = "{niet af"; rc, u = draai()
check("SV13 is de planning onleesbaar, dan wijzigt de server niets en meldt het", rc == 1 and REPO.f["state.json"] == "{niet af" and any("onleesbaar" in p for p in u["problemen"]), json.dumps([rc, u["problemen"]]))
nieuw(planning(36, 52, stempel=False)); rc, u = draai(); s = st()
check("SV14 een planning zonder controlegetal krijgt er een van de server (volgnummer 1) met een backup vooraf; de planning zelf verandert niet", rc == 0 and s["integriteit"]["n"] == 1 and OND.stempel_status(s) == "ok" and s["store"] == planning(36, 52, stempel=False)["store"] and len(backups()) >= 7, json.dumps([rc, s.get("integriteit"), u["acties"]]))
# ── SV15-16: beschadigde backups ──────────────────────────────────────────────────────────────
def met_namen(s): s["team"] = s["team"] + ["Dave"]
nieuw(planning(36, 52)); REPO.f["backups/2026-10-18_09-00.json"] = json.dumps(planning(36, 52, extra=met_namen)); rc, u = draai()
check("SV15 een beschadigde backup (met een verwijderde naam) tussen de nieuwste drie wordt verwijderd als er nog minstens 5 goede overblijven; alle overgebleven backups zijn in orde", rc == 0 and "backups/2026-10-18_09-00.json" not in REPO.f and len(backups()) >= 6 and all(OND.backup_oordeel(REPO.f[b], 17) is None for b in backups()), json.dumps([rc, u, backups()[-2:]]))
nieuw(planning(36, 52), goede_backups=2); REPO.f["backups/2026-10-18_09-00.json"] = json.dumps(planning(36, 52, extra=met_namen)); rc, u = draai()
check("SV16 zijn er te weinig goede backups (minder dan 5), dan verwijdert de server niets maar meldt het probleem", rc == 1 and "backups/2026-10-18_09-00.json" in REPO.f and any("beschadigde backup" in p for p in u["problemen"]), json.dumps([rc, u["problemen"]]))
# ── SV17: gelijktijdig schrijven ──────────────────────────────────────────────────────────────
def browser():
    s = json.loads(REPO.f["state.json"]); s["store"]["2026-W45"]["Wim"]["MA"] = ["vrij"]; s["manuallyEdited"].setdefault("2026-W45", []).append("Wim-MA"); OND.stempel(s, s); REPO.f["state.json"] = json.dumps(s)
nieuw(planning(20, 49)); REPO.hook = browser; rc, u = draai(); s = st()
check("SV17 schrijft een browser tegelijk een wijziging (409 op de planning), dan overschrijft de server die nooit: hij begint opnieuw op de nieuwste planning; de wijziging van de collega staat er daarna nog in en de oude weken zijn alsnog verwijderd", rc == 0 and s["store"]["2026-W45"]["Wim"]["MA"] == ["vrij"] and sorted(s["store"])[0] == "2026-W32" and OND.stempel_status(s) == "ok", json.dumps([rc, u, s["store"]["2026-W45"]["Wim"]["MA"], sorted(s["store"])[:1]]))
# ── SV18: droogloop ───────────────────────────────────────────────────────────────────────────
nieuw(planning(20, 49)); voor = dict(REPO.f); rc, u = draai(droog=True)
check("SV18 in een droogloop (ONDERHOUD_DROOG=1) wijzigt de server niets: planning, backups, accounts en logboek blijven gelijk; alleen het statusbestand wordt geschreven, met 'droog: true' en wat er zou gebeuren", rc == 0 and REPO.f["state.json"] == voor["state.json"] and backups() == sorted(k for k in voor if k.startswith("backups/")) and not any(k.startswith("audit/") for k in REPO.f) and json.loads(REPO.f["onderhoud.json"])["droog"] is True and any("ouder dan 2 maanden" in a for a in u["acties"]), json.dumps([rc, u["acties"]]))
# ── SV19-23: de grenzen ───────────────────────────────────────────────────────────────────────
nieuw(planning(20, 26)); rc, u = draai(); n7 = len(st()["store"])
check("SV19 zijn er maar 7 weken en zijn die allemaal ouder dan 2 maanden, dan verwijdert de server niets: er blijven altijd minstens 8 weken over", n7 == 7 and not state_puts(), json.dumps([n7, state_puts()]))
nieuw(planning(20, 29)); rc, u = draai(); n10 = len(st()["store"])
check("SV20 bij 10 weken (allemaal oud) mogen er hooguit 2 weg: er blijven er 8", n10 == 8, str(n10))
nieuw(planning(36, 52)); rc, u = draai()
check("SV21 zijn er geen weken ouder dan 2 maanden, dan blijft de planning ongewijzigd (17 weken)", len(st()["store"]) == 17 and not state_puts(), str(len(st()["store"])))
nieuw(planning(33, 52)); rc, u = draai(nu="2026-11-04T08:00:00Z")
check("SV22 de grens ligt op precies 2 maanden: week 35 (eindigt 30 augustus) is te oud, week 36 (eindigt 6 september) nog niet", sorted(st()["store"])[0] == "2026-W36" and len(st()["store"]) == 17, json.dumps(sorted(st()["store"])[:2]))
nieuw(planning(33, 52)); rc, u = draai(nu="2026-09-06T23:00:00Z")
check("SV23 de grens volgt de datum van de server (hier 6 september): niets in week 33 t/m 52 is te oud, de planning blijft intact", len(st()["store"]) == 20, str(len(st()["store"])))
# ── SV24-26: fouten ───────────────────────────────────────────────────────────────────────────
nieuw(planning(20, 49)); REPO.stuk = {"backups/"}; voor = REPO.f["state.json"]; rc, u = draai()
check("SV24 lukt de backup vooraf niet, dan wijzigt de server de planning niet en meldt het probleem (Action rood)", rc == 1 and REPO.f["state.json"] == voor and any("backup vooraf is niet gelukt" in p for p in u["problemen"]), json.dumps([rc, u["problemen"]]))
nieuw(planning(20, 49)); voor = REPO.f["state.json"]; REPO.tamper = {"na_put": False, "n": 1}; rc, u = draai()
check("SV25 klopt de teruglezing na het schrijven niet (hier: een week ontbreekt), dan zet de server de planning automatisch terug naar de stand van voor het onderhoud en meldt het probleem (Action rood)", rc == 1 and json.loads(REPO.f["state.json"]) == json.loads(voor) and any("controle na opslaan mislukt" in p for p in u["problemen"]), json.dumps([rc, u["problemen"]]))
nieuw(planning(20, 49)); REPO.f["state.json"] = json.dumps({"team": [], "store": {}, "template": {}, "manuallyEdited": {}, "hidden": []}); rc, u = draai()
check("SV26 is de planning leeg of ongeldig (geen team), dan wijzigt de server niets", rc == 1 and not state_puts(), json.dumps([rc, u["problemen"]]))
# ── SV27-30: schakelaar en alleen-lezen ───────────────────────────────────────────────────────
nieuw(planning(20, 49)); REPO.f["onderhoud-config.json"] = json.dumps({"droog": True}); voor = REPO.f["state.json"]; rc, u = draai()
check("SV27 staat in onderhoud-config.json {\"droog\": true}, dan kijkt de server alleen: de planning blijft gelijk, er komen geen backups bij; het statusbestand zegt 'droog: true' en wat er zou gebeuren", rc == 0 and REPO.f["state.json"] == voor and len(backups()) == 6 and json.loads(REPO.f["onderhoud.json"])["droog"] is True and any("ouder dan 2 maanden" in a for a in u["acties"]), json.dumps([rc, u["acties"]]))
nieuw(planning(20, 49)); REPO.f["onderhoud-config.json"] = "{kapot"; voor = REPO.f["state.json"]; rc, u = draai()
check("SV28 is onderhoud-config.json onleesbaar, dan wijzigt de server voor de zekerheid niets en meldt dat", rc == 0 and REPO.f["state.json"] == voor and any("onleesbaar" in m for m in u["meldingen"]), json.dumps([rc, u["meldingen"]]))
nieuw(planning(20, 49)); REPO.f["onderhoud-config.json"] = json.dumps({"droog": False}); rc, u = draai()
check("SV29 staat in onderhoud-config.json {\"droog\": false} (of ontbreekt het bestand), dan wordt er gewoon onderhouden", rc == 0 and len(st()["store"]) == 18, str(len(st()["store"])))
nieuw(planning(20, 49)); voor = dict(REPO.f); rc, u = draai(extra_env={"ONDERHOUD_ALLEEN_LEZEN": "1"})
check("SV30 in de alleen-lezen-stand (ONDERHOUD_ALLEEN_LEZEN=1) schrijft de server helemaal niets: geen planning, geen backups, geen logboek en ook geen statusbestand; wel de lijst van wat hij zou doen", rc == 0 and REPO.f == voor and not REPO.puts and any("ouder dan 2 maanden" in a for a in u["acties"]), json.dumps([rc, REPO.puts[:2], u["acties"]]))
# ── SV31: tijdelijke fout van GitHub (verwerkt, maar 502 teruggegeven) ────────────────────────
nieuw(planning(20, 49)); REPO.na_toepassen_502 = {"backups/", "state.json"}; rc, u = draai(); s = st()
check("SV31 geeft GitHub bij een schrijfactie een tijdelijke fout (502) terwijl die wel is verwerkt, dan herkent de server dat de gewenste inhoud er al staat: geen valse mislukking, geen dubbele schrijfactie, en het onderhoud verloopt normaal (backup vooraf en achteraf, 12 weken verwijderd, geen problemen)", rc == 0 and not u["problemen"] and not any("niet gelukt" in m for m in u["meldingen"]) and len(s["store"]) == 18 and OND.stempel_status(s) == "ok" and len(nieuwe_backups()) == 2, json.dumps([rc, u, len(s["store"])]))
# ── SV32-34: de status onthoudt welke planning de server het laatst zag ────────────────────────
nieuw(planning(36, 52)); rc, u = draai(nu="2026-11-04T08:00:00Z"); s1 = json.loads(REPO.f["onderhoud.json"])
def browser2():
    s = json.loads(REPO.f["state.json"]); s["store"]["2026-W45"]["Wim"]["MA"] = ["vrij"]; s["manuallyEdited"].setdefault("2026-W45", []).append("Wim-MA"); OND.stempel(s, s); REPO.f["state.json"] = json.dumps(s)
browser2(); sha_na = REPO.sha("state.json"); rc, u = draai(nu="2026-11-04T08:10:00Z"); s2 = json.loads(REPO.f["onderhoud.json"])
check("SV32 het statusbestand bevat de versie van de planning die de server het laatst zag (state_sha); na een wijziging door een browser krijgt de eerstvolgende ronde een nieuwe status, ook binnen het uur", s1["state_sha"] != s2["state_sha"] and s2["state_sha"] == sha_na and s2["t"].startswith("2026-11-04T08:10"), json.dumps([s1.get("state_sha", "")[:8], s2.get("state_sha", "")[:8], sha_na[:8], s2["t"]]))
n_p = len(REPO.puts); rc, u = draai(nu="2026-11-04T08:20:00Z")
check("SV33 een ronde zonder wijziging van de planning, binnen het uur, schrijft geen nieuwe status (geen overbodige commits)", len(REPO.puts) == n_p, str(len(REPO.puts) - n_p))
nieuw(planning(20, 49)); rc, u = draai(); sj = json.loads(REPO.f["onderhoud.json"])
check("SV34 na een wijziging door de server zelf (oude weken verwijderd) wijst state_sha naar de planning zoals de server hem heeft achtergelaten", sj["state_sha"] == REPO.sha("state.json"), json.dumps([sj["state_sha"][:8], REPO.sha("state.json")[:8]]))

# ── SV35-45: de controles die de server zelf doet (het Checks-venster toont deze uitslag) ──────────────────
def checks(): return {c["id"]: c for c in json.loads(REPO.f["onderhoud.json"])["checks"]}
LABEL_A = '<span id="app-version">versie 4 nov 2026 · 146</span>'; LABEL_B = '<span id="app-version">versie 4 nov 2026 · 147</span>'
def basis(s=None, groepen=None):
    nieuw(s or planning(36, 52)); REPO.f["index.html"] = LABEL_A; REPO.pages = LABEL_A
    if groepen is not None: REPO.f["groups.json"] = json.dumps({"v": 1, "administrators": groepen})
nu_id = ["github", "uitrol", "stempel", "weken", "namen", "team", "vreemd", "statussen", "manueel", "halvedag", "oudeweken", "grootte", "groups", "accounts", "wachtwoorden", "instellingen", "serveronderhoud", "backups", "backup_actueel", "backup_geldig", "logboek"]
basis(); rc, u = draai(); c = checks()
check("SV35 de server doet 21 controles in vier groepen en legt de uitslag vast in het statusbestand; bij een gezonde planning is er geen enkele fout en zijn de uitslagen: alles in orde, behalve dat er maar een Administrator is (let op) en wie nog het startwachtwoord heeft (info)", rc == 0 and sorted(c) == sorted(nu_id) and {x["s"] for x in c.values()} <= {"ok", "info", "let"} and c["groups"]["s"] == "let" and "maar één Administrator" in c["groups"]["t"] and c["wachtwoorden"]["s"] == "info" and c["accounts"]["t"] == "2 accounts: 2 van de 10 teamleden hebben een eigen wachtwoord" and all(c[k]["s"] == "ok" for k in ("github", "uitrol", "stempel", "weken", "namen", "team", "vreemd", "statussen", "manueel", "halvedag", "oudeweken", "grootte", "instellingen", "serveronderhoud", "backups", "backup_actueel", "backup_geldig", "logboek")) and {x["groep"] for x in c.values()} == {0, 1, 2, 3}, json.dumps({k: (v["s"], v["t"][:50]) for k, v in c.items() if v["s"] != "ok"}))
for pages, hoofd, verwacht, zoek in ((LABEL_A, LABEL_A, "ok", "dezelfde versie"), (LABEL_A, LABEL_B, "let", "loopt achter"), (None, LABEL_A, "info", "niet te bereiken"), (LABEL_A, "geen label", "info", "niet te lezen")):
    basis(); REPO.f["index.html"] = hoofd; REPO.pages = pages; rc, u = draai(); r = checks()["uitrol"]
    check(f"SV36{verwacht[0]} de check 'Uitrol van de pagina' vergelijkt de versie op de site met die op main: {zoek} ({verwacht})", r["s"] == verwacht and zoek in r["t"], json.dumps(r))
# statussen, halve dagen, weken, team, grootte
def rommel(s): s["store"]["2026-W41"]["Bas"]["DI"] = ["deel"]; s["store"]["2026-W46"]["Wim"]["DI"] = ["vm_vrij"]; s["manuallyEdited"].setdefault("2026-W46", []).append("Wim-DI"); s["store"]["2026-W37"]["Sam"]["MA"] = ["nm_vrij"]; s["manuallyEdited"].setdefault("2026-W37", []).append("Sam-MA")
basis(planning(36, 52, extra=rommel)); rc, u = draai(); c = checks()
check("SV37 een cel die alleen uit een onbekende status bestaat wordt gemeld (let op); een halve dag vrij zonder invulling in de toekomst (Wim, week 46) wordt gemeld met de naam, een in het verleden (Sam, week 37) niet", c["statussen"]["s"] == "let" and "alleen uit een onbekende status" in c["statussen"]["t"] and c["halvedag"]["s"] == "let" and "Wim (1)" in c["halvedag"]["t"] and "Sam" not in c["halvedag"]["t"], json.dumps([c["statussen"], c["halvedag"]]))
def geenwerkweek(s): del s["template"]["Ted"]
basis(planning(36, 52, extra=geenwerkweek)); rc, u = draai(); c = checks()
check("SV38 een teamlid zonder werkweek is een fout in de check 'Team en werkweken'; omdat het een nieuwe fout is wordt de Action rood (exitcode 1) en staat het in de problemen", c["team"]["s"] == "fout" and "Ted" in c["team"]["t"] and rc == 1 and any("Team en werkweken" in p for p in u["problemen"]), json.dumps([rc, c["team"], u["problemen"]]))
rc, u = draai(nu="2026-11-04T08:10:00Z")
check("SV39 blijft dezelfde fout bestaan, dan wordt de Action niet bij elke ronde opnieuw rood (geen mail bij elke ronde): de fout staat nog wel in de uitslag", checks()["team"]["s"] == "fout" and rc == 0, json.dumps([rc, u["problemen"]]))
basis(); REPO.f["backups/2026-10-11_09-00.json"] = json.dumps(planning(20, 60)); [REPO.f.__setitem__(f"backups/2026-10-1{i}_09-00.json", json.dumps(planning(20, 60))) for i in range(1, 7)]; basis_s = planning(36, 45); REPO.f["state.json"] = json.dumps(basis_s); rc, u = draai(); c = checks()
check("SV40 heeft de planning opeens veel minder weken dan de nieuwste backup (10 tegen 41), dan is dat een fout in de check 'Aantal weken' (mogelijk beschadigd)", c["weken"]["s"] == "fout" and "opeens veel minder weken" in c["weken"]["t"], json.dumps(c["weken"]))
def groot(jaren):
    def f(s):
        w = s["store"]["2026-W43"] if "2026-W43" in s["store"] else next(iter(s["store"].values()))
        for j in range(2030, 2030 + jaren):
            for i in range(1, 53): s["store"][f"{j}-W{i:02d}"] = json.loads(json.dumps(w))
    return f
basis(planning(36, 52, extra=groot(14))); rc, u = draai(); g1 = checks()["grootte"]
basis(planning(36, 52, extra=groot(17))); rc, u = draai(); g2 = checks()["grootte"]
check("SV41 de grootte van de planning: een aandachtspunt boven 700 KB en een fout boven 900 KB (dan kan GitHub het bestand niet meer uitleveren)", g1["s"] in ("let", "fout") and g2["s"] == "fout" and ("let" if g1["s"] == "let" else "fout") and "KB" in g1["t"], json.dumps([g1, g2]))
# Administrators, accounts, instellingen
for adm, verwacht, zoek in (([ "Hans", "Marco", "Monitor"], "ok", "2 Administrators"), (["Monitor"], "fout", "geen enkele"), (["Hans", "Marco", "Dave", "Monitor"], "let", "niet in het team"), (["Hans", "Marco"], "let", "Monitor-account")):
    basis(groepen=adm); rc, u = draai(); r = checks()["groups"]
    check(f"SV42{verwacht[0]} de check 'Administrators' meldt {adm}: {zoek} ({verwacht})", r["s"] == verwacht and zoek in r["t"], json.dumps(r))
basis(); REPO.f["users.json"] = json.dumps({"v": 1, "users": {p: {} for p in ["Bas", "Bram", "Hans", "Marco", "Sam", "Sercan", "Monitor"]}}); rc, u = draai(); c = checks()
check("SV43 de check 'Accounts' zegt precies hoeveel teamleden een eigen wachtwoord hebben ('7 accounts: 6 van de 10 teamleden hebben een eigen wachtwoord, plus het Monitor-account') en 'Eigen wachtwoorden' noemt wie nog het startwachtwoord gebruikt", c["accounts"]["t"] == "7 accounts: 6 van de 10 teamleden hebben een eigen wachtwoord, plus het Monitor-account" and c["wachtwoorden"]["s"] == "info" and all(n in c["wachtwoorden"]["t"] for n in ("Wim", "Wouter", "Annies", "Ted")), json.dumps([c["accounts"], c["wachtwoorden"]]))
basis(); REPO.f["settings.json"] = json.dumps({"v": 1, "talen": {"Dave": ["nl"], "Wim": ["nl"]}, "personen": {}}); rc, u = draai()
check("SV44 instellingen (boodschap, talen) van een verwijderde naam worden gemeld (let op)", checks()["instellingen"]["s"] == "let" and "Dave" in checks()["instellingen"]["t"], json.dumps(checks()["instellingen"]))
# backups en logboek
basis(); [REPO.f.pop(b) for b in backups()]; rc, u = draai(droog=True); c = checks()
check("SV45 zijn er helemaal geen backups, dan is dat een fout; zijn het er meer dan 80, dan een aandachtspunt", c["backups"]["s"] == "fout" and c["backup_actueel"] if False else c["backups"]["s"] == "fout", json.dumps(c["backups"]))
basis()
for i in range(1, 85): REPO.f[f"backups/2026-09-{(i % 28) + 1:02d}_{i // 28:02d}-00.json"] = json.dumps(planning(36, 52))
rc, u = draai(droog=True); check("SV46 meer dan 80 backups is een aandachtspunt", checks()["backups"]["s"] == "let" and "veel" in checks()["backups"]["t"], json.dumps(checks()["backups"]))
basis(planning(36, 52, t="2026-11-04T05:00:00.000Z")); REPO.f["backups/2026-10-18_09-00.json"] = json.dumps(planning(36, 52, extra=lambda s: s["store"]["2026-W40"]["Wim"]["MA"].__setitem__(0, "vrij"))); rc, u = draai(droog=True)
check("SV47 verschilt de nieuwste backup van de planning en is de laatste opslag al ruim een half uur oud, dan is dat een aandachtspunt in 'Laatste backup bevat de laatste opslag' (in een droogloop maakt de server geen backup bij)", checks()["backup_actueel"]["s"] == "let", json.dumps(checks()["backup_actueel"]))
for inhoud, verwacht, zoek in ((None, "ok", "nog geen regels"), ('{"a":1}\n{"b":2}\n', "ok", "allemaal leesbaar"), ('{"a":1}\n{kapot\n{"b":2}\n', "let", "1 van de 3")):
    basis()
    if inhoud is not None: REPO.f["audit/2026-11-04.jsonl"] = inhoud
    rc, u = draai(droog=True); r = checks()["logboek"]
    check(f"SV48{verwacht[0]} de check 'Logboek van vandaag is leesbaar' meldt: {zoek} ({verwacht})", r["s"] == verwacht and zoek in r["t"], json.dumps(r))
# het statusbestand verandert alleen als een controle verandert
basis(); rc, u = draai(nu="2026-11-04T08:00:00Z"); n_p = len(REPO.puts); rc, u = draai(nu="2026-11-04T08:10:00Z"); n_gelijk = len(REPO.puts) - n_p
REPO.pages = LABEL_B; REPO.f["index.html"] = LABEL_A; n_p = len(REPO.puts); rc, u = draai(nu="2026-11-04T08:20:00Z"); n_wijz = len(REPO.puts) - n_p
check("SV49 het statusbestand wordt niet opnieuw geschreven zolang alle controles gelijk blijven, maar wel zodra er een verandert (hier: de site loopt achter op main), ook binnen het uur", n_gelijk == 0 and n_wijz == 1 and checks()["uitrol"]["s"] == "let", json.dumps([n_gelijk, n_wijz, checks()["uitrol"]["s"]]))


basis(); [REPO.f.__setitem__(f"backups/2026-10-1{i}_09-00.json", json.dumps(planning(20, 60))) for i in range(1, 7)]; REPO.f["state.json"] = json.dumps(planning(36, 45)); n_b0 = len(backups()); rc, u = draai()
check("SV50 ziet de planning er beschadigd uit (opeens veel minder weken dan de backups), dan maakt de server er geen backup van bij en meldt hij een probleem (Action rood)", len(backups()) == n_b0 and rc == 1 and any("geen backup bijgemaakt" in p for p in u["problemen"]), json.dumps([rc, u["problemen"], len(backups()) - n_b0]))

print(f"\nklaar: {sum(1 for r in UIT if r.startswith('PASS'))} geslaagd, {sum(1 for r in UIT if r.startswith('FAIL'))} gefaald")
