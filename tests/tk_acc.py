import base64, json, sys
from playwright.sync_api import sync_playwright
HTML = open(sys.argv[1], encoding="utf-8").read(); UIT = []
def check(naam, ok, detail=""):
    UIT.append(("PASS  " if ok else "FAIL  ") + naam + ("" if ok else "   -> " + str(detail)[:500])); print(UIT[-1], flush=True)
TEAM = ["Wim", "Wouter", "Annies", "Bas", "Bram", "Marco", "Hans", "Sercan", "Ted", "Sam"]; S = {"users": None}
def handler(route, request):
    u = request.url; cors = {"access-control-allow-origin": "*"}
    if u.rstrip("/") == "https://buas-it.github.io/teamplanning-ict": return route.fulfill(status=200, content_type="text/html", body=HTML)
    if "/contents/users.json" in u and S["users"] is not None:
        return route.fulfill(status=200, headers=cors, content_type="application/json", body=json.dumps({"sha": "x", "encoding": "base64", "content": base64.b64encode(json.dumps({"v": 1, "users": {n: {"hash": "h"} for n in S["users"]}}).encode()).decode()}))
    return route.fulfill(status=404, headers=cors, content_type="application/json", body="{}")
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = b.new_context(timezone_id="UTC"); ctx.route("**/*", handler); p = ctx.new_page(); fouten = []; p.on("pageerror", lambda e: fouten.append(str(e)[:120]))
    p.goto("https://buas-it.github.io/teamplanning-ict/"); p.wait_for_timeout(2500); p.evaluate(f"TEAM.length = 0; TEAM.push(...{json.dumps(TEAM)})")
    def run(users): S["users"] = users; p.evaluate("CHK.net = null"); return p.evaluate("(async () => await CHECKS.find(c => c.id === 'accounts').run())()")
    r = run(["Bas", "Bram", "Hans", "Marco", "Monitor", "Sam", "Sercan"]); check("AC1 zoals nu: 6 teamleden met een eigen wachtwoord plus Monitor staat er duidelijk: '7 accounts: 6 van de 10 teamleden hebben een eigen wachtwoord, plus het Monitor-account'", r["s"] == "ok" and r["t"] == "7 accounts: 6 van de 10 teamleden hebben een eigen wachtwoord, plus het Monitor-account", json.dumps(r))
    r = run(TEAM + ["Monitor"]); check("AC2 hebben alle 10 teamleden een eigen wachtwoord: '11 accounts: 10 van de 10 teamleden hebben een eigen wachtwoord, plus het Monitor-account'", r["s"] == "ok" and r["t"] == "11 accounts: 10 van de 10 teamleden hebben een eigen wachtwoord, plus het Monitor-account", json.dumps(r))
    r = run(["Hans"]); check("AC3 bij een enkel account staat het enkelvoud: '1 account: 1 van de 10 teamleden heeft een eigen wachtwoord'", r["s"] == "ok" and r["t"] == "1 account: 1 van de 10 teamleden heeft een eigen wachtwoord", json.dumps(r))
    r = run(["Hans", "Zoveel", "Monitor"]); check("AC4 een account van iemand buiten het team blijft een aandachtspunt (let op)", r["s"] == "let" and "Zoveel" in r["t"], json.dumps(r))
    r = run(["Hans", "Dave"]); check("AC5 een account van een verwijderde naam blijft een fout", r["s"] == "fout" and "Dave" in r["t"], json.dumps(r))
    check("AC6 geen fouten in de pagina", not fouten, str(fouten[:2])); b.close()
print(f"\nklaar: {sum(1 for r in UIT if r.startswith('PASS'))} geslaagd, {sum(1 for r in UIT if r.startswith('FAIL'))} gefaald")
