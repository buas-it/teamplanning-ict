#!/usr/bin/env python3
"""Serveronderhoud van Bezetting Teams.

Draait als GitHub Action (niet in een browser, niet bij een ingelogde Administrator) en voert de acties uit die gegevens wijzigen:
- verwijderde namen, planning van niet-teamleden, onbekende statussen en verweesde markeringen uit de planning halen;
- weken die helemaal ouder zijn dan 2 maanden verwijderen (eerst een backup; hooguit 40% per ronde; er blijven altijd minstens 8 weken);
- een controlegetal vastleggen, backups bijhouden en beschadigde backups opruimen, accounts van verwijderde namen weghalen;
- alles in het logboek zetten en een statusbestand (onderhoud.json) schrijven, waar Info > Checks de gezondheid van deze taak uit afleest.

Veiligheid: klopt het controlegetal van de planning niet, of is de planning onleesbaar, dan schrijft deze taak niets en meldt het (de Action wordt dan rood
en GitHub stuurt een melding). Elke schrijfactie gebruikt de sha van het bestand, dus een gelijktijdige wijziging van een browser wordt nooit overschreven.
Omgeving: GITHUB_TOKEN, GITHUB_REPOSITORY; optioneel DATA_BRANCH (data), ONDERHOUD_DROOG=1 (alleen kijken, niets wijzigen behalve het statusbestand).
"""
import base64, copy, datetime as dt, json, os, random, re, sys, time, urllib.error, urllib.request
from zoneinfo import ZoneInfo

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
REPO = os.environ.get("GITHUB_REPOSITORY", "buas-it/teamplanning-ict")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
BRANCH = os.environ.get("DATA_BRANCH", "data")
DROOG = os.environ.get("ONDERHOUD_DROOG", "").lower() in ("1", "true", "ja", "yes")
ALLEEN_LEZEN = os.environ.get("ONDERHOUD_ALLEEN_LEZEN", "").lower() in ("1", "true", "ja", "yes")   # handmatig meekijken: schrijft echt niets, ook geen statusbestand
if ALLEEN_LEZEN:
    DROOG = True
AMS = ZoneInfo("Europe/Amsterdam")
NAMEN_WEG = ["Frederique", "Ivor", "Dave"]          # moeten nooit meer terugkomen
MONITOR = "Monitor"
DAGEN = ["MA", "DI", "WO", "DO", "VR"]
STATUSSEN = {"kantoor", "vm_kantoor", "nm_kantoor", "thuis", "vm_thuis", "nm_thuis", "vrij", "vm_vrij", "nm_vrij", "ziek", "ziek_thuis", "extern", "vm_extern", "nm_extern"}
MIN_WEKEN = 8            # er blijven altijd minstens zoveel weken over
MAX_DEEL = 0.4           # hooguit 40% van de weken per ronde
MAX_PER_RONDE = 26
MIN_GOEDE_BACKUPS = 5    # een beschadigde backup wordt alleen verwijderd als er nog zoveel goede overblijven
ACHTERSTAND_MIN = 30     # een backup loopt zoveel minuten achter voordat de server er een bijmaakt
STATUS_VERVERSEN_MIN = 55
WEEKSLEUTEL = re.compile(r"^\d{4}-W\d{2}$")


def nu():
    v = os.environ.get("ONDERHOUD_NU")      # alleen voor tests
    return dt.datetime.fromisoformat(v.replace("Z", "+00:00")) if v else dt.datetime.now(dt.timezone.utc)


# ── GitHub ──────────────────────────────────────────────────────────────────────────────────
class Conflict(Exception):
    pass


