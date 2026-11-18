import sqlite3
from datetime import datetime, timedelta, timezone
import requests
import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson

st.set_page_config(page_title="World Football Predictor Pro", page_icon="⚽", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at 18% 15%, rgba(16,185,129,0.18), transparent 42%),
                radial-gradient(circle at 85% 20%, rgba(56,189,248,0.14), transparent 40%),
                linear-gradient(145deg, #040d0a 0%, #091722 50%, #050c14 100%);
    color: #f1f5f9;
}
[data-testid="stHeader"] { background: rgba(4,13,10,0.55); backdrop-filter: blur(8px); }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #06131a 0%, #081c18 100%); border-right: 1px solid rgba(16,185,129,0.25); }
.hero-banner { background: linear-gradient(120deg, rgba(16,185,129,0.20), rgba(15,23,42,0.85)); border: 1px solid rgba(52,211,153,0.35); border-radius: 14px; padding: 14px 18px; margin-bottom: 14px; }
.glass-card { background: rgba(10,22,30,0.80); border: 1px solid rgba(52,211,153,0.25); border-radius: 12px; padding: 12px 16px; margin-bottom: 10px; }
[data-testid="stMetric"] { background: rgba(12,27,36,0.85); border: 1px solid rgba(52,211,153,0.25); border-radius: 10px; padding: 8px 10px; }
.stButton > button { background: linear-gradient(90deg, #059669, #10b981); color: #fff; border: none; border-radius: 8px; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# --- 1. COMPETITIONS ---
ESPN_CUPS = {
    "🏆 UEFA Champions League": "uefa.champions", "🟠 UEFA Europa League": "uefa.europa",
    "🟢 UEFA Conference League": "uefa.europa.conf", "🇪🇺 UEFA Nations League": "uefa.nations",
    "🇪🇸 Spain - Copa del Rey": "esp.copa_del_rey", "🇩🇪 Germany - DFB Pokal": "ger.dfb_pokal",
    "🌍 FIFA World Cup": "fifa.world", "🌍 CAF AFCON": "caf.nations",
    "🌏 AFC Champions League": "afc.champions", "🌎 Copa Libertadores": "conmebol.libertadores",
    "🌎 Copa Sudamericana": "conmebol.sudamericana",
}
MAIN_LEAGUES = {
    "🇬🇧 England - Premier League": "E0", "🇬🇧 England - Championship": "E1", "🇬🇧 England - League 1": "E2",
    "🇬🇧 England - League 2": "E3", "🇬🇧 England - National League": "EC", "🏴 Scotland - Premiership": "SC0",
    "🏴 Scotland - Championship": "SC1", "🇪🇸 Spain - La Liga": "SP1", "🇪🇸 Spain - Segunda": "SP2",
    "🇩🇪 Germany - Bundesliga": "D1", "🇩🇪 Germany - 2. Bundesliga": "D2", "🇮🇹 Italy - Serie A": "I1",
    "🇮🇹 Italy - Serie B": "I2", "🇫🇷 France - Ligue 1": "F1", "🇫🇷 France - Ligue 2": "F2",
    "🇳🇱 Netherlands - Eredivisie": "N1", "🇧🇪 Belgium - Pro League": "B1", "🇵🇹 Portugal - Liga": "P1",
    "🇹🇷 Turkey - Super Lig": "T1", "🇬🇷 Greece - Super League": "G1",
}
WORLD_LEAGUES = {
    "🇦🇷 Argentina - Primera": "ARG", "🇧🇷 Brazil - Serie A": "BRA", "🇺🇸 USA - MLS": "USA",
    "🇲🇽 Mexico - Liga MX": "MEX", "🇯🇵 Japan - J-League": "JPN", "🇨🇳 China - Super League": "CHN",
    "🇦🇹 Austria - Bundesliga": "AUT", "🇩🇰 Denmark - Superliga": "DNK", "🇫🇮 Finland - Veikkausliiga": "FIN",
    "🇮🇪 Ireland - Premier": "IRL", "🇳🇴 Norway - Eliteserien": "NOR", "🇵🇱 Poland - Ekstraklasa": "POL",
    "🇷🇴 Romania - Liga 1": "ROU", "🇷🇺 Russia - Premier": "RUS", "🇸🇪 Sweden - Allsvenskan": "SWE",
    "🇨🇭 Switzerland - Super League": "SWZ",
}

# --- 2. SQLITE BET TRACKER ---
def init_db():
    conn = sqlite3.connect("my_bets.db")
    conn.execute("CREATE TABLE IF NOT EXISTS bets (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, league TEXT, match_name TEXT, tip TEXT, confidence INTEGER, odds REAL, stake REAL, status TEXT DEFAULT 'Pending', profit REAL DEFAULT 0.0)")
    conn.commit(); conn.close()

def save_bet(league, match_name, tip, conf, odds, stake):
    conn = sqlite3.connect("my_bets.db")
    conn.execute("INSERT INTO bets (date, league, match_name, tip, confidence, odds, stake) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (datetime.now().strftime("%Y-%m-%d %H:%M"), league, match_name, tip, conf, odds, stake))
    conn.commit(); conn.close()

def update_bet(bet_id, status):
    conn = sqlite3.connect("my_bets.db")
    row = conn.execute("SELECT odds, stake FROM bets WHERE id = ?", (bet_id,)).fetchone()
    if row:
        odds, stake = row
        profit = round(stake * (odds - 1), 2) if status == "Won" else (-stake if status == "Lost" else 0.0)
        conn.execute("UPDATE bets SET status = ?, profit = ? WHERE id = ?", (status, profit, bet_id))
        conn.commit()
    conn.close()

def load_bets():
    conn = sqlite3.connect("my_bets.db")
    df = pd.read_sql_query("SELECT * FROM bets ORDER BY id DESC", conn)
    conn.close(); return df

init_db()

# --- 3. DATA LOADERS ---
@st.cache_data(ttl=1800)
def load_espn(slug):
    base = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"
    seen, fin, up = set(), [], []
    for w in [None, "20260801-20270131", "20260101-20260731", "20250801-20251231"]:
        try:
            r = requests.get(base if w is None else f"{base}?dates={w}&limit=400", headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            if r.status_code != 200: continue
            for ev in r.json().get("events", []):
                eid = ev.get("id")
                if eid in seen: continue
                seen.add(eid)
                comp = (ev.get("competitions") or [{}])[0]
                cs = comp.get("competitors") or []
                hc = next((c for c in cs if c.get("homeAway") == "home"), None)
                ac = next((c for c in cs if c.get("homeAway") == "away"), None)
                if not hc or not ac: continue
                hn, an = (hc.get("team") or {}).get("displayName"), (ac.get("team") or {}).get("displayName")
                if not hn or not an: continue
                dt = (ev.get("date") or "")[:10]
                state = ((comp.get("status") or {}).get("type") or {}).get("state", "")
                if state == "post":
                    try: fin.append({"Date": dt, "HomeTeam": hn, "AwayTeam": an, "FTHG": int(float(hc.get("score") or 0)), "FTAG": int(float(ac.get("score") or 0))})
                    except (ValueError, TypeError): pass
                elif state == "pre":
                    up.append((dt, hn, an))
        except Exception: pass
    df = pd.DataFrame(fin)
    if not df.empty:
        df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("DateParsed").reset_index(drop=True)
    return df, sorted(set(up), key=lambda x: x[0])[:35], ""

@st.cache_data(ttl=3600)
def load_main_csv(code):
    frames = []
    for s in ["2526", "2627"]:
        try:
            d = pd.read_csv(f"https://www.football-data.co.uk/mmz4281/{s}/{code}.csv", encoding="latin1")
            frames.append(d.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"]))
        except Exception: pass
    if not frames: return pd.DataFrame(), [], "Could not download CSV."
    full = pd.concat(frames, ignore_index=True)
    full["FTHG"], full["FTAG"] = full["FTHG"].astype(int), full["FTAG"].astype(int)
    full["DateParsed"] = pd.to_datetime(full["Date"], dayfirst=True, errors="coerce")
    return full.sort_values("DateParsed").reset_index(drop=True), [], ""

@st.cache_data(ttl=3600)
def load_world_csv(code):
    try:
        d = pd.read_csv(f"https://www.football-data.co.uk/new/{code}.csv", encoding="latin1")
        d = d.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG"}).dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"]).tail(800)
        d["FTHG"], d["FTAG"] = d["FTHG"].astype(int), d["FTAG"].astype(int)
        d["DateParsed"] = pd.to_datetime(d["Date"], dayfirst=True, errors="coerce")
        return d.sort_values("DateParsed").reset_index(drop=True), [], ""
    except Exception: return pd.DataFrame(), [], "Could not download CSV."

@st.cache_data(ttl=3600)
def search_goal_leagues(query, key):
    try:
        r = requests.get("https://api.goal-api.com/v1/leagues", params={"search": query, "limit": 50}, headers={"Authorization": f"Bearer {key.strip()}"}, timeout=15)
        return r.json().get("data", []) if r.status_code == 200 else []
    except Exception: return []

@st.cache_data(ttl=1800)
def load_goal_fixtures(league_id, key):
    headers = {"Authorization": f"Bearer {key.strip()}"}
    all_items, ok, last_err = [], False, ""
    now = datetime.now(timezone.utc)
    plan = [
        (f"https://api.goal-api.com/v1/leagues/{league_id}/fixtures", {"limit": 100}),
        (f"https://api.goal-api.com/v1/leagues/{league_id}/results", {"limit": 100}),
        ("https://api.goal-api.com/v1/fixtures", {"leagueId": league_id, "from": (now - timedelta(days=90)).strftime("%Y-%m-%d"), "to": (now + timedelta(days=21)).strftime("%Y-%m-%d"), "limit": 100}),
    ]
    for url, bp in plan:
        for offset in [0, 100]:
            try:
                r = requests.get(url, params={**bp, "offset": offset}, headers=headers, timeout=15)
                if r.status_code == 401: return pd.DataFrame(), [], "❌ Invalid GOAL API key."
                if r.status_code != 200: last_err = f"API {r.status_code}"; break
                ok = True; p = r.json(); items = p.get("data") or []; all_items.extend(items)
                if not (p.get("pagination") or {}).get("hasMore", False) or len(items) < 100: break
            except Exception as e: last_err = str(e); break
    fin, up, sf, su = [], [], set(), set()
    for m in all_items:
        h = (m.get("homeTeam") or {}).get("name") or m.get("homeTeamName")
        a = (m.get("awayTeam") or {}).get("name") or m.get("awayTeamName")
        if not h or not a: continue
        dt = (m.get("kickoffUtc") or m.get("matchDate") or "")[:10]
        hs = m.get("homeScore") if m.get("homeScore") is not None else m.get("homeTeamScore")
        as_ = m.get("awayScore") if m.get("awayScore") is not None else m.get("awayTeamScore")
        per, stt = str(m.get("matchPeriod") or "").upper(), str(m.get("matchStatus") or "").upper()
        is_fin = per == "FINISHED" or stt in ("FINISHED", "FT", "AET", "PEN", "AFTER PEN.", "PLAYED")
        is_up = per in ("NOT_STARTED", "SCHEDULED") or stt in ("SCHEDULED", "NOT_STARTED", "NS", "TIMED", "UPCOMING", "")
        if hs is not None and as_ is not None and (is_fin or (not is_up and per != "NOT_STARTED")):
            try:
                if (dt, h, a) not in sf:
                    sf.add((dt, h, a)); fin.append({"Date": dt, "HomeTeam": h, "AwayTeam": a, "FTHG": int(float(hs)), "FTAG": int(float(as_))})
            except (ValueError, TypeError): pass
        elif not is_fin and (dt, h, a) not in su:
            su.add((dt, h, a)); up.append((dt, h, a))
    df = pd.DataFrame(fin)
    if not df.empty:
        df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("DateParsed").reset_index(drop=True)
    return df, sorted(up, key=lambda x: x[0])[:40], ("" if ok else last_err)

# --- 4. STATS & POISSON ENGINE ---
def get_metrics(df, team, venue="all", last_n=5):
    base = {"form": "-", "gf": 1.2, "ga": 1.2, "o15": 60, "o25": 45, "o35": 20, "btts": 50, "corners": 0.0, "shots_ot": 0.0, "power": 50.0}
    if df.empty: return base
    if venue == "home": g = df[df["HomeTeam"] == team].tail(last_n)
    elif venue == "away": g = df[df["AwayTeam"] == team].tail(last_n)
    else: g = df[(df["HomeTeam"] == team) | (df["AwayTeam"] == team)].tail(last_n)
    if g.empty: return base
    fm, gf_t, ga_t, o15, o25, o35, btts, ct, stt, pts = [], 0, 0, 0, 0, 0, 0, 0, 0, 0
    hc, hs = "HC" in g.columns and "AC" in g.columns, "HST" in g.columns and "AST" in g.columns
    for _, r in g.iterrows():
        ih = r["HomeTeam"] == team
        gf, ga = (r["FTHG"], r["FTAG"]) if ih else (r["FTAG"], r["FTHG"])
        gf_t += gf; ga_t += ga; tot = gf + ga
        if gf > ga: fm.append("W"); pts += 3
        elif gf == ga: fm.append("D"); pts += 1
        else: fm.append("L")
        if tot > 1: o15 += 1
        if tot > 2: o25 += 1
        if tot > 3: o35 += 1
        if gf > 0 and ga > 0: btts += 1
        if hc and pd.notna(r["HC"]) and pd.notna(r["AC"]): ct += r["HC"] if ih else r["AC"]
        if hs and pd.notna(r["HST"]) and pd.notna(r["AST"]): stt += r["HST"] if ih else r["AST"]
    n = len(g)
    pwr = float(np.clip((pts / (n * 3)) * 65 + ((gf_t - ga_t) / n) * 10 + 18, 10, 99))
    return {"form": "".join(fm), "gf": round(gf_t/n, 2), "ga": round(ga_t/n, 2), "o15": round(o15/n*100),
            "o25": round(o25/n*100), "o35": round(o35/n*100), "btts": round(btts/n*100),
            "corners": round(ct/n, 1) if hc else 0.0, "shots_ot": round(stt/n, 1) if hs else 0.0, "power": round(pwr, 1)}

def get_h2h(df, home, away):
    if df.empty: return pd.DataFrame()
    h = df[((df["HomeTeam"] == home) & (df["AwayTeam"] == away)) | ((df["HomeTeam"] == away) & (df["AwayTeam"] == home))].tail(5)
    return pd.DataFrame() if h.empty else h[["Date", "HomeTeam", "FTHG", "FTAG", "AwayTeam"]].iloc[::-1]

def analyze_fixture(df, home, away, o1=1.85, ox=3.50, o2=4.20):
    ha, aa = get_metrics(df, home, "all", 15), get_metrics(df, away, "all", 15)
    h5, a5 = get_metrics(df, home, "home", 5), get_metrics(df, away, "away", 5)
    if h5["form"] == "-" and ha["form"] != "-": h5 = ha
    if a5["form"] == "-" and aa["form"] != "-": a5 = aa
    ahg = max(float(df["FTHG"].mean()), 0.5) if not df.empty else 1.35
    aag = max(float(df["FTAG"].mean()), 0.5) if not df.empty else 1.15
    eh = float(np.clip(((h5["gf"]*0.65 + ha["gf"]*0.35)/ahg) * ((a5["ga"]*0.65 + aa["ga"]*0.35)/ahg) * ahg, 0.25, 4.0))
    ea = float(np.clip(((a5["gf"]*0.65 + aa["gf"]*0.35)/aag) * ((h5["ga"]*0.65 + ha["ga"]*0.35)/aag) * aag, 0.25, 4.0))
    mat = np.array([[poisson.pmf(i, eh) * poisson.pmf(j, ea) for j in range(7)] for i in range(7)])
    p1, px, p2 = float(np.sum(np.tril(mat, -1))), float(np.sum(np.diag(mat))), float(np.sum(np.triu(mat, 1)))
    p1x, px2, p12 = p1 + px, p2 + px, p1 + p2
    po05 = float(sum(mat[i, j] for i in range(7) for j in range(7) if i + j > 0))
    po15 = float(sum(mat[i, j] for i in range(7) for j in range(7) if i + j > 1))
    po25 = float(sum(mat[i, j] for i in range(7) for j in range(7) if i + j > 2))
    po35 = float(sum(mat[i, j] for i in range(7) for j in range(7) if i + j > 3))
    pu25, pu35 = 1.0 - po25, 1.0 - po35
    pbtts = float(sum(mat[i, j] for i in range(1, 7) for j in range(1, 7)))
    png = 1.0 - pbtts
    top_scores = [f"{np.unravel_index(k, mat.shape)[0]}:{np.unravel_index(k, mat.shape)[1]} ({mat.ravel()[k]*100:.0f}%)" for k in np.argsort(mat.ravel())[::-1][:3]]
    probs = {"1": p1, "X": px, "2": p2}
    bp = max(probs, key=probs.get); bprob = probs[bp]
    if bp == "1" and bprob < 0.52 and p1x >= 0.72: tip, cp = "1X", p1x
    elif bp == "2" and bprob < 0.52 and px2 >= 0.72: tip, cp = "X2", px2
    else: tip, cp = bp, bprob
    conf = int(np.clip(round((cp - 0.25) / 0.60 * 9 + 1), 1, 10))
    safes = {"1X": p1x, "X2": px2, "12": p12, "Over 1.5": po15, "Under 3.5": pu35}
    sname = max(safes, key=safes.get); sprob = safes[sname]
    if p1 >= 0.55 and po15 >= 0.68: combo = "1 & Over 1.5"
    elif p2 >= 0.55 and po15 >= 0.68: combo = "2 & Over 1.5"
    elif p1x >= 0.72 and pu35 >= 0.65: combo = "1X & Under 3.5"
    elif px2 >= 0.72 and pu35 >= 0.65: combo = "X2 & Under 3.5"
    elif po25 >= 0.55 and pbtts >= 0.55: combo = "Over 2.5 & BTTS"
    else: combo = f"{tip} & {'Over 1.5' if po15 >= 0.65 else 'Under 3.5'}"
    evs = {"1": p1*o1 - 1, "X": px*ox - 1, "2": p2*o2 - 1}
    bevs = max(evs, key=evs.get); bev = evs[bevs]
    tags = []
    if conf >= 8 and {"1": o1, "X": ox, "2": o2}.get(bp, 1.45) <= 1.65: tags.append("🔒 Banker")
    if bev >= 0.05: tags.append(f"💎 Value ({bevs}: +{bev*100:.0f}% EV)")
    if px >= 0.29 and abs(h5["power"] - a5["power"]) <= 12: tags.append("⚖️ Draw Watch")
    verdict = f"{home} xG {eh:.2f} vs {away} {ea:.2f}. Safest: {sname} ({sprob*100:.0f}%) | Combo: {combo}."
    return {
        "Match": f"{home} vs {away}", "Tip": tip, "Conf": conf, "Safest": f"{sname} ({sprob*100:.0f}%)",
        "Combo": combo, "1": o1, "X": ox, "2": o2,
        "O/U 2.5": f"{'Over' if po25 >= 0.52 else 'Under'} ({po25*100:.0f}%)",
        "BTTS": f"{pbtts*100:.0f}%", "Score": top_scores[0].split(" ")[0],
        "Category": " | ".join(tags) if tags else "Standard",
        "_raw": {"home": home, "away": away, "eh": eh, "ea": ea, "p1": p1, "px": px, "p2": p2,
                 "p1x": p1x, "px2": px2, "p12": p12, "po05": po05, "po15": po15, "po25": po25,
                 "po35": po35, "pu25": pu25, "pu35": pu35, "pbtts": pbtts, "png": png,
                 "top_scores": top_scores, "sname": sname, "sprob": sprob, "combo": combo,
                 "verdict": verdict, "ev": evs, "h5": h5, "a5": a5},
    }

# --- 5. AI ADVISOR ---
def build_ctx(res, h2h, comp):
    r = res["_raw"]; h5, a5 = r["h5"], r["a5"]
    h2ht = "None" if h2h.empty else h2h.to_string(index=False)
    return (f"Comp: {comp} | Match: {res['Match']} | Odds 1={res['1']} X={res['X']} 2={res['2']}\n"
            f"xG: {r['home']} {r['eh']:.2f} - {r['ea']:.2f} {r['away']} | 1={r['p1']*100:.1f}% X={r['px']*100:.1f}% 2={r['p2']*100:.1f}%\n"
            f"DC: 1X={r['p1x']*100:.1f}% X2={r['px2']*100:.1f}% | O1.5={r['po15']*100:.1f}% O2.5={r['po25']*100:.1f}% BTTS={r['pbtts']*100:.1f}%\n"
            f"Safest: {res['Safest']} | Combo: {res['Combo']} | Scores: {', '.join(r['top_scores'])}\n"
            f"H-Last5: {h5['form']} Pwr={h5['power']} | A-Last5: {a5['form']} Pwr={a5['power']}\nH2H:\n{h2ht}")

def smart_advisor(res, q):
    r = res["_raw"]
    mkts = sorted([(f"{r['home']} (1)", r["p1"]), ("Draw (X)", r["px"]), (f"{r['away']} (2)", r["p2"]),
                   ("1X", r["p1x"]), ("X2", r["px2"]), ("Over 1.5", r["po15"]), ("Over 2.5", r["po25"]),
                   ("Under 2.5", r["pu25"]), ("Under 3.5", r["pu35"]), ("BTTS Yes", r["pbtts"]), ("BTTS No", r["png"])],
                  key=lambda x: x[1], reverse=True)
    bev_s = max(r["ev"], key=r["ev"].get); bev_v = r["ev"][bev_s]
    return (f"**Smart Analysis: {res['Match']}**\n\n"
            f"🎯 **Best Pick:** **{mkts[0][0]}** (`{mkts[0][1]*100:.1f}%`) | **Combo:** `{res['Combo']}`\n\n"
            f"1. **{mkts[0][0]}** — `{mkts[0][1]*100:.1f}%`\n2. **{mkts[1][0]}** — `{mkts[1][1]*100:.1f}%`\n3. **{mkts[2][0]}** — `{mkts[2][1]*100:.1f}%`\n\n"
            f"💎 **Best Value:** `{bev_s}` (`{bev_v*100:+.1f}%` EV) | **Scores:** {', '.join(r['top_scores'])}")
def ask_llm(provider, key, ctx, hist, q):
    sys_p = f"You are an expert football betting analyst. Use ONLY these stats to pick the best option, backup, and risk:\n{ctx}"
    k = key.strip()
    if provider == "Groq (Free AI)":
        msgs = [{"role": "system", "content": sys_p}] + [{"role": m["role"], "content": m["content"]} for m in hist[-6:]] + [{"role": "user", "content": q}]
        err = ""
        for m in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"}, json={"model": m, "messages": msgs, "temperature": 0.3}, timeout=25)
                if r.status_code == 200: return r.json()["choices"][0]["message"]["content"]
                err = f"Groq Error {r.status_code}: {r.text[:150]}"
            except Exception as e: err = str(e)
        return err
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in hist[-6:]] + [{"role": "user", "parts": [{"text": q}]}]
    err = ""
    for m in ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-flash-latest"]:
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}", headers={"Content-Type": "application/json"}, json={"system_instruction": {"parts": [{"text": sys_p}]}, "contents": contents, "generationConfig": {"temperature": 0.3}}, timeout=25)
            if r.status_code == 200: return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            err = f"Gemini Error {r.status_code}: {r.text[:150]}"
        except Exception as e: err = str(e)
    return err



# --- 6. SIDEBAR ---
if "daily_list" not in st.session_state: st.session_state.daily_list = []
if "ai_messages" not in st.session_state: st.session_state.ai_messages = []

st.sidebar.header("🌍 Select Competition")
mode = st.sidebar.radio("Category", [
    "🏆 UEFA, CAF, AFC, FIFA & Cups (No Key)",
    "⚽ 36 Global Leagues (No Key)",
    "🔎 All 1,000+ Competitions (GOAL API Key)",
])

df_league, upcoming_fixtures, selected_comp, load_err = pd.DataFrame(), [], "", ""

if mode == "🏆 UEFA, CAF, AFC, FIFA & Cups (No Key)":
    selected_comp = st.sidebar.selectbox("Tournament", list(ESPN_CUPS.keys()))
    custom = st.sidebar.text_input("Or custom ESPN slug", placeholder="e.g. eng.1, esp.1")
    slug = custom.strip() if custom.strip() else ESPN_CUPS[selected_comp]
    if custom.strip(): selected_comp = f"Custom ({slug})"
    df_league, upcoming_fixtures, load_err = load_espn(slug)
elif mode == "⚽ 36 Global Leagues (No Key)":
    all_l = {**MAIN_LEAGUES, **WORLD_LEAGUES}
    selected_comp = st.sidebar.selectbox("League", list(all_l.keys()))
    code = all_l[selected_comp]
    df_league, upcoming_fixtures, load_err = load_main_csv(code) if selected_comp in MAIN_LEAGUES else load_world_csv(code)
else:
    gkey = st.sidebar.text_input("GOAL API Key (goal-api.com)", type="password")
    qp = st.sidebar.selectbox("Presets", ["Custom Search", "Copa del Rey", "CAF Champions League", "NPFL", "UEFA Champions League", "UEFA Europa League", "AFC Champions League", "Saudi Pro League"])
    sq = st.sidebar.text_input("Search ANY Competition", value="" if qp == "Custom Search" else qp)
    if gkey and sq:
        found = search_goal_leagues(sq, gkey)
        if found:
            opts = {f"{x.get('name')} ({(x.get('country') or {}).get('name', 'Intl')})": x.get("id") for x in found}
            selected_comp = st.sidebar.selectbox("Pick Competition", list(opts.keys()))
            df_league, upcoming_fixtures, load_err = load_goal_fixtures(opts[selected_comp], gkey)
        else: st.sidebar.warning("No competition matched.")
    else: st.sidebar.info("Enter free key from goal-api.com")

st.sidebar.divider()
st.sidebar.header("🤖 AI Space Settings")
ai_prov = st.sidebar.selectbox("AI Engine", ["Built-in Smart Advisor (No Key)", "Groq (Free AI)", "Google Gemini (Free AI)"])
ai_key = st.sidebar.text_input("Paste Free AI Key", type="password") if ai_prov != "Built-in Smart Advisor (No Key)" else ""

# --- 7. MAIN INTERFACE ---
st.markdown('<div class="hero-banner"><h2 style="margin:0;color:#ecfdf5;">⚽ World Football Predictor Pro</h2><div style="color:#a7f3d0;font-size:0.9rem;">All Global Competitions • Full Analyzed Options • AI Betting Advisor</div></div>', unsafe_allow_html=True)

tab_board, tab_ai, tab_daily, tab_track = st.tabs(["🔍 Match Analyzer & All Games", "🤖 AI Space", "🔥 Daily Tips", "📒 Bet Tracker"])
cur_res, cur_h2h = None, pd.DataFrame()

with tab_board:
    if load_err: st.error(load_err)
    ht = (set(df_league["HomeTeam"].unique()) | set(df_league["AwayTeam"].unique())) if not df_league.empty else set()
    ut = {t for _, fh, fa in upcoming_fixtures for t in (fh, fa)}
    teams = sorted(ht | ut)

    if not teams:
        st.info("Open the sidebar (top-left arrow on phone) and pick a competition to view all matches & full analysis.")
    else:
        st.caption(f"**{selected_comp}** — Finished history: **{len(df_league)}** | Upcoming matches: **{len(upcoming_fixtures)}**")

        # ALL UPCOMING MATCHES AUTO-ANALYZED BOARD
        if upcoming_fixtures:
            st.subheader(f"📋 All Upcoming Matches — Fully Analyzed ({len(upcoming_fixtures)})")
            rows = []
            for dt, fh, fa in upcoming_fixtures:
                a = analyze_fixture(df_league, fh, fa)
                rows.append({"Date": dt, "Match": a["Match"], "Best Tip": f"{a['Tip']} ({a['Conf']}/10)",
                             "Safest Pick": a["Safest"], "Combo Option": a["Combo"], "O/U 2.5": a["O/U 2.5"],
                             "BTTS": a["BTTS"], "Score": a["Score"], "Verdict": a["_raw"]["verdict"]})
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            st.divider()

        st.subheader("🎯 Deep Match Analyzer & Custom Odds Check")
        dh, da = 0, min(1, len(teams) - 1)
        if upcoming_fixtures:
            labels = ["-- Pick Manually --"] + [f"{dt} | {h} vs {a}" for dt, h, a in upcoming_fixtures]
            pick = st.selectbox("📅 Auto-Select Any Match Above", labels)
            if pick != "-- Pick Manually --":
                _, fh, fa = upcoming_fixtures[labels.index(pick) - 1]
                if fh in teams and fa in teams: dh, da = teams.index(fh), teams.index(fa)

        c1, c2 = st.columns(2)
        home_t = c1.selectbox("Home Team", teams, index=dh)
        away_t = c2.selectbox("Away Team", teams, index=da)

        oc1, oc2, oc3, oc4 = st.columns([1, 1, 1, 1.3])
        o1 = oc1.number_input("Odds 1", min_value=1.01, value=1.85, step=0.05)
        ox = oc2.number_input("Odds X", min_value=1.01, value=3.50, step=0.05)
        o2 = oc3.number_input("Odds 2", min_value=1.01, value=4.20, step=0.05)
        stake = oc4.number_input("Stake", min_value=1.0, value=1000.0, step=100.0)

        if home_t != away_t:
            res = analyze_fixture(df_league, home_t, away_t, o1, ox, o2)
            raw = res["_raw"]; cur_res = res; cur_h2h = get_h2h(df_league, home_t, away_t)

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Best Tip", f"{res['Tip']} ({res['Conf']}/10)")
            m2.metric("Safest Pick", res["Safest"])
            m3.metric("Best Combo", res["Combo"])
            m4.metric("Goals & BTTS", f"{res['O/U 2.5']} | {res['BTTS']}")
            m5.metric("Exact Score", res["Score"])

            st.markdown(f'<div class="glass-card"><b>🧠 Full Verdict ({res["Category"]}):</b> {raw["verdict"]}<br><b>Top 3 Scores:</b> {", ".join(raw["top_scores"])}</div>', unsafe_allow_html=True)

            b1, b2 = st.columns(2)
            if b1.button("➕ Add to Daily Tips", use_container_width=True):
                rc = {k: v for k, v in res.items() if k != "_raw"}; rc["Competition"] = selected_comp
                st.session_state.daily_list.append(rc); st.success("Added!")
            podds = {"1": o1, "X": ox, "2": o2, "1X": round(1/(1/o1+1/ox), 2), "X2": round(1/(1/o2+1/ox), 2)}.get(res["Tip"], o1)
            if b2.button("💾 Save to Bet Tracker", use_container_width=True):
                save_bet(selected_comp, res["Match"], res["Tip"], res["Conf"], podds, stake); st.success("Saved!")

            st.markdown("**📊 All Analyzed Markets & Probabilities**")
            mk_df = pd.DataFrame({
                "Result Market": ["Home Win (1)", "Draw (X)", "Away Win (2)", "Double Chance 1X", "Double Chance X2", "Double Chance 12"],
                "Win %": [f"{raw['p1']*100:.1f}%", f"{raw['px']*100:.1f}%", f"{raw['p2']*100:.1f}%", f"{raw['p1x']*100:.1f}%", f"{raw['px2']*100:.1f}%", f"{raw['p12']*100:.1f}%"],
                "Goals Market": ["Over 0.5 Goals", "Over 1.5 Goals", "Over 2.5 Goals", "Under 2.5 Goals", "Under 3.5 Goals", "BTTS Yes (GG)"],
                "Goal %": [f"{raw['po05']*100:.1f}%", f"{raw['po15']*100:.1f}%", f"{raw['po25']*100:.1f}%", f"{raw['pu25']*100:.1f}%", f"{raw['pu35']*100:.1f}%", f"{raw['pbtts']*100:.1f}%"],
            })
            st.dataframe(mk_df, hide_index=True, use_container_width=True)

            ch, ca = st.columns(2)
            h5, a5 = raw["h5"], raw["a5"]
            ch.info(f"🏠 **{home_t} (L5 Home):** `{h5['form']}` | Power `{h5['power']}` | GF `{h5['gf']}` GA `{h5['ga']}` | Corners `{h5['corners']}`")
            ca.info(f"✈️ **{away_t} (L5 Away):** `{a5['form']}` | Power `{a5['power']}` | GF `{a5['gf']}` GA `{a5['ga']}` | Corners `{a5['corners']}`")
            if not cur_h2h.empty:
                st.markdown("**🤝 Recent Head-to-Head**")
                st.dataframe(cur_h2h, hide_index=True, use_container_width=True)
        else:
            st.warning("Select two different teams.")

with tab_ai:
    st.subheader("🤖 AI Betting Advisor Space")
    if cur_res is None:
        st.info("Select a match in **Match Analyzer** first.")
    else:
        st.success(f"**Active Match:** {cur_res['Match']} | Best Tip: `{cur_res['Tip']}` | Safest: `{cur_res['Safest']}` | Combo: `{cur_res['Combo']}`")
        ctx = build_ctx(cur_res, cur_h2h, selected_comp)
        qc = st.columns(4)
        qq = None
        if qc[0].button("🎯 Best Pick", use_container_width=True): qq = "Select the single best option and explain why."
        if qc[1].button("🔒 Safest Acca", use_container_width=True): qq = "What is the safest option for an accumulator?"
        if qc[2].button("💎 Value (+EV)", use_container_width=True): qq = "Which option gives the best value against my odds?"
        if qc[3].button("⚽ Goals/BTTS", use_container_width=True): qq = "Pick the best Over/Under or BTTS option."
        with st.form("ai_form", clear_on_submit=True):
            tq = st.text_input("Ask AI anything:", placeholder="e.g. Is 1X & Under 3.5 safe here?")
            sub = st.form_submit_button("Ask AI 🚀")
        prompt = qq if qq else (tq.strip() if sub and tq.strip() else None)
        if prompt:
            st.session_state.ai_messages.append({"role": "user", "content": prompt})
            with st.spinner("Analyzing..."):
                rep = smart_advisor(cur_res, prompt) if (ai_prov == "Built-in Smart Advisor (No Key)" or not ai_key.strip()) else ask_llm(ai_prov, ai_key, ctx, st.session_state.ai_messages[:-1], prompt)
            st.session_state.ai_messages.append({"role": "assistant", "content": rep})
        for m in reversed(st.session_state.ai_messages):
            with st.chat_message(m["role"]): st.markdown(m["content"])
        if st.session_state.ai_messages and st.button("🧹 Clear Chat"):
            st.session_state.ai_messages = []; st.rerun()

with tab_daily:
    st.subheader("🔥 Daily Curated Tips")
    if not st.session_state.daily_list:
        st.info("Click **Add to Daily Tips** on any match to build your card.")
    else:
        dd = pd.DataFrame(st.session_state.daily_list)
        st.dataframe(dd, hide_index=True, use_container_width=True)
        c1, c2, c3 = st.columns(3)
        c1.markdown("### 🔒 Bankers"); c1.dataframe(dd[dd["Category"].str.contains("Banker")][["Match", "Tip", "Conf"]], hide_index=True)
        c2.markdown("### 💎 Value"); c2.dataframe(dd[dd["Category"].str.contains("Value")][["Match", "Category", "Score"]], hide_index=True)
        c3.markdown("### ⚖️ Draws"); c3.dataframe(dd[dd["Category"].str.contains("Draw")][["Match", "X", "Score"]], hide_index=True)
        if st.button("🗑️ Clear Daily List"):
            st.session_state.daily_list = []; st.rerun()

with tab_track:
    st.subheader("📒 My Bet History & ROI")
    bdf = load_bets()
    if bdf.empty:
        st.info("No saved picks yet.")
    else:
        st_df = bdf[bdf["status"].isin(["Won", "Lost"])]
        stk = st_df["stake"].sum() if not st_df.empty else 0.0
        prf = st_df["profit"].sum() if not st_df.empty else 0.0
        wr = (len(st_df[st_df["status"] == "Won"]) / len(st_df) * 100) if not st_df.empty else 0.0
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Picks", len(bdf)); k2.metric("Win Rate", f"{wr:.1f}%")
        k3.metric("Profit/Loss", f"{prf:+,.2f}"); k4.metric("ROI", f"{(prf/stk*100 if stk>0 else 0.0):+.1f}%")
        st.divider()
        for _, row in bdf.iterrows():
            cols = st.columns([3, 1.5, 1, 1, 1.1, 1.1])
            cols[0].write(f"**{row['match_name']}** ({row['date']})")
            cols[1].write(f"`{row['tip']}` ({row['confidence']}/10) @ **{row['odds']}**")
            cols[2].write(f"{row['stake']:.0f}"); cols[3].write(f"**{row['status']}** ({row['profit']:+.0f})")
            if row["status"] == "Pending":
                if cols[4].button("✅ Won", key=f"w_{row['id']}"): update_bet(row["id"], "Won"); st.rerun()
                if cols[5].button("❌ Lost", key=f"l_{row['id']}"): update_bet(row["id"], "Lost"); st.rerun()
