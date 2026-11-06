#!/usr/bin/env python3
"""Logboek van bezoeken en inloggen van Bezetting Teams.

De site is statisch en het inloggen wordt in de browser gecontroleerd, dus een server ziet een bezoek of een inlog niet zelf. De pagina meldt ze daarom
aan GitHub (repository_dispatch, type 'logboek'); deze taak schrijft ze met de TIJD VAN GITHUB in audit/<dag>.jsonl. Wie of welk apparaat het was,
blijft wat de pagina meldt (alle gebruikers delen een token, de server kan dat niet bewijzen). De wijzigingen van de planning staan niet hier:
die leidt onderhoud.py af uit de opslagen zelf.
"""
import json, os, random, re, sys, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import onderhoud as O   # dezelfde hulpfuncties (lezen, schrijven, tijd); main() van onderhoud.py draait niet bij het importeren

MAX_EVENTS = 25            # hooguit zoveel meldingen per keer (de pagina stuurt er niet meer dan 20)
ANON_VENSTER_MIN = 10      # iemand zonder naam kan het logboek niet vullen: hooguit 3 regels per 10 minuten (en 3 blokkades)
ANON_MAX = 3
AFWIJKING_S = 120          # het tijdstip van het apparaat bewaren we alleen als het meer dan 2 minuten afwijkt
EID = re.compile(r"^[A-Za-z0-9_\-]{6,48}$")


def tekst(v, lengte):
    return v.strip()[:lengte] if isinstance(v, str) else ""


def schoon(e, nu):
    """Een melding van de pagina omzetten naar een logregel (alleen bekende velden, begrensde lengtes) of None."""
    if not isinstance(e, dict):
        return None
    actie = tekst(e.get("action"), 200)
    if not actie:
        return None
    eid = e.get("eid") if isinstance(e.get("eid"), str) and EID.match(e["eid"]) else "dsp-" + "".join(random.choice("0123456789abcdef") for _ in range(12))
    regel = {"v": 1, "eid": eid, "t": nu.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "user": tekst(e.get("user"), 60) or "onbekend", "ws": tekst(e.get("ws"), 80), "device": tekst(e.get("device"), 40),
             "id": tekst(e.get("id"), 100), "wsinfo": tekst(e.get("wsinfo"), 160), "action": actie, "n": 0, "trunc": False, "changes": [], "bron": "dispatch"}
    try:
        t_app = dt.datetime.fromisoformat(str(e.get("t")).replace("Z", "+00:00"))
        if abs((nu - t_app).total_seconds()) > AFWIJKING_S:
            regel["t_apparaat"] = t_app.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        pass
    if e.get("anon") is True:
        regel["anon"] = True
        if e.get("blok") is True:
            regel["blok"] = True
    return regel


def main():
    pad = os.environ.get("GITHUB_EVENT_PATH")
    try:
        ev = json.load(open(pad, encoding="utf-8")) if pad else {}
    except Exception as e:
        print(f"de melding is niet te lezen ({e})"); return 0
    events = (ev.get("client_payload") or {}).get("events")
    if not isinstance(events, list) or not events:
        print("geen meldingen in de aanvraag"); return 0
    nu = O.nu(); regels = [r for r in (schoon(e, nu) for e in events[:MAX_EVENTS]) if r]
    if not regels:
        print("geen geldige meldingen"); return 0
    if O.ALLEEN_LEZEN:
        print(f"alleen lezen: {len(regels)} regels zouden worden geschreven"); return 0
    # beperking voor regels zonder naam (zoals de pagina die zelf deed): hooguit 3 per 10 minuten, en 3 blokkades van een apparaat
    if any(r.get("anon") for r in regels):
        f = O.lees(f"audit/{nu.strftime('%Y-%m-%d')}.jsonl"); recent = []
        for l in (f["tekst"] if f else "").split("\n"):
            try: e = json.loads(l)
            except Exception: continue
            try: ok = e.get("anon") and (nu - dt.datetime.fromisoformat(e["t"].replace("Z", "+00:00"))).total_seconds() < ANON_VENSTER_MIN * 60
            except Exception: ok = False
            if ok: recent.append(e)
        ruimte = ANON_MAX - sum(1 for e in recent if not e.get("blok")); ruimte_blok = ANON_MAX - sum(1 for e in recent if e.get("blok")); toe = []
        for r in regels:
            if not r.get("anon"): toe.append(r)
            elif r.get("blok"):
                if ruimte_blok > 0: ruimte_blok -= 1; toe.append(r)
            elif ruimte > 0: ruimte -= 1; toe.append(r)
        regels = toe
    if not regels:
        print("niets te schrijven (de beperking voor regels zonder naam)"); return 0
    O.log_schrijf_dagen(regels)
    print(f"{len(regels)} regels in het logboek gezet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
