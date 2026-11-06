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
ACHTERSTAND_MIN = 5      # de server maakt een backup zodra er zoveel minuten niets meer is gewijzigd (de pagina deed dat vroeger elke 10 minuten)
BACKUP_BEWAAR_DAGEN = 14  # backups worden zoveel dagen bewaard (op UTC-datum in de naam, zoals de pagina vroeger deed)
AUDIT_BEWAAR_DAGEN = 31   # dagbestanden van het logboek worden zoveel dagen bewaard
MIN_BEWAARD = 5           # bij het opruimen blijven er altijd minstens zoveel backups over
MAX_OPRUIMEN = 20         # hooguit zoveel bestanden per ronde opruimen
WACHT_FACTOR = float(os.environ.get("ONDERHOUD_WACHT_FACTOR", "0" if os.environ.get("ONDERHOUD_NU") else "1"))   # voor tests: niet echt wachten
STATUS_VERVERSEN_MIN = 55
WEEKSLEUTEL = re.compile(r"^\d{4}-W\d{2}$")
PAGES_URL = os.environ.get("PAGES_URL", "https://buas-it.github.io/teamplanning-ict/")
LABEL = re.compile(r'id="app-version"[^>]*>\s*(versie [^<]+?)\s*<')
GROEPEN = ["Verbinding en versie", "Planning", "Team, accounts en rechten", "Backups en logboek"]


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


def lees_ref(pad, ref):
    """Zoals lees(), maar van een andere branch (bijvoorbeeld main)."""
    s, j = call("GET", f"contents/{pad}?ref={ref}&t={int(time.time() * 1000)}")
    if s == 404:
        return None
    if s != 200 or j.get("encoding") != "base64":
        raise RuntimeError(f"{pad} ({ref}) kon niet worden gelezen (HTTP {s})")
    return {"sha": j["sha"], "tekst": base64.b64decode(j["content"]).decode("utf-8")}