def call(methode, pad, body=None):
    url = f"{API}/repos/{REPO}/{pad}"
    data = json.dumps(body).encode() if body is not None else None
    for poging in range(4):
        req = urllib.request.Request(url, data=data, method=methode, headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json", "Content-Type": "application/json", "User-Agent": "bezetting-onderhoud"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                j = json.loads(e.read() or b"{}")
            except Exception:
                j = {}
            if e.code in (409, 422) and methode in ("PUT", "DELETE"):
                raise Conflict(f"{e.code}: {j.get('message')}")
            if e.code in (500, 502, 503, 504) and poging < 3:
                time.sleep(2 * (poging + 1)); continue
            return e.code, j
        except (urllib.error.URLError, TimeoutError):
            if poging < 3:
                time.sleep(2 * (poging + 1)); continue
            raise
    return 599, {}


def lees(pad):
    """{'sha', 'tekst'} of None als het bestand er niet is."""
    s, j = call("GET", f"contents/{pad}?ref={BRANCH}&t={int(time.time() * 1000)}")
    if s == 404:
        return None
    if s != 200 or j.get("encoding") != "base64":
        raise RuntimeError(f"{pad} kon niet worden gelezen (HTTP {s})")
    return {"sha": j["sha"], "tekst": base64.b64decode(j["content"]).decode("utf-8")}


def lijst(pad):
    s, j = call("GET", f"contents/{pad}?ref={BRANCH}&t={int(time.time() * 1000)}")
    return j if s == 200 and isinstance(j, list) else []


def schrijf(pad, tekst, sha, bericht):
    body = {"message": bericht, "content": base64.b64encode(tekst.encode("utf-8")).decode(), "branch": BRANCH}
    if sha:
        body["sha"] = sha
    s, j = call("PUT", f"contents/{pad}", body)
    if s not in (200, 201):
        raise RuntimeError(f"{pad} kon niet worden geschreven (HTTP {s}: {j.get('message')})")
    return j["content"]["sha"]


def verwijder(pad, sha, bericht):
    s, j = call("DELETE", f"contents/{pad}", {"message": bericht, "sha": sha, "branch": BRANCH})
    if s not in (200, 204):
        raise RuntimeError(f"{pad} kon niet worden verwijderd (HTTP {s})")


# ── controlegetal (identiek aan de pagina) ─────────────────────────────────────────────────────
def _canon(v):
    if isinstance(v, list):
        return "[" + ",".join(_canon(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + _canon(v[k]) for k in sorted(v)) + "}"
    return json.dumps(v, ensure_ascii=False)


def _imul(a, b):
    return (a * b) & 0xFFFFFFFF


def cyrb53(s):
    h1, h2 = 0xdeadbeef, 0x41c6ce57
    b = s.encode("utf-16-le", "surrogatepass")
    for i in range(0, len(b), 2):
        ch = b[i] | (b[i + 1] << 8)
        h1 = _imul(h1 ^ ch, 2654435761); h2 = _imul(h2 ^ ch, 1597334677)
    h1 = (_imul(h1 ^ (h1 >> 16), 2246822507) ^ _imul(h2 ^ (h2 >> 13), 3266489909)) & 0xFFFFFFFF
    h2 = (_imul(h2 ^ (h2 >> 16), 2246822507) ^ _imul(h1 ^ (h1 >> 13), 3266489909)) & 0xFFFFFFFF
    return 4294967296 * (2097151 & h2) + h1


def kern(s):
    return _canon({"team": s.get("team", []), "store": s.get("store", {}), "template": s.get("template", {}), "manuallyEdited": s.get("manuallyEdited", {}), "hidden": s.get("hidden", [])})


def planning_hash(s):
    return format(cyrb53(kern(s)), "x").rjust(14, "0")


def stempel_status(s):
    i = s.get("integriteit")
    if not i or not isinstance(i.get("h"), str):
        return "geen"
    return "ok" if planning_hash(s) == i["h"] else "fout"


def stempel(s, vorig):
    i = (vorig or {}).get("integriteit") or {}
    s["integriteit"] = {"n": (i.get("n") or 0) + 1, "h": planning_hash(s), "t": nu().strftime("%Y-%m-%dT%H:%M:%S.000Z"), "door": "Server (onderhoud)", "bev": i.get("bev") or 0}
    return s


# ── de planning ────────────────────────────────────────────────────────────────────────────────
def geldig(s):
    return isinstance(s, dict) and isinstance(s.get("team"), list) and len(s["team"]) > 0 and isinstance(s.get("store"), dict) and isinstance(s.get("template", {}), dict) and isinstance(s.get("manuallyEdited", {}), dict)


def split(k):
    i = k.rfind("-")
    return k[:i], k[i + 1:]


def grens():
    """De datum van 2 maanden geleden (Nederlandse tijd)."""
    v = nu().astimezone(AMS).date(); m, j = v.month - 2, v.year
    if m <= 0:
        m += 12; j -= 1
    for d in range(v.day, 27, -1):
        try:
            return dt.date(j, m, d)
        except ValueError:
            continue
    return dt.date(j, m, min(v.day, 28))


def week_einde(wk):
    try:
        return dt.date.fromisocalendar(int(wk[:4]), int(wk[6:]), 7)
    except ValueError:
        return None


def opschonen(s):
    """Haalt weg wat niet hoort; geeft (nieuwe planning, acties, meldingen). Weken ouder dan 2 maanden worden hier nog niet verwijderd."""
    n = copy.deepcopy(s); acties = []; meldingen = []
    team = n["team"]; n.setdefault("template", {}); n.setdefault("manuallyEdited", {}); n.setdefault("hidden", [])
    # 1. verwijderde namen
    weg = 0
    n["team"] = [p for p in n["team"] if p not in NAMEN_WEG]; weg += len(team) - len(n["team"])
    n["hidden"] = [p for p in n["hidden"] if p not in NAMEN_WEG]
    for p in NAMEN_WEG:
        if p in n["template"]:
            del n["template"][p]; weg += 1
    for wk in n["store"]:
        for p in NAMEN_WEG:
            if p in n["store"][wk]:
                del n["store"][wk][p]; weg += 1
    for wk in list(n["manuallyEdited"]):
        k0 = len(n["manuallyEdited"][wk]); n["manuallyEdited"][wk] = [k for k in n["manuallyEdited"][wk] if split(k)[0] not in NAMEN_WEG]; weg += k0 - len(n["manuallyEdited"][wk])
    if weg:
        acties.append(f"verwijderde namen ({', '.join(NAMEN_WEG)}) uit de planning gehaald ({weg} onderdelen)")
    team = n["team"]
    # 2. planning of werkweek van iemand die niet in het team staat
    vreemd = set()
    for wk in n["store"]:
        for p in list(n["store"][wk]):
            if p not in team:
                vreemd.add(p); del n["store"][wk][p]
    for p in list(n["template"]):
        if p not in team:
            vreemd.add(p); del n["template"][p]
    if vreemd:
        acties.append(f"planning/werkweek van niet-teamleden verwijderd: {', '.join(sorted(vreemd))}")
    # 3. onbekende statussen: het onbekende eruit, wat geldig is blijft; bestaat een cel alleen uit onbekende statussen, dan alleen melden
    schoon = 0; alleen_onbekend = []
    for wk in n["store"]:
        for p in n["store"][wk]:
            for d, v in list(n["store"][wk][p].items()):
                if isinstance(v, list) and any(k not in STATUSSEN for k in v):
                    ok = [k for k in v if k in STATUSSEN]
                    if ok:
                        n["store"][wk][p][d] = ok; n["manuallyEdited"].setdefault(wk, [])
                        if f"{p}-{d}" not in n["manuallyEdited"][wk]:
                            n["manuallyEdited"][wk].append(f"{p}-{d}")
                        schoon += 1
                    else:
                        alleen_onbekend.append(f"{wk} {p} {d}")
    if schoon:
        acties.append(f"onbekende status uit {schoon} {'cellen' if schoon != 1 else 'cel'} gehaald")
    if alleen_onbekend:
        meldingen.append(f"{len(alleen_onbekend)} cellen bestaan alleen uit een onbekende status (bijv. {alleen_onbekend[0]}): niet aangeraakt")
    # 4. verweesde markeringen
    wees = 0
    for wk in list(n["manuallyEdited"]):
        if wk not in n["store"]:
            wees += len(n["manuallyEdited"][wk]) or 1; del n["manuallyEdited"][wk]; continue
        k0 = len(n["manuallyEdited"][wk]); n["manuallyEdited"][wk] = [k for k in n["manuallyEdited"][wk] if split(k)[0] in team and split(k)[1] in DAGEN]; wees += k0 - len(n["manuallyEdited"][wk])
    if wees:
        acties.append(f"{wees} verweesde {'markeringen' if wees != 1 else 'markering'} opgeruimd")
    return n, acties, meldingen


def oude_weken(n):
    """De weken die helemaal ouder zijn dan 2 maanden, begrensd (40% per ronde, minstens 8 over). Geeft (te verwijderen weken, alle oude weken)."""
    g = grens(); oud = []
    for wk in sorted(n["store"]):
        if not WEEKSLEUTEL.match(wk):
            continue
        e = week_einde(wk)
        if e is not None and e < g:
            oud.append(wk)
    aantal = len(n["store"]); max_nu = min(MAX_PER_RONDE, int(aantal * MAX_DEEL), aantal - MIN_WEKEN)
    return (oud[:max_nu] if max_nu >= 1 else []), oud


# ── backups ───────────────────────────────────────────────────────────────────────────────────
def backup_naam(t):
    # zoals de pagina: de datum volgens UTC, de tijd volgens Nederlandse tijd (zo blijven de namen op volgorde)
    return f"{t.astimezone(dt.timezone.utc).strftime('%Y-%m-%d')}_{t.astimezone(AMS).strftime('%H-%M')}.json"


def maak_backup(tekst, bestaand, label):
    for k in range(0, 15):
        naam = backup_naam(nu() + dt.timedelta(minutes=k))
        if naam not in bestaand:
            break
    else:
        raise RuntimeError("geen vrije backupnaam")
    sha = schrijf(f"backups/{naam}", tekst, None, f"{label} {naam[:-5]}")
    terug = lees(f"backups/{naam}")
    if not terug or terug["tekst"] != tekst:
        raise RuntimeError(f"backup {naam} is niet teruggelezen zoals geschreven")
    bestaand.add(naam)
    return naam


def backup_oordeel(tekst, aantal_weken):
    """None als de backup goed is, anders de reden."""
    try:
        b = json.loads(tekst)
    except Exception:
        return "niet leesbaar"
    if not geldig(b):
        return "leeg of ongeldig"
    if any(p in NAMEN_WEG for p in b.get("team", [])) or any(p in NAMEN_WEG for w in b["store"].values() for p in w):
        return "bevat een verwijderde naam"
    if aantal_weken >= 10 and len(b["store"]) < aantal_weken * 0.5:
        return "veel minder weken dan de planning"
    return None


# ── logboek en status ─────────────────────────────────────────────────────────────────────────
def log_regel(tekst):
    return {"v": 1, "eid": "".join(random.choice("0123456789abcdef") for _ in range(12)), "t": nu().strftime("%Y-%m-%dT%H:%M:%S.000Z"), "user": "Server", "ws": "GitHub Actions", "device": "server", "id": "Server@onderhoud", "wsinfo": "GitHub Actions · serveronderhoud", "action": tekst, "n": 0, "trunc": False, "changes": []}


def log_schrijf(regels):
    if not regels or DROOG or ALLEEN_LEZEN:
        return
    pad = f"audit/{nu().strftime('%Y-%m-%d')}.jsonl"
    for _ in range(4):
        f = lees(pad)
        nieuw = (f["tekst"] if f else "") + "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in regels)
        try:
            schrijf(pad, nieuw, f["sha"] if f else None, f"Audit {nu().strftime('%Y-%m-%d')} \u2014 Server (onderhoud)"); return
        except Conflict:
            time.sleep(1 + random.random())
    print("let op: het logboek kon niet worden bijgewerkt", file=sys.stderr)


def schrijf_status(acties, problemen, meldingen, extra):
    if ALLEEN_LEZEN:
        return
    f = lees("onderhoud.json"); vorig = None
    if f:
        try:
            vorig = json.loads(f["tekst"])
        except Exception:
            vorig = None
    st = {"v": 1, "t": nu().strftime("%Y-%m-%dT%H:%M:%S.000Z"), "droog": DROOG, "acties": acties, "problemen": problemen, "meldingen": meldingen}
    st.update(extra)
    if vorig:
        oud = dt.datetime.fromisoformat(vorig.get("t", "2000-01-01T00:00:00+00:00").replace("Z", "+00:00"))
        gelijk = vorig.get("acties") == acties and vorig.get("problemen") == problemen and vorig.get("meldingen") == meldingen and vorig.get("droog") == DROOG
        if gelijk and (nu() - oud).total_seconds() < STATUS_VERVERSEN_MIN * 60:
            return   # niets nieuws en nog vers: geen extra commit
    schrijf("onderhoud.json", json.dumps(st, ensure_ascii=False, indent=1) + "\n", f["sha"] if f else None, "Serveronderhoud: status")


# ── een ronde ─────────────────────────────────────────────────────────────────────────────────
def ronde():
    acties, problemen, meldingen = [], [], []
    extra = {}
    f = lees("state.json")
    if not f:
        return acties, ["state.json bestaat niet"], meldingen, extra
    try:
        s = json.loads(f["tekst"])
    except Exception as e:
        return acties, [f"state.json is onleesbaar ({e}): er is niets gewijzigd"], meldingen, extra
    if not geldig(s):
        return acties, ["state.json is leeg of ongeldig: er is niets gewijzigd"], meldingen, extra
    st = stempel_status(s)
    if st == "fout":
        return acties, [f"het controlegetal van de planning klopt niet (laatste opslag nr. {s['integriteit'].get('n')} door {s['integriteit'].get('door')}): er is niets gewijzigd, een Administrator moet dit eerst beoordelen"], meldingen, extra
    extra["weken"] = len(s["store"]); extra["team"] = len(s["team"])
    n, a1, m1 = opschonen(s); acties += a1; meldingen += m1
    teWissen, alle_oud = oude_weken(n)
    if teWissen:
        for wk in teWissen:
            n["store"].pop(wk, None); n["manuallyEdited"].pop(wk, None)
        acties.append(f"{len(teWissen)} {'weken' if len(teWissen) != 1 else 'week'} ouder dan 2 maanden verwijderd ({teWissen[0]}{' t/m ' + teWissen[-1] if len(teWissen) > 1 else ''})")
    rest = len(alle_oud) - len(teWissen)
    if rest > 0:
        meldingen.append(f"nog {rest} oude {'weken' if rest != 1 else 'week'} te verwijderen in de volgende ronde")
    wijziging = kern(n) != kern(s)
    gewijzigd_bestand = wijziging or st == "geen"
    bestaand = {x["name"] for x in lijst("backups")}
    if gewijzigd_bestand and DROOG:
        acties.append("(droogloop: er is niets geschreven)")
    elif gewijzigd_bestand:
        # eerst een backup van de planning zoals die nu is; lukt dat niet, dan wordt er niets gewijzigd
        try:
            naam = maak_backup(f["tekst"], bestaand, "Auto-backup (server, voor onderhoud)")
        except Exception as e:
            return acties, [f"de backup vooraf is niet gelukt ({e}): er is niets gewijzigd"], meldingen, extra
        acties.insert(0, f"backup vooraf: {naam[:-5]}")
        if st == "geen" and not wijziging:
            acties.append("controlegetal vastgelegd")
        stempel(n, s)
        nieuw_tekst = json.dumps(n, ensure_ascii=False)
        sha = schrijf("state.json", nieuw_tekst, f["sha"], "Update planning \u2014 Server (onderhoud)")
        # teruglezen en vergelijken
        t = lees("state.json"); fouten = []
        try:
            T = json.loads(t["tekst"]) if t else None
        except Exception:
            T = None
        if not T or not geldig(T):
            fouten.append("de opgeslagen planning is onleesbaar")
        else:
            if stempel_status(T) != "ok":
                fouten.append("het controlegetal van de opgeslagen planning klopt niet")
            if kern(T) != kern(n):
                fouten.append("wat op GitHub staat wijkt af van wat is opgeslagen")
            if len(T["store"]) != len(n["store"]):
                fouten.append("het aantal weken klopt niet")
        if fouten:
            try:   # automatisch terugzetten naar de planning van voor het onderhoud
                schrijf("state.json", f["tekst"], t["sha"] if t else sha, "Planning teruggezet \u2014 Server (onderhoud): controle na opslaan mislukt")
                fouten.append("de planning is teruggezet naar de stand van voor het onderhoud")
            except Exception as e2:
                fouten.append(f"terugzetten lukte niet ({e2}): zet backup {naam[:-5]} terug")
            return acties, ["controle na opslaan mislukt: " + "; ".join(fouten)], meldingen, extra
        extra["weken"] = len(n["store"]); extra["team"] = len(n["team"]); extra["stempel_n"] = n["integriteit"]["n"]
        bestaand = {x["name"] for x in lijst("backups")}
        try:
            naam2 = maak_backup(nieuw_tekst, bestaand, "Auto-backup (server, na onderhoud)"); acties.append(f"backup achteraf: {naam2[:-5]}")
        except Exception as e:
            meldingen.append(f"de backup achteraf is niet gelukt ({e})")
        s = n
    else:
        extra["stempel_n"] = (s.get("integriteit") or {}).get("n")
    # backups bijhouden: loopt de nieuwste achter op de planning, dan er een bijmaken
    if not DROOG and not gewijzigd_bestand:
        bestaand = {x["name"] for x in lijst("backups")}; nieuwste = sorted(bestaand)[-1] if bestaand else None; achter = True
        if nieuwste:
            b = lees(f"backups/{nieuwste}")
            try:
                achter = not b or planning_hash(json.loads(b["tekst"])) != planning_hash(s)
            except Exception:
                achter = True
        t_stempel = None
        try:
            t_stempel = dt.datetime.fromisoformat(s["integriteit"]["t"].replace("Z", "+00:00"))
        except Exception:
            t_stempel = None
        if achter and (t_stempel is None or (nu() - t_stempel).total_seconds() > ACHTERSTAND_MIN * 60):
            try:
                acties.append(f"backup bijgemaakt: {maak_backup(f['tekst'], bestaand, 'Auto-backup (server)')[:-5]}")
            except Exception as e:
                problemen.append(f"een backup maken is niet gelukt ({e})")
    # beschadigde backups: de nieuwste drie nakijken
    items = sorted(lijst("backups"), key=lambda x: x["name"])
    if items:
        slecht = []
        for it in items[-3:]:
            b = lees(f"backups/{it['name']}")
            r = backup_oordeel(b["tekst"], len(s["store"])) if b else "niet leesbaar"
            if r:
                slecht.append((it, r))
        if slecht:
            tekst = "; ".join(f"{it['name'][:-5]} ({r})" for it, r in slecht)
            if len(items) - len(slecht) >= MIN_GOEDE_BACKUPS and not DROOG:
                for it, r in slecht:
                    verwijder(f"backups/{it['name']}", it["sha"], f"Beschadigde backup verwijderd (server): {it['name']}")
                acties.append(f"beschadigde backup verwijderd: {tekst}")
            else:
                problemen.append(f"beschadigde backup: {tekst} (niet verwijderd: te weinig goede backups of droogloop)")
    # accounts van verwijderde namen
    u = lees("users.json")
    if u:
        try:
            uj = json.loads(u["tekst"]); acc = uj.get("users", {})
            weg = [p for p in acc if p in NAMEN_WEG]
            vreemd = [p for p in acc if p not in s["team"] and p != MONITOR and p not in NAMEN_WEG]
            if weg and not DROOG:
                for p in weg:
                    del acc[p]
                schrijf("users.json", json.dumps(uj, ensure_ascii=False), u["sha"], "Account van verwijderde naam verwijderd \u2014 Server (onderhoud)")
                acties.append(f"account van verwijderde naam verwijderd: {', '.join(weg)}")
            if vreemd:
                meldingen.append(f"accounts van mensen die niet in het team staan: {', '.join(vreemd)}")
        except Exception as e:
            meldingen.append(f"users.json niet gecontroleerd ({e})")
    return acties, problemen, meldingen, extra


def lees_config():
    """onderhoud-config.json op de data-branch: {"droog": true} laat de taak alleen kijken. Ontbreekt het bestand, dan wordt er gewoon onderhouden; is het onleesbaar, dan wordt er niets gewijzigd."""
    global DROOG
    try:
        f = lees("onderhoud-config.json")
    except Exception as e:
        DROOG = True; return [f"onderhoud-config.json niet te lezen ({e}): alleen gekeken"]
    if not f:
        return []
    try:
        c = json.loads(f["tekst"])
        if c.get("droog") is True:
            DROOG = True
        return []
    except Exception:
        DROOG = True; return ["onderhoud-config.json is onleesbaar: alleen gekeken, niets gewijzigd"]


def main():
    config_meldingen = lees_config()
    acties = problemen = meldingen = extra = None
    for poging in range(3):
        try:
            acties, problemen, meldingen, extra = ronde(); break
        except Conflict as e:
            print(f"gelijktijdige wijziging ({e}); opnieuw proberen", file=sys.stderr); time.sleep(2 + random.random() * 3)
    else:
        acties, problemen, meldingen, extra = [], ["er is steeds tegelijk een andere wijziging binnengekomen: niets gewijzigd, volgende ronde opnieuw"], [], {}
    meldingen = (meldingen or []) + config_meldingen
    log_schrijf([log_regel("onderhoud: " + a) for a in acties] + [log_regel("onderhoud: PROBLEEM: " + p) for p in problemen])
    try:
        schrijf_status(acties, problemen, meldingen, extra or {})
    except Exception as e:
        print(f"let op: het statusbestand kon niet worden geschreven ({e})", file=sys.stderr)
    print(json.dumps({"acties": acties, "problemen": problemen, "meldingen": meldingen, "droog": DROOG}, ensure_ascii=False, indent=1))
    sys.exit(1 if problemen else 0)


if __name__ == "__main__":
    main()