def http_tekst(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "bezetting-onderhoud", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def pagina_main():
    """De tekst van index.html op main (of None): daar staan de verplichte vrije dagen, de verjaardagen, het versielabel en het token van de pagina in."""
    try:
        m = lees_ref("index.html", "main"); return m["tekst"] if m else None
    except Exception:
        return None


def parse_locked(html):
    m = re.search(r"const LOCKED_DAYS = new Set\(\[(.*?)\]\);", html or "", re.S)
    return set(re.findall(r'"(\d{4}-W\d{2}-[A-Z]{2})"', m.group(1))) if m else None


def parse_verjaardagen(html):
    m = re.search(r"let VERJAARDAGEN = \{(.*?)\};", html or "", re.S)
    return dict(re.findall(r'(\w+)\s*:\s*"(\d\d-\d\d)"', m.group(1))) if m else None


def parse_token(html):
    m = re.search(r"const GH_TOKEN\s*=\s*(.*?);", html or "", re.S)
    if not m: return None
    t = "".join(re.findall(r'"([^"]*)"', m.group(1)))
    return t if t.startswith(("github_pat_", "ghp_")) else None


def token_info(token):
    """(status, koppen in kleine letters, json) van een verzoek met het token van de pagina. Het token wordt nergens getoond of bewaard."""
    req = urllib.request.Request(f"{API}/repos/{REPO}", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "bezetting-onderhoud"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, {}


_LAATSTE = {}
def laatste_opslag_tijd(s=None):
    """Wanneer is de planning voor het laatst opgeslagen, volgens GitHub (de tijd van de commit). Alleen als dat niet te lezen is gebruiken we het tijdstip dat de pagina in het controlegetal zette."""
    if "t" in _LAATSTE: return _LAATSTE["t"]
    t = None
    try:
        st_, j = call("GET", f"commits?sha={BRANCH}&path=state.json&per_page=1")
        if st_ == 200 and isinstance(j, list) and j: t = dt.datetime.fromisoformat(j[0]["commit"]["committer"]["date"].replace("Z", "+00:00"))
    except Exception:
        t = None
    if t is None and s:
        try: t = dt.datetime.fromisoformat(s["integriteit"]["t"].replace("Z", "+00:00"))
        except Exception: t = None
    _LAATSTE["t"] = t
    return t


def lijst(pad):
    s, j = call("GET", f"contents/{pad}?ref={BRANCH}&t={int(time.time() * 1000)}")
    return j if s == 200 and isinstance(j, list) else []


def schrijf(pad, tekst, sha, bericht):
    body = {"message": bericht, "content": base64.b64encode(tekst.encode("utf-8")).decode(), "branch": BRANCH}
    if sha:
        body["sha"] = sha
    try:
        s, j = call("PUT", f"contents/{pad}", body)
    except Conflict:
        # GitHub geeft soms een tijdelijke fout (502) terwijl de schrijfactie wel is verwerkt; de herhaalpoging krijgt dan "bestaat al" of "sha klopt niet".
        # Staat er precies wat we wilden schrijven, dan is het gelukt. Anders is er echt tegelijk iets anders gewijzigd.
        nu_f = lees(pad)
        if nu_f and nu_f["tekst"] == tekst:
            return nu_f["sha"]
        raise
    if s not in (200, 201):
        raise RuntimeError(f"{pad} kon niet worden geschreven (HTTP {s}: {j.get('message')})")
    return j["content"]["sha"]


def verwijder(pad, sha, bericht):
    try:
        s, j = call("DELETE", f"contents/{pad}", {"message": bericht, "sha": sha, "branch": BRANCH})
    except Conflict:
        if lees(pad) is None:
            return   # al verwijderd (een eerdere poging was wel verwerkt)
        raise
    if s == 404:
        return       # bestaat niet meer: al verwijderd
    if s not in (200, 204):
        raise RuntimeError(f"{pad} kon niet worden verwijderd (HTTP {s})")


# ── het logboek van wijzigingen: de server leidt ze af uit de opslagen van de planning (de pagina schrijft alleen nog bezoeken en inloggen) ──
LOG_MAX_CHANGES = 200
LOG_STATUS = {"ok": True, "fout": None}   # voor de controle 'Wijzigingsregels worden door de server geschreven'


def log_diff(base, cur, hinted):
    """Identiek aan auditDiff in de pagina: wat is er veranderd tussen twee standen van de planning."""
    same = lambda a, b: (a or []) == (b or [])
    b_team = [p for p in base.get("team", []) if p != "__divider__"]; c_team = [p for p in cur.get("team", []) if p != "__divider__"]
    both = [p for p in c_team if p in b_team]
    team = [{"s": "team+", "p": p} for p in c_team if p not in b_team] + [{"s": "team-", "p": p} for p in b_team if p not in c_team]
    b_tpl = base.get("template") or {}; c_tpl = cur.get("template") or {}; tpl = []
    for p in both:
        for d in DAGEN:
            a = (b_tpl.get(p) or {}).get(d); b = (c_tpl.get(p) or {}).get(d)
            if not same(a, b): tpl.append({"s": "standaard", "p": p, "d": d, "from": a or [], "to": b or []})
    b_store = base.get("store") or {}; c_store = cur.get("store") or {}; cells = []
    for w in c_store:
        bw = b_store.get(w) or {}; cw = c_store.get(w) or {}
        for p in both:
            for d in DAGEN:
                b = (cw.get(p) or {}).get(d)
                if b is None: continue
                a = (bw.get(p) or {}).get(d)
                if a is None: a = (b_tpl.get(p) or {}).get(d)
                if not same(a, b): cells.append({"s": "cel", "w": w, "p": p, "d": d, "from": a or [], "to": b or []})
    if tpl and not hinted: changes = team + tpl + [{"s": "doorgevoerd", "n": len(cells)}]; n = len(team) + len(tpl)
    else: changes = team + tpl + cells; n = len(team) + len(tpl) + len(cells)
    return {"n": n, "trunc": len(changes) > LOG_MAX_CHANGES, "changes": changes[:LOG_MAX_CHANGES], "action": "standaard" if tpl else ("team" if team and not cells else "wijziging")}


def log_state_op(ref):
    s, j = call("GET", f"contents/state.json?ref={ref}")
    if s != 200 or j.get("encoding") != "base64": return None
    try: d = json.loads(base64.b64decode(j["content"]).decode("utf-8"))
    except Exception: return None
    return d if geldig(d) else None


def log_wijzigingen(pointer):
    """(regels, nieuwe pointer, meldingen): de wijzigingsregels van alle opslagen van de planning na de laatst verwerkte opslag."""
    s, lst = call("GET", f"commits?sha={BRANCH}&path=state.json&per_page=100")
    if s != 200 or not isinstance(lst, list): raise RuntimeError(f"de opslagen zijn niet te lezen (HTTP {s})")
    if not lst: return [], pointer, []
    nieuwste = lst[0]["sha"]
    if not pointer: return [], nieuwste, []   # de eerste keer: vanaf nu bijhouden (wat daarvoor is gebeurd heeft de pagina al gelogd)
    if nieuwste == pointer: return [], pointer, []
    nieuw = []; gevonden = False
    for c in lst:
        if c["sha"] == pointer: gevonden = True; break
        nieuw.append(c)
    meldingen = [] if gevonden else [f"meer dan {len(lst)} opslagen sinds de vorige ronde: de oudste zijn niet gelogd"]
    nieuw.reverse(); regels = []
    vorig = log_state_op(nieuw[0]["parents"][0]["sha"]) if nieuw[0].get("parents") else None
    for c in nieuw:
        cur = log_state_op(c["sha"]); msg = (c["commit"].get("message") or "").split("\n")[0]
        if cur is None: meldingen.append(f"opslag {c['sha'][:7]} is niet te lezen: geen wijzigingsregel"); continue
        if vorig is not None and "Server (onderhoud)" not in msg:
            m = re.match(r"^(.*?) \u2014 (\S+)(?: \((.*)\))?$", msg)
            basis_t = m.group(1) if m else msg; ident = m.group(2) if m else None; ws = (m.group(3) or "") if m else ""
            hint = basis_t if basis_t.startswith(("periode: ", "backup hersteld: ")) else ("backup hersteld: " + basis_t[len("Herstel backup "):] if basis_t.startswith("Herstel backup ") else None)
            d = log_diff(vorig, cur, bool(hint))
            if d["n"]:
                t = dt.datetime.fromisoformat(c["commit"]["committer"]["date"].replace("Z", "+00:00")).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                regel = {"v": 1, "eid": "srv-" + c["sha"][:12], "t": t, "user": (ident.split("@")[0] if ident else "onbekend"), "ws": ws, "device": (ident.split("@")[1] if ident and "@" in ident else ""), "id": ident or "", "wsinfo": "",
                         "action": hint or d["action"], "n": d["n"], "trunc": d["trunc"], "changes": d["changes"], "bron": "server"}
                if not ident: regel["buiten_app"] = True
                regels.append(regel)
        vorig = cur
    return regels, nieuwste, meldingen


def log_schrijf_dagen(regels):
    """De regels per dag toevoegen aan audit/<dag>.jsonl, zonder dubbelen (op eid)."""
    for dag in sorted({r["t"][:10] for r in regels}):
        pad = f"audit/{dag}.jsonl"; nieuw_r = [r for r in regels if r["t"][:10] == dag]
        for _ in range(5):
            f = lees(pad); aanwezig = set()
            for l in (f["tekst"] if f else "").split("\n"):
                try: aanwezig.add(json.loads(l).get("eid"))
                except Exception: pass
            toe = [r for r in nieuw_r if r["eid"] not in aanwezig]
            if not toe: break
            tekst = (f["tekst"] if f else "")
            if tekst and not tekst.endswith("\n"): tekst += "\n"
            try:
                schrijf(pad, tekst + "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in toe), f["sha"] if f else None, f"Audit {dag} \u2014 Server (onderhoud)"); break
            except Conflict:
                time.sleep(1 + random.random())
        else:
            raise RuntimeError(f"het logboek van {dag} kon niet worden bijgewerkt")


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


def opschonen(s, locked=None):
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
    # 5. verplichte vrije dagen (feestdagen, kerstperiode): voor iedereen Vrij, ongeacht de werkweek
    if locked:
        gezet = 0
        for wk in n["store"]:
            for d in DAGEN:
                if f"{wk}-{d}" in locked:
                    for p in team:
                        if p in n["store"][wk] and n["store"][wk][p].get(d) != ["vrij"]:
                            n["store"][wk][p][d] = ["vrij"]; gezet += 1
        if gezet:
            acties.append(f"{gezet} {'cel' if gezet == 1 else 'cellen'} op een verplichte vrije dag op Vrij gezet")
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
        except Exception as e:   # een serverfout van GitHub mag de rest van de ronde (het statusbestand) niet tegenhouden
            print(f"let op: het logboek kon niet worden bijgewerkt ({e})", file=sys.stderr); return
    print("let op: het logboek kon niet worden bijgewerkt", file=sys.stderr)


def schrijf_status(acties, problemen, meldingen, extra, checks=None):
    if ALLEEN_LEZEN:
        return
    f = lees("onderhoud.json"); vorig = None
    if f:
        try:
            vorig = json.loads(f["tekst"])
        except Exception:
            vorig = None
    st = {"v": 1, "t": nu().strftime("%Y-%m-%dT%H:%M:%S.000Z"), "droog": DROOG, "acties": acties, "problemen": problemen, "meldingen": meldingen, "checks": checks or []}
    st.update(extra)
    if vorig:
        oud = dt.datetime.fromisoformat(vorig.get("t", "2000-01-01T00:00:00+00:00").replace("Z", "+00:00"))
        gelijk = vorig.get("acties") == acties and vorig.get("problemen") == problemen and vorig.get("meldingen") == meldingen and vorig.get("droog") == DROOG and vorig.get("state_sha") == extra.get("state_sha") and vorig.get("audit_commit") == extra.get("audit_commit") and [(c["id"], c["s"], c["t"]) for c in (vorig.get("checks") or [])] == [(c["id"], c["s"], c["t"]) for c in (checks or [])]   # is de planning veranderd sinds de vorige ronde, dan komt er een nieuwe status
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
    extra["weken"] = len(s["store"]); extra["team"] = len(s["team"]); extra["state_sha"] = f["sha"]   # de versie van de planning die de server nu ziet
    locked = parse_locked(pagina_main())   # de verplichte vrije dagen staan in de pagina op main
    n, a1, m1 = opschonen(s, locked); acties += a1; meldingen += m1
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
        extra["weken"] = len(n["store"]); extra["team"] = len(n["team"]); extra["stempel_n"] = n["integriteit"]["n"]; extra["state_sha"] = t["sha"]; extra["stempel_bev"] = n["integriteit"].get("bev", 0)   # de planning zoals de server hem zojuist heeft achtergelaten
        bestaand = {x["name"] for x in lijst("backups")}
        try:
            naam2 = maak_backup(nieuw_tekst, bestaand, "Auto-backup (server, na onderhoud)"); acties.append(f"backup achteraf: {naam2[:-5]}")
        except Exception as e:
            meldingen.append(f"de backup achteraf is niet gelukt ({e})")
        s = n
    else:
        extra["stempel_n"] = (s.get("integriteit") or {}).get("n"); extra["stempel_bev"] = (s.get("integriteit") or {}).get("bev", 0)
    # backups bijhouden: loopt de nieuwste achter op de planning, dan er een bijmaken
    if not DROOG and not gewijzigd_bestand:
        bestaand = {x["name"] for x in lijst("backups")}; nieuwste = sorted(bestaand)[-1] if bestaand else None; achter = True
        if nieuwste:
            b = lees(f"backups/{nieuwste}")
            try:
                achter = not b or planning_hash(json.loads(b["tekst"])) != planning_hash(s)
            except Exception:
                achter = True
        t_stempel = laatste_opslag_tijd(s)   # de tijd van GitHub bij de laatste opslag: de klok van een apparaat telt niet mee
        wacht_af = False
        if achter and t_stempel is not None and (nu() - t_stempel).total_seconds() < ACHTERSTAND_MIN * 60:
            rest = ACHTERSTAND_MIN * 60 - (nu() - t_stempel).total_seconds() + 3   # wachten tot er 5 minuten niets is gewijzigd (de Action mag 10 minuten duren)
            time.sleep(min(rest, 330) * WACHT_FACTOR)
            f2 = lees("state.json")
            if not f2 or f2["sha"] != f["sha"]:
                meldingen.append("de planning is tijdens het wachten gewijzigd: de volgende ronde maakt de backup"); wacht_af = True
        if achter and not wacht_af:
            grootste = 0
            for naam_b in sorted(bestaand)[-5:]:
                try:
                    bb = lees(f"backups/{naam_b}"); grootste = max(grootste, len(json.loads(bb["tekst"])["store"])) if bb else grootste
                except Exception:
                    pass
            if len(s["store"]) >= 10 and grootste >= 10 and len(s["store"]) < grootste * 0.5:   # nooit een backup maken van een planning die er beschadigd uitziet
                problemen.append(f"de planning heeft opeens veel minder weken ({len(s['store'])}) dan de nieuwste backups ({grootste}): er is geen backup bijgemaakt, een Administrator moet dit beoordelen")
            else:
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
    # bewaartermijnen: backups (14 dagen) en dagbestanden van het logboek (31 dagen)
    try:
        cut_b = (nu() - dt.timedelta(days=BACKUP_BEWAAR_DAGEN)).strftime("%Y-%m-%d")
        items_b = sorted(lijst("backups"), key=lambda x: x["name"])
        oud_b = [it for it in items_b if it["name"][:10] < cut_b]
        weg_b = oud_b[:max(0, min(MAX_OPRUIMEN, len(items_b) - MIN_BEWAARD))]
        if weg_b and DROOG:
            meldingen.append(f"droogloop: {len(weg_b)} backups ouder dan {BACKUP_BEWAAR_DAGEN} dagen zouden worden verwijderd")
        elif weg_b:
            for it in weg_b:
                verwijder(f"backups/{it['name']}", it["sha"], f"Verwijder oude backup {it['name'][:10]} (server, bewaartermijn {BACKUP_BEWAAR_DAGEN} dagen)")
            acties.append(f"{len(weg_b)} {'backup' if len(weg_b) == 1 else 'backups'} ouder dan {BACKUP_BEWAAR_DAGEN} dagen verwijderd ({weg_b[0]['name'][:10]}{' t/m ' + weg_b[-1]['name'][:10] if len(weg_b) > 1 else ''})")
        rest_b = len(oud_b) - len(weg_b)
        if rest_b > 0 and not DROOG:
            meldingen.append(f"nog {rest_b} {'backup' if rest_b == 1 else 'backups'} ouder dan {BACKUP_BEWAAR_DAGEN} dagen te verwijderen in een volgende ronde")
        cut_a = (nu() - dt.timedelta(days=AUDIT_BEWAAR_DAGEN)).strftime("%Y-%m-%d")
        oud_a = sorted((it for it in lijst("audit") if re.match(r"^\d{4}-\d\d-\d\d\.jsonl$", it["name"]) and it["name"][:10] < cut_a), key=lambda x: x["name"])
        weg_a = oud_a[:MAX_OPRUIMEN]
        if weg_a and DROOG:
            meldingen.append(f"droogloop: {len(weg_a)} dagbestanden van het logboek ouder dan {AUDIT_BEWAAR_DAGEN} dagen zouden worden verwijderd")
        elif weg_a:
            for it in weg_a:
                verwijder(f"audit/{it['name']}", it["sha"], f"Audit opgeruimd: {it['name'][:10]} (server, bewaartermijn {AUDIT_BEWAAR_DAGEN} dagen)")
            acties.append(f"{len(weg_a)} {'dagbestand' if len(weg_a) == 1 else 'dagbestanden'} van het logboek ouder dan {AUDIT_BEWAAR_DAGEN} dagen verwijderd ({weg_a[0]['name'][:10]}{' t/m ' + weg_a[-1]['name'][:10] if len(weg_a) > 1 else ''})")
    except Conflict:
        raise
    except Exception as e:
        meldingen.append(f"het opruimen van oude backups en logboekbestanden is niet gelukt ({e})")
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


# ── de controles (alles wat niet van een apparaat afhangt) ──────────────────────────────────────
def controles(acties, problemen):
    """Geeft een lijst {id, groep, naam, s (ok|info|let|fout), t} van alle controles die de server kan doen. De pagina laat dit zien en doet zelf alleen wat bij het apparaat hoort."""
    uit = []
    def add(id, groep, naam, s, t):
        uit.append({"id": id, "groep": groep, "naam": naam, "s": s, "t": t})
    def veilig(naam_groep, f):
        try:
            f()
        except Exception as e:
            add(naam_groep, 3, naam_groep, "fout", f"de controle zelf is mislukt: {e}")
    try:
        f = lees("state.json"); s = json.loads(f["tekst"]) if f else None
    except Exception:
        f = None; s = None
    ok_state = bool(s) and geldig(s); team = s["team"] if ok_state else []
    if not ok_state:
        add("github", 0, "GitHub bereikbaar", "fout", "de server kan de planning niet (goed) lezen"); return uit
    add("github", 0, "GitHub bereikbaar", "ok", "de server kan de planning lezen")
    # uitrol van de pagina
    pagina = pagina_main()
    try:
        lm = (LABEL.search(pagina) or [None, None])[1] if pagina else None
        try:
            pg = LABEL.search(http_tekst(PAGES_URL + "index.html?k=" + str(int(time.time())))); lp = pg.group(1) if pg else None; bereikbaar = True
        except Exception:
            lp = None; bereikbaar = False
        if not lm: add("uitrol", 0, "Uitrol van de pagina (GitHub Pages)", "info", "de versie op main is niet te lezen")
        elif not bereikbaar or not lp: add("uitrol", 0, "Uitrol van de pagina (GitHub Pages)", "info", "de site is vanaf de server niet te bereiken of toont geen versie")
        elif lm == lp: add("uitrol", 0, "Uitrol van de pagina (GitHub Pages)", "ok", f"de site toont dezelfde versie als main ({lm})")
        else: add("uitrol", 0, "Uitrol van de pagina (GitHub Pages)", "let", f"de site toont {lp}, main heeft {lm}: de uitrol loopt achter")
    except Exception as e:
        add("uitrol", 0, "Uitrol van de pagina (GitHub Pages)", "info", f"niet te controleren ({e})")
    # het token van de pagina (dat alle gebruikers delen): werkt het nog, mag het schrijven, wanneer verloopt het, hoeveel API-ruimte is er over
    tok = parse_token(pagina)
    if not tok:
        add("token", 0, "Token van de pagina", "info", "het token is niet te vinden in de pagina (of de pagina is niet te lezen)")
        add("limiet", 0, "Ruimte in de API-limiet", "info", "niet te meten zonder het token van de pagina")
    else:
        try:
            st_t, hd, js = token_info(tok)
        except Exception as e:
            st_t, hd, js = None, {}, {}; add("token", 0, "Token van de pagina", "info", f"niet te controleren ({e})"); add("limiet", 0, "Ruimte in de API-limiet", "info", "niet te meten")
        if st_t is not None:
            if st_t != 200:
                add("token", 0, "Token van de pagina", "fout", f"het token van de pagina werkt niet meer (HTTP {st_t}): wijzigingen kunnen niet worden opgeslagen"); add("limiet", 0, "Ruimte in de API-limiet", "info", "niet te meten: het token werkt niet")
            else:
                push = (js.get("permissions") or {}).get("push", True); verloopt = hd.get("github-authentication-token-expiration"); dagen = None
                if verloopt:
                    try: dagen = (dt.datetime.strptime(verloopt.strip(), "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=dt.timezone.utc) - nu()).days
                    except ValueError: dagen = None
                if not push: add("token", 0, "Token van de pagina", "fout", "het token mag niet schrijven: wijzigingen kunnen niet worden opgeslagen")
                elif dagen is not None and dagen <= 7: add("token", 0, "Token van de pagina", "fout", f"het token verloopt over {max(dagen, 0)} dagen ({verloopt.strip()[:10]}): maak een nieuw token en zet het in de pagina")
                elif dagen is not None and dagen <= 30: add("token", 0, "Token van de pagina", "let", f"het token verloopt over {dagen} dagen ({verloopt.strip()[:10]}): maak op tijd een nieuw token")
                elif dagen is not None: add("token", 0, "Token van de pagina", "ok", f"het token werkt, mag schrijven en is geldig tot {verloopt.strip()[:10]}")
                else: add("token", 0, "Token van de pagina", "info", "het token werkt en mag schrijven; er is geen vervaldatum bekend (een token zonder vervaldatum)")
                try: rest, maxi = int(hd.get("x-ratelimit-remaining")), int(hd.get("x-ratelimit-limit"))
                except (TypeError, ValueError): rest = maxi = None
                if rest is None: add("limiet", 0, "Ruimte in de API-limiet", "info", "GitHub gaf de limiet niet door")
                else: add("limiet", 0, "Ruimte in de API-limiet", "fout" if rest < 50 else "let" if rest < 300 else "ok", (f"nog maar {rest} van {maxi} verzoeken per uur over: bijna op" if rest < 300 else f"ruim voldoende (de limiet is {maxi} verzoeken per uur)"))
    # planning
    i = s.get("integriteit") or {}; stp = stempel_status(s)
    n_s = i.get("n") or 0; bev_s = i.get("bev") or 0
    try:
        vs = lees("onderhoud.json"); vorig_s = json.loads(vs["tekst"]) if vs else {}
    except Exception:
        vorig_s = {}
    eerder_n = vorig_s.get("stempel_n"); teruggezet = stp == "ok" and isinstance(eerder_n, int) and n_s < eerder_n and bev_s <= (vorig_s.get("stempel_bev") or 0)
    if teruggezet: add("stempel", 1, "Controlegetal", "fout", f"het volgnummer ({n_s}) is lager dan eerder gezien ({eerder_n}): een oudere stand is teruggezet buiten de app om; een Administrator moet dit beoordelen en bevestigen")
    else: add("stempel", 1, "Controlegetal", {"ok": "ok", "geen": "let", "fout": "fout"}[stp], {"ok": f"klopt (opslag {i.get('n')} door {i.get('door')})", "geen": "nog niet vastgelegd", "fout": f"klopt niet (opslag {i.get('n')} door {i.get('door')}): een Administrator moet dit beoordelen"}[stp])
    items = sorted(lijst("backups"), key=lambda x: x["name"])
    n = len(s["store"]); ks = sorted(s["store"]); nieuwste = None; grootste_b = 0
    for it in items[-5:]:
        try:
            b = lees(f"backups/{it['name']}"); bj = json.loads(b["tekst"]) if b else None
            if it is items[-1]: nieuwste = bj
            if bj and geldig(bj): grootste_b = max(grootste_b, len(bj["store"]))
        except Exception:
            pass
    if not ks: add("weken", 1, "Aantal weken in de planning", "fout", "geen enkele week")
    elif n >= 10 and grootste_b >= 10 and n < grootste_b * 0.5: add("weken", 1, "Aantal weken in de planning", "fout", f"opeens veel minder weken ({n}) dan in de nieuwste backups ({grootste_b}): mogelijk beschadigd")
    else: add("weken", 1, "Aantal weken in de planning", "ok", f"{n} weken, {ks[0]} t/m {ks[-1]}")
    personen = set(team) | set(s.get("hidden", [])) | set(s.get("template", {})) | {p for w in s["store"].values() for p in w} | {split(k)[0] for l in s.get("manuallyEdited", {}).values() for k in l}
    weg = sorted(p for p in personen if p in NAMEN_WEG)
    add("namen", 1, "Verwijderde namen zijn weg", "fout" if weg else "ok", f"een verwijderde naam staat nog in de planning: {', '.join(weg)}" if weg else f"{', '.join(NAMEN_WEG)} komen nergens voor")
    f_ = []
    dub = sorted({p for p in team if team.count(p) > 1})
    if dub: f_.append("dubbele namen: " + ", ".join(dub))
    zonder = [p for p in team if p not in s.get("template", {}) or any(not isinstance(s["template"][p].get(d), list) for d in DAGEN)]
    if zonder: f_.append("geen volledige werkweek voor " + ", ".join(zonder))
    verb = [p for p in s.get("hidden", []) if p not in team]
    if verb: f_.append("verborgen maar geen teamlid: " + ", ".join(verb))
    add("team", 1, "Team en werkweken", "fout" if f_ else "ok", "; ".join(f_) if f_ else f"{len(team)} personen, iedereen heeft een werkweek" + (f"; {len(s['hidden'])} verborgen" if s.get("hidden") else ""))
    vreemd = sorted({p for w in s["store"].values() for p in w if p not in team} | {p for p in s.get("template", {}) if p not in team})
    add("vreemd", 1, "Geen planning voor niet-teamleden", "let" if vreemd else "ok", ("planning of werkweek van " + ", ".join(vreemd) + ", die niet in het team staan") if vreemd else "alleen het team")
    slecht = []; leeg = []
    for wk in s["store"]:
        for p, dd in s["store"][wk].items():
            for d, v in dd.items():
                if isinstance(v, list) and any(k not in STATUSSEN for k in v): (slecht if any(k in STATUSSEN for k in v) else leeg).append(f"{wk} {p} {d}")
    if slecht: add("statussen", 1, "Alle statussen zijn geldig", "let", f"{len(slecht)} cellen met een onbekende status (bijv. {slecht[0]})")
    elif leeg: add("statussen", 1, "Alle statussen zijn geldig", "let", f"{len(leeg)} cellen bestaan alleen uit een onbekende status (bijv. {leeg[0]})")
    else: add("statussen", 1, "Alle statussen zijn geldig", "ok", "alle cellen hebben een geldige status")
    wees = sum(1 for wk, l in s.get("manuallyEdited", {}).items() for k in (l if wk in s["store"] else [None]) if k is None or split(k)[0] not in team or split(k)[1] not in DAGEN)
    add("manueel", 1, "Handmatige markeringen kloppen", "let" if wees else "ok", f"{wees} {'markering verwijst' if wees == 1 else 'markeringen verwijzen'} naar een week, persoon of dag die niet bestaat" if wees else "alle markeringen verwijzen naar bestaande dagen")
    vandaag = nu().astimezone(AMS).date(); half = {}
    for wk, l in s.get("manuallyEdited", {}).items():
        if wk not in s["store"] or not WEEKSLEUTEL.match(wk): continue
        for k in l:
            p, d = split(k)
            if p not in team or d not in DAGEN: continue
            v = s["store"][wk].get(p, {}).get(d)
            if v in (["vm_vrij"], ["nm_vrij"]):
                try: dag = dt.date.fromisocalendar(int(wk[:4]), int(wk[6:]), DAGEN.index(d) + 1)
                except ValueError: continue
                if dag >= vandaag: half[p] = half.get(p, 0) + 1
    add("halvedag", 1, "Halve dagen zijn aangevuld", "let" if half else "ok", ("nog niet aangevuld: " + ", ".join(f"{p} ({c})" for p, c in sorted(half.items())) + ". Zij krijgen de vraag zodra ze de pagina openen") if half else "alle halve dagen zijn aangevuld")
    oud = [wk for wk in s["store"] if WEEKSLEUTEL.match(wk) and (week_einde(wk) or dt.date.max) < grens()]
    add("oudeweken", 1, "Roosters ouder dan 2 maanden", "info" if oud else "ok", f"{len(oud)} {'week' if len(oud) == 1 else 'weken'} ouder dan 2 maanden; de server verwijdert ze in de volgende ronde" if oud else f"geen weken ouder dan 2 maanden (de oudste is {ks[0] if ks else '-'})")
    locked = parse_locked(pagina)
    if locked is None: add("verplicht", 1, "Verplichte vrije dagen staan op Vrij", "info", "de lijst met verplichte vrije dagen is niet te lezen uit de pagina")
    else:
        fout_v = sum(1 for wk in s["store"] for d in DAGEN if f"{wk}-{d}" in locked for p in team if p in s["store"][wk] and s["store"][wk][p].get(d) != ["vrij"]); dagen_v = sum(1 for wk in s["store"] for d in DAGEN if f"{wk}-{d}" in locked)
        add("verplicht", 1, "Verplichte vrije dagen staan op Vrij", "let" if fout_v else "ok", f"{fout_v} {'cel' if fout_v == 1 else 'cellen'} op een verplichte vrije dag {'staat' if fout_v == 1 else 'staan'} niet op Vrij (de server zet ze in de volgende ronde recht)" if fout_v else (f"{dagen_v} verplichte vrije dagen in de planning, voor iedereen Vrij" if dagen_v else "geen verplichte vrije dagen in de geladen weken"))
    kb = round(len(f["tekst"].encode("utf-8")) / 1024)
    add("grootte", 1, "Grootte van de planning", "fout" if kb > 900 else "let" if kb > 700 else "ok", f"{kb} KB van maximaal 1000 KB" + (": GitHub levert bestanden boven 1000 KB niet meer uit" if kb > 900 else ": de planning wordt te groot" if kb > 700 else ""))
    # team, accounts en rechten
    try:
        g = lees("groups.json"); lst = (json.loads(g["tekst"]).get("administrators") or []) if g else []
        echte = [a for a in lst if a in team]; vr = [a for a in lst if a not in team and a != MONITOR]
        if not echte: add("groups", 2, "Administrators", "fout", "geen enkele Administrator die teamlid is")
        elif vr: add("groups", 2, "Administrators", "let", "Administrators die niet in het team staan: " + ", ".join(vr))
        elif MONITOR not in lst: add("groups", 2, "Administrators", "let", "het Monitor-account staat niet als Administrator in de lijst")
        elif len(echte) < 2: add("groups", 2, "Administrators", "let", f"maar één Administrator ({echte[0]}): bij uitval kan niemand beheren")
        else: add("groups", 2, "Administrators", "ok", f"{len(echte)} Administrators ({', '.join(echte)}) en het Monitor-account")
    except Exception as e:
        add("groups", 2, "Administrators", "fout", f"groups.json niet leesbaar ({e})")
    try:
        u = lees("users.json"); acc = list((json.loads(u["tekst"]).get("users") or {}).keys()) if u else []
        w2 = [a for a in acc if a in NAMEN_WEG]; vr2 = [a for a in acc if a not in team and a != MONITOR and a not in NAMEN_WEG]
        eigen = [p for p in team if p in acc]
        if w2: add("accounts", 2, "Accounts", "fout", "account van een verwijderde naam: " + ", ".join(w2))
        elif vr2: add("accounts", 2, "Accounts", "let", "accounts van mensen die niet in het team staan: " + ", ".join(vr2))
        else: add("accounts", 2, "Accounts", "ok", f"{len(acc)} {'account' if len(acc) == 1 else 'accounts'}: {len(eigen)} van de {len(team)} teamleden {'heeft' if len(eigen) == 1 else 'hebben'} een eigen wachtwoord" + (", plus het Monitor-account" if MONITOR in acc else ""))
        zw = [p for p in team if p not in acc]
        add("wachtwoorden", 2, "Eigen wachtwoorden", "info" if zw else "ok", ("nog het startwachtwoord: " + ", ".join(zw)) if zw else "iedereen heeft een eigen wachtwoord")
    except Exception as e:
        add("accounts", 2, "Accounts", "fout", f"users.json niet leesbaar ({e})")
    try:
        st_ = lees("settings.json")
        if not st_: add("instellingen", 2, "Instellingen (boodschap en talen)", "ok", "nog niet aangemaakt: standaardwaarden gelden")
        else:
            d = json.loads(st_["tekst"]); sl = {p for k in ("talen", "personen", "campus", "monitor", "persoonlijk") for p in (d.get(k) or {})}
            w3 = sorted(p for p in sl if p in NAMEN_WEG); v3 = sorted(p for p in sl if p not in team and p != MONITOR and p not in NAMEN_WEG)
            if w3: add("instellingen", 2, "Instellingen (boodschap en talen)", "let", "instellingen van een verwijderde naam: " + ", ".join(w3))
            elif v3: add("instellingen", 2, "Instellingen (boodschap en talen)", "let", "instellingen voor mensen die niet in het team staan: " + ", ".join(v3))
            else: add("instellingen", 2, "Instellingen (boodschap en talen)", "ok", "leesbaar en alleen voor het team")
    except Exception as e:
        add("instellingen", 2, "Instellingen (boodschap en talen)", "fout", f"settings.json niet leesbaar ({e})")
    vj = parse_verjaardagen(pagina)
    if vj is None: add("verjaardagen", 2, "Verjaardag bekend voor iedereen", "info", "de verjaardagen zijn niet te lezen uit de pagina")
    else:
        def md_ok(v):
            try: dt.date(2024, int(v[:2]), int(v[3:])); return True   # 2024 is een schrikkeljaar: 29 februari mag
            except ValueError: return False
        ontbr = [p for p in team if p not in vj]; ongl = [p for p in team if p in vj and not md_ok(vj[p])]
        if ontbr or ongl: add("verjaardagen", 2, "Verjaardag bekend voor iedereen", "let", "; ".join(x for x in ((("geen verjaardag bekend voor " + ", ".join(ontbr)) if ontbr else ""), (("ongeldige verjaardag voor " + ", ".join(ongl)) if ongl else "")) if x))
        else: add("verjaardagen", 2, "Verjaardag bekend voor iedereen", "ok", f"alle {len(team)} teamleden")
    # backups en logboek
    add("serveronderhoud", 3, "Serveronderhoud (taak op GitHub)", "fout" if problemen else "ok", ("de laatste ronde meldde een probleem: " + "; ".join(problemen)[:300]) if problemen else ("de server draait" + (f"; deze ronde: {len(acties)} {'actie' if len(acties) == 1 else 'acties'}" if acties else "; niets te doen")))
    if not items: add("backups", 3, "Backups aanwezig", "fout", "er zijn geen backups")
    else:
        nm = items[-1]["name"][:-5].replace("_", " "); nm = nm[:-3] + ":" + nm[-2:]
        add("backups", 3, "Backups aanwezig", "let" if len(items) > 80 else "ok", f"{len(items)} backups: dat worden er veel (oude worden niet automatisch opgeruimd)" if len(items) > 80 else f"{len(items)} {'backup' if len(items) == 1 else 'backups'}, de nieuwste van {nm}")
        if not nieuwste: add("backup_actueel", 3, "Laatste backup bevat de laatste opslag", "let", "de nieuwste backup is niet leesbaar")
        elif planning_hash(nieuwste) == planning_hash(s): add("backup_actueel", 3, "Laatste backup bevat de laatste opslag", "ok", "gelijk aan de huidige planning")
        else:
            _LAATSTE.clear(); ts = laatste_opslag_tijd(s)
            if ts and (nu() - ts).total_seconds() < ACHTERSTAND_MIN * 60: add("backup_actueel", 3, "Laatste backup bevat de laatste opslag", "ok", "loopt iets achter op de laatste opslag (normaal: de server maakt een backup zodra er 5 minuten niets is gewijzigd)")
            else: add("backup_actueel", 3, "Laatste backup bevat de laatste opslag", "let", "de planning is gewijzigd sinds de nieuwste backup")
        slecht_b = []
        for it in items[-3:]:
            b = lees(f"backups/{it['name']}"); r = backup_oordeel(b["tekst"], n) if b else "niet leesbaar"
            if r: slecht_b.append(f"{it['name'][:-5]} ({r})")
        add("backup_geldig", 3, "Nieuwste backups zijn in orde", "fout" if slecht_b else "ok", ("beschadigd: " + "; ".join(slecht_b)) if slecht_b else f"de {min(3, len(items))} nieuwste backups zijn leesbaar en volledig")
    try:
        cut_b2 = (nu() - dt.timedelta(days=BACKUP_BEWAAR_DAGEN)).strftime("%Y-%m-%d"); n_oud_b = sum(1 for it in items if it["name"][:10] < cut_b2)
        add("backups_termijn", 3, f"Backups binnen de bewaartermijn ({BACKUP_BEWAAR_DAGEN} dagen)", "info" if n_oud_b else "ok", f"{n_oud_b} {'backup is' if n_oud_b == 1 else 'backups zijn'} ouder dan {BACKUP_BEWAAR_DAGEN} dagen; de server ruimt ze in de volgende ronde op" if n_oud_b else f"geen backups ouder dan {BACKUP_BEWAAR_DAGEN} dagen")
        cut_a2 = (nu() - dt.timedelta(days=AUDIT_BEWAAR_DAGEN)).strftime("%Y-%m-%d"); n_oud_a = sum(1 for it in lijst("audit") if re.match(r"^\d{4}-\d\d-\d\d\.jsonl$", it["name"]) and it["name"][:10] < cut_a2)
        add("logboek_termijn", 3, f"Logboek binnen de bewaartermijn ({AUDIT_BEWAAR_DAGEN} dagen)", "info" if n_oud_a else "ok", f"{n_oud_a} {'dagbestand is' if n_oud_a == 1 else 'dagbestanden zijn'} ouder dan {AUDIT_BEWAAR_DAGEN} dagen; de server ruimt ze in de volgende ronde op" if n_oud_a else f"geen dagbestanden ouder dan {AUDIT_BEWAAR_DAGEN} dagen")
    except Exception as e:
        add("backups_termijn", 3, f"Backups binnen de bewaartermijn ({BACKUP_BEWAAR_DAGEN} dagen)", "info", f"niet te controleren ({e})")
    add("logboek_server", 3, "Wijzigingsregels worden door de server geschreven", "ok" if LOG_STATUS["ok"] else "fout", "de server zet elke wijziging van de planning in het logboek (de pagina schrijft alleen bezoeken en inloggen)" if LOG_STATUS["ok"] else f"het logboek van wijzigingen is niet bijgewerkt: {LOG_STATUS['fout']}")
    try:
        buiten = []
        for dag in (nu() - dt.timedelta(days=1), nu()):
            fa = lees(f"audit/{dag.strftime('%Y-%m-%d')}.jsonl")
            for l in (fa["tekst"] if fa else "").split("\n"):
                try: e = json.loads(l)
                except Exception: continue
                if e.get("buiten_app") and dt.datetime.fromisoformat(e["t"].replace("Z", "+00:00")) >= nu() - dt.timedelta(hours=24): buiten.append(e)
        add("logboek_onbekend", 3, "Wijzigingen zonder bekende gebruiker (24 uur)", "let" if buiten else "ok", f"{len(buiten)} {'wijziging' if len(buiten) == 1 else 'wijzigingen'} zonder bekende gebruiker, mogelijk buiten de app gedaan (het token staat in de pagina): kijk in het logboek bij 'onbekend'" if buiten else "alle wijzigingen van de laatste 24 uur hebben een bekende gebruiker")
    except Exception as e:
        add("logboek_onbekend", 3, "Wijzigingen zonder bekende gebruiker (24 uur)", "info", f"niet te controleren ({e})")
    try:
        a = lees(f"audit/{nu().strftime('%Y-%m-%d')}.jsonl")
        if not a: add("logboek", 3, "Logboek van vandaag is leesbaar", "ok", "nog geen regels vandaag")
        else:
            regels = [l for l in a["tekst"].split("\n") if l.strip()]; kapot = 0
            for l in regels:
                try: json.loads(l)
                except Exception: kapot += 1
            add("logboek", 3, "Logboek van vandaag is leesbaar", "let" if kapot else "ok", f"{kapot} van de {len(regels)} regels van vandaag zijn kapot" if kapot else f"{len(regels)} regels, allemaal leesbaar")
    except Exception as e:
        add("logboek", 3, "Logboek van vandaag is leesbaar", "let", f"niet te lezen ({e})")
    return uit


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
    audit_oud = None; audit_ptr = None; audit_meld = []
    try:
        vs = lees("onderhoud.json"); audit_oud = (json.loads(vs["tekst"]) if vs else {}).get("audit_commit")
    except Exception:
        audit_oud = None
    audit_ptr = audit_oud
    try:
        regels_w, ptr_nieuw, audit_meld = log_wijzigingen(audit_oud)
        if DROOG or ALLEEN_LEZEN:
            if regels_w: audit_meld.append(f"{'droogloop' if DROOG else 'alleen lezen'}: {len(regels_w)} wijzigingsregels zouden in het logboek worden gezet")
        else:
            log_schrijf_dagen(regels_w); audit_ptr = ptr_nieuw
        LOG_STATUS.update({"ok": True, "fout": None})
    except Exception as e:
        audit_meld = audit_meld + [f"het logboek van wijzigingen is niet bijgewerkt ({e})"]; LOG_STATUS.update({"ok": False, "fout": str(e)})
    acties = problemen = meldingen = extra = None
    for poging in range(3):
        try:
            acties, problemen, meldingen, extra = ronde(); break
        except Conflict as e:
            print(f"gelijktijdige wijziging ({e}); opnieuw proberen", file=sys.stderr); time.sleep(2 + random.random() * 3)
    else:
        acties, problemen, meldingen, extra = [], ["er is steeds tegelijk een andere wijziging binnengekomen: niets gewijzigd, volgende ronde opnieuw"], [], {}
    meldingen = (meldingen or []) + config_meldingen + audit_meld
    extra = dict(extra or {}); extra["audit_commit"] = audit_ptr
    checks = []
    try:
        checks = controles(acties or [], problemen or [])
        try:
            vorig_st = lees("onderhoud.json"); vorige = json.loads(vorig_st["tekst"]) if vorig_st else {}
        except Exception:
            vorige = {}
        eerder_fout = {c["id"] for c in (vorige.get("checks") or []) if c["s"] == "fout"}
        for c in checks:
            if c["s"] == "fout" and c["id"] not in eerder_fout and c["id"] != "serveronderhoud":
                problemen = (problemen or []) + [f"controle '{c['naam']}': {c['t']}"]
    except Exception as e:
        meldingen.append(f"de controles zijn niet gelukt ({e})")
    log_schrijf([log_regel("onderhoud: " + a) for a in acties] + [log_regel("onderhoud: PROBLEEM: " + p) for p in problemen])
    try:
        schrijf_status(acties, problemen, meldingen, extra or {}, checks)
    except Exception as e:
        print(f"let op: het statusbestand kon niet worden geschreven ({e})", file=sys.stderr)
    print(json.dumps({"acties": acties, "problemen": problemen, "meldingen": meldingen, "droog": DROOG}, ensure_ascii=False, indent=1))
    sys.exit(1 if problemen else 0)


if __name__ == "__main__":
    main()
