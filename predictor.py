import json, sqlite3
from datetime import datetime, timedelta, timezone
import requests
import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson

ESPN_CUPS = {
    "🏆 UEFA Champions League": "uefa.champions", "🟠 UEFA Europa League": "uefa.europa",
    "🟢 UEFA Conference League": "uefa.europa.conf", "🇪🇺 UEFA Nations League": "uefa.nations",
    "🇪🇸 Spain - Copa del Rey": "esp.copa_del_rey", "🇩🇪 Germany - DFB Pokal": "ger.dfb_pokal",
    "🌍 FIFA World Cup": "fifa.world", "🌍 CAF AFCON": "caf.nations",
    "🌏 AFC Champions League": "afc.champions", "🌎 Copa Libertadores": "conmebol.libertadores",
    "🌎 Copa Sudamericana": "conmebol.sudamericana",
}
SCAN_LEAGUES = {
    "🇬🇧 Premier League": "eng.1", "🇬🇧 Championship": "eng.2",
    "🇪🇸 La Liga": "esp.1", "🇩🇪 Bundesliga": "ger.1",
    "🇮🇹 Serie A": "ita.1", "🇫🇷 Ligue 1": "fra.1",
    "🇳🇱 Eredivisie": "ned.1", "🇵🇹 Liga Portugal": "por.1",
    "🏆 UEFA Champions League": "uefa.champions", "🟠 UEFA Europa League": "uefa.europa",
    "🟢 UEFA Conference League": "uefa.europa.conf", "🇪🇸 Copa del Rey": "esp.copa_del_rey",
}
MAIN_LEAGUES = {
    "🇬🇧 England - Premier League": "E0", "🇬🇧 England - Championship": "E1", "🇬🇧 England - League 1": "E2",
    "🇬🇧 England - League 2": "E3", "🇬🇧 England - National League": "EC", "🏴 Scotland - Premiership": "SC0",
    "🏴 Scotland - Championship": "SC1", "🇪🇸 Spain - La Liga": "SP1", "🇪🇸 Spain - Segunda": "SP2",
    "🇩🇪 Germany - Bundesliga": "D1", "🇩🇪 Germany - 2. Bundesliga": "D2", "🇮🇹 Italy - Serie A": "I1",
    "🇮🇹 Italy - Serie B": "I2", "🇫🇷 France - Ligue 1": "F1", "🇫🇷 France - Ligue 2": "F2",
    "🇳🇱 Netherlands - Eredivisie": "N1", "🇧🇪 Belgium - Pro League": "B1", "🇵🇹 Portugal - Liga Portugal": "P1",
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

def get_secret(name, default=""):
    try: return str(st.secrets.get(name, default))
    except Exception: return default

def init_db():
    c = sqlite3.connect("my_bets.db")
    c.execute("CREATE TABLE IF NOT EXISTS bets (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, league TEXT, match_name TEXT, tip TEXT, confidence INTEGER, odds REAL, stake REAL, status TEXT DEFAULT 'Pending', profit REAL DEFAULT 0.0)")
    c.execute("CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT)")
    c.commit(); c.close()

def save_state(k, obj):
    c = sqlite3.connect("my_bets.db"); c.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)", (k, json.dumps(obj))); c.commit(); c.close()

def load_state(k, default):
    c = sqlite3.connect("my_bets.db"); r = c.execute("SELECT value FROM app_state WHERE key=?", (k,)).fetchone(); c.close()
    if r:
        try: return json.loads(r[0])
        except Exception: pass
    return default

def save_bet(lg, m, tip, conf, odds, stake):
    c = sqlite3.connect("my_bets.db")
    c.execute("INSERT INTO bets (date,league,match_name,tip,confidence,odds,stake) VALUES (?,?,?,?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), lg, m, tip, conf, odds, stake))
    c.commit(); c.close()

def update_bet(bid, status):
    c = sqlite3.connect("my_bets.db"); row = c.execute("SELECT odds,stake FROM bets WHERE id=?", (bid,)).fetchone()
    if row:
        p = round(row[1]*(row[0]-1), 2) if status == "Won" else (-row[1] if status == "Lost" else 0.0)
        c.execute("UPDATE bets SET status=?, profit=? WHERE id=?", (status, p, bid)); c.commit()
    c.close()

def load_bets():
    c = sqlite3.connect("my_bets.db"); df = pd.read_sql_query("SELECT * FROM bets ORDER BY id DESC", c); c.close(); return df

def am_to_dec(ml):
    try:
        v = float(ml)
        if v == 0: return None
        return round(1 + v/100.0, 2) if v > 0 else round(1 + 100.0/abs(v), 2)
    except Exception: return None

def parse_espn_odd(b):
    if not isinstance(b, dict): return None
    if b.get("value"):
        try:
            v = float(b["value"])
            if v > 1.01: return round(v, 2)
        except Exception: pass
    return am_to_dec(b["moneyLine"]) if b.get("moneyLine") is not None else None

def extract_comp_odds(comp):
    odl = comp.get("odds") or []
    if not odl: return None, None, None, ""
    od = odl[0]
    o1, ox, o2 = parse_espn_odd(od.get("homeTeamOdds")), parse_espn_odd(od.get("drawOdds")), parse_espn_odd(od.get("awayTeamOdds"))
    bk = (od.get("provider") or {}).get("name", "ESPN Odds") if o1 else ""
    return o1, ox, o2, bk

def norm_t(s): return "".join(c for c in s.lower() if c.isalnum() or c == " ").strip()

def find_odds(h, a, od):
    if not od: return None
    nh, na = norm_t(h), norm_t(a)
    if (nh, na) in od: return od[(nh, na)]
    st_w = {"fc","cf","sc","ac","afc","club","city","united","real"}
    hw = {w for w in nh.split() if len(w) > 2 and w not in st_w}
    aw = {w for w in na.split() if len(w) > 2 and w not in st_w}
    for (oh, oa), val in od.items():
        if (nh in oh or oh in nh or (hw and any(w in oh for w in hw))) and (na in oa or oa in na or (aw and any(w in oa for w in aw))):
            return val
    return None

@st.cache_data(ttl=1800)
def load_the_odds_api(key):
    if not key.strip(): return [], {}, ""
    try:
        r = requests.get("https://api.the-odds-api.com/v4/sports/upcoming/odds", params={"apiKey": key.strip(), "regions": "uk,eu", "markets": "h2h", "oddsFormat": "decimal"}, timeout=15)
        if r.status_code != 200: return [], {}, f"The Odds API {r.status_code}: {r.text[:120]}"
        evs, om = [], {}
        for ev in r.json():
            if not str(ev.get("sport_key", "")).startswith("soccer"): continue
            h, a, bks = ev.get("home_team", ""), ev.get("away_team", ""), ev.get("bookmakers") or []
            if not h or not a or not bks: continue
            bk = bks[0]; mkt = next((m for m in bk.get("markets", []) if m.get("key") == "h2h"), None)
            if not mkt: continue
            o1 = ox = o2 = None
            for out in mkt.get("outcomes", []):
                if out.get("name") == h: o1 = out.get("price")
                elif out.get("name") == a: o2 = out.get("price")
                elif str(out.get("name", "")).lower() == "draw": ox = out.get("price")
            if o1 and ox and o2:
                val = (round(float(o1), 2), round(float(ox), 2), round(float(o2), 2), bk.get("title", "Bookie"))
                om[(norm_t(h), norm_t(a))] = val
                evs.append({"DateTime": ev.get("commence_time", "")[:16].replace("T", " "), "League": ev.get("sport_title", "Soccer"), "Home": h, "Away": a, "1": val[0], "X": val[1], "2": val[2], "Bookie": val[3], "LeagueId": None})
        return evs, om, ""
    except Exception as e: return [], {}, str(e)

@st.cache_data(ttl=900, show_spinner=False)
def load_espn_by_date(date_str):
    last_err = ""
    for host in ["site.api.espn.com", "site.web.api.espn.com"]:
        try:
            r = requests.get(f"https://{host}/apis/site/v2/sports/soccer/all/scoreboard?dates={date_str}", timeout=15)
            if r.status_code != 200: last_err = f"HTTP {r.status_code}"; continue
            games = []
            for ev in r.json().get("events", []):
                comp = (ev.get("competitions") or [{}])[0]; cs = comp.get("competitors") or []
                hc = next((c for c in cs if c.get("homeAway") == "home"), None)
                ac = next((c for c in cs if c.get("homeAway") == "away"), None)
                if not hc or not ac: continue
                hn, an = (hc.get("team") or {}).get("displayName"), (ac.get("team") or {}).get("displayName")
                if not hn or not an: continue
                sti = (comp.get("status") or {}).get("type") or {}
                o1, ox, o2, bk = extract_comp_odds(comp)
                lgl = ev.get("leagues") or []
                lgn = lgl[0].get("name") if lgl and isinstance(lgl[0], dict) else None
                lg = (ev.get("season") or {}).get("slug") or lgn or "Soccer"
                games.append({"DateTime": (ev.get("date") or "")[:16].replace("T", " "), "League": lg, "Home": hn, "Away": an, "Status": sti.get("shortDetail", "Scheduled"), "1": o1, "X": ox, "2": o2, "Bookie": bk, "LeagueId": None})
            return games, ""
        except Exception as e: last_err = str(e)
    return [], f"Could not reach ESPN daily scoreboard ({last_err})."

@st.cache_data(ttl=1800)
def load_espn(slug):
    base = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"
    seen, fin, up = set(), [], {}
    for w in [None, "202611", "202610", "202609", "202608"]:
        try:
            r = requests.get(base if w is None else f"{base}?dates={w}", timeout=12)
            if r.status_code != 200: continue
            for ev in r.json().get("events", []):
                eid = ev.get("id")
                if eid in seen: continue
                seen.add(eid)
                comp = (ev.get("competitions") or [{}])[0]; cs = comp.get("competitors") or []
                hc = next((c for c in cs if c.get("homeAway") == "home"), None)
                ac = next((c for c in cs if c.get("homeAway") == "away"), None)
                if not hc or not ac: continue
                hn, an = (hc.get("team") or {}).get("displayName"), (ac.get("team") or {}).get("displayName")
                if not hn or not an: continue
                dt = (ev.get("date") or "")[:10]
                st_s = ((comp.get("status") or {}).get("type") or {}).get("state", "")
                if st_s == "post":
                    try: fin.append({"Date": dt, "HomeTeam": hn, "AwayTeam": an, "FTHG": int(float(hc.get("score") or 0)), "FTAG": int(float(ac.get("score") or 0))})
                    except (ValueError, TypeError): pass
                elif st_s == "pre":
                    o1, ox, o2, bk = extract_comp_odds(comp)
                    up[(dt, hn, an)] = (dt, hn, an, o1, ox, o2, bk)
        except Exception: pass
    df = pd.DataFrame(fin)
    if not df.empty:
        df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("DateParsed").reset_index(drop=True)
    return df, sorted(up.values(), key=lambda x: x[0])[:35], ""

@st.cache_data(ttl=900)
def load_goal_by_date(date_iso, key):
    hdr = {"Authorization": f"Bearer {key.strip()}"}; items, err = [], ""
    for off in [0, 100]:
        try:
            r = requests.get(f"https://api.goal-api.com/v1/fixtures/date/{date_iso}", params={"limit": 100, "offset": off}, headers=hdr, timeout=15)
            if r.status_code == 401: return [], "❌ Invalid GOAL API key."
            if r.status_code != 200: err = f"GOAL API {r.status_code}"; break
            p = r.json(); data = p.get("data") or []; items.extend(data)
            if not (p.get("pagination") or {}).get("hasMore", False) or len(data) < 100: break
        except Exception as e: err = str(e); break
    games = []
    for m in items:
        h, a = (m.get("homeTeam") or {}).get("name") or m.get("homeTeamName"), (m.get("awayTeam") or {}).get("name") or m.get("awayTeamName")
        if not h or not a: continue
        lg = (m.get("league") or {}).get("name") or m.get("leagueName") or "League"
        lid = (m.get("league") or {}).get("id") or m.get("leagueId")
        games.append({"DateTime": (m.get("kickoffUtc") or date_iso)[:16].replace("T", " "), "League": lg, "Home": h, "Away": a, "Status": m.get("matchStatus") or "Scheduled", "1": None, "X": None, "2": None, "Bookie": "", "LeagueId": lid})
    return games, ("" if items or not err else err)

@st.cache_data(ttl=3600)
def load_main_csv(code):
    frames = []
    for s in ["2526", "2627"]:
        try: frames.append(pd.read_csv(f"https://www.football-data.co.uk/mmz4281/{s}/{code}.csv", encoding="latin1").dropna(subset=["HomeTeam","AwayTeam","FTHG","FTAG"]))
        except Exception: pass
    if not frames: return pd.DataFrame(), [], "Could not download CSV."
    f = pd.concat(frames, ignore_index=True)
    f["FTHG"], f["FTAG"] = f["FTHG"].astype(int), f["FTAG"].astype(int)
    f["DateParsed"] = pd.to_datetime(f["Date"], dayfirst=True, errors="coerce")
    return f.sort_values("DateParsed").reset_index(drop=True), [], ""

@st.cache_data(ttl=3600)
def load_world_csv(code):
    try:
        d = pd.read_csv(f"https://www.football-data.co.uk/new/{code}.csv", encoding="latin1").rename(columns={"Home":"HomeTeam","Away":"AwayTeam","HG":"FTHG","AG":"FTAG"}).dropna(subset=["HomeTeam","AwayTeam","FTHG","FTAG"]).tail(800)
        d["FTHG"], d["FTAG"] = d["FTHG"].astype(int), d["FTAG"].astype(int)
        d["DateParsed"] = pd.to_datetime(d["Date"], dayfirst=True, errors="coerce")
        return d.sort_values("DateParsed").reset_index(drop=True), [], ""
    except Exception: return pd.DataFrame(), [], "Could not download CSV."

@st.cache_data(ttl=3600)
def search_goal_leagues(q, key):
    try:
        r = requests.get("https://api.goal-api.com/v1/leagues", params={"search": q, "limit": 50}, headers={"Authorization": f"Bearer {key.strip()}"}, timeout=15)
        return r.json().get("data", []) if r.status_code == 200 else []
    except Exception: return []

@st.cache_data(ttl=1800)
def load_goal_fixtures(lid, key):
    hdr, items, ok, lerr = {"Authorization": f"Bearer {key.strip()}"}, [], False, ""
    now = datetime.now(timezone.utc)
    plan = [(f"https://api.goal-api.com/v1/leagues/{lid}/fixtures",{"limit":100}), (f"https://api.goal-api.com/v1/leagues/{lid}/results",{"limit":100}), ("https://api.goal-api.com/v1/fixtures",{"leagueId":lid,"from":(now-timedelta(days=90)).strftime("%Y-%m-%d"),"to":(now+timedelta(days=21)).strftime("%Y-%m-%d"),"limit":100})]
    for url, bp in plan:
        for off in [0, 100]:
            try:
                r = requests.get(url, params={**bp, "offset": off}, headers=hdr, timeout=15)
                if r.status_code == 401: return pd.DataFrame(), [], "❌ Invalid GOAL API key."
                if r.status_code != 200: lerr = f"API {r.status_code}"; break
                ok = True; p = r.json(); d = p.get("data") or []; items.extend(d)
                if not (p.get("pagination") or {}).get("hasMore", False) or len(d) < 100: break
            except Exception as e: lerr = str(e); break
    fin, up, sf, su = [], [], set(), set()
    for m in items:
        h, a = (m.get("homeTeam") or {}).get("name") or m.get("homeTeamName"), (m.get("awayTeam") or {}).get("name") or m.get("awayTeamName")
        if not h or not a: continue
        dt = (m.get("kickoffUtc") or m.get("matchDate") or "")[:10]
        hs = m.get("homeScore") if m.get("homeScore") is not None else m.get("homeTeamScore")
        as_ = m.get("awayScore") if m.get("awayScore") is not None else m.get("awayTeamScore")
        per, stt = str(m.get("matchPeriod") or "").upper(), str(m.get("matchStatus") or "").upper()
        isf = per == "FINISHED" or stt in ("FINISHED","FT","AET","PEN","AFTER PEN.","PLAYED")
        isu = per in ("NOT_STARTED","SCHEDULED") or stt in ("SCHEDULED","NOT_STARTED","NS","TIMED","UPCOMING","")
        if hs is not None and as_ is not None and (isf or (not isu and per != "NOT_STARTED")):
            try:
                if (dt, h, a) not in sf: sf.add((dt, h, a)); fin.append({"Date":dt,"HomeTeam":h,"AwayTeam":a,"FTHG":int(float(hs)),"FTAG":int(float(as_))})
            except (ValueError, TypeError): pass
        elif not isf and (dt, h, a) not in su: su.add((dt, h, a)); up.append((dt, h, a, None, None, None, ""))
    df = pd.DataFrame(fin)
    if not df.empty:
        df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("DateParsed").reset_index(drop=True)
    return df, sorted(up, key=lambda x: x[0])[:40], ("" if ok else lerr)

def get_metrics(df, team, venue="all", last_n=5):
    base = {"form":"-","gf":1.2,"ga":1.2,"o15":60,"o25":45,"o35":20,"btts":50,"corners":0.0,"shots_ot":0.0,"power":50.0}
    if df.empty: return base
    g = df[df["HomeTeam"]==team].tail(last_n) if venue=="home" else (df[df["AwayTeam"]==team].tail(last_n) if venue=="away" else df[(df["HomeTeam"]==team)|(df["AwayTeam"]==team)].tail(last_n))
    if g.empty: return base
    fm, gft, gat, o15, o25, o35, bt, ct, stt, pts = [], 0, 0, 0, 0, 0, 0, 0, 0, 0
    hc, hs = "HC" in g.columns and "AC" in g.columns, "HST" in g.columns and "AST" in g.columns
    for _, r in g.iterrows():
        ih = r["HomeTeam"] == team
        gf, ga = (r["FTHG"], r["FTAG"]) if ih else (r["FTAG"], r["FTHG"])
        gft += gf; gat += ga; tot = gf + ga
        if gf > ga: fm.append("W"); pts += 3
        elif gf == ga: fm.append("D"); pts += 1
        else: fm.append("L")
        if tot > 1: o15 += 1
        if tot > 2: o25 += 1
        if tot > 3: o35 += 1
        if gf > 0 and ga > 0: bt += 1
        if hc and pd.notna(r["HC"]) and pd.notna(r["AC"]): ct += r["HC"] if ih else r["AC"]
        if hs and pd.notna(r["HST"]) and pd.notna(r["AST"]): stt += r["HST"] if ih else r["AST"]
    n = len(g); pwr = float(np.clip((pts/(n*3))*65 + ((gft-gat)/n)*10 + 18, 10, 99))
    return {"form":"".join(fm),"gf":round(gft/n,2),"ga":round(gat/n,2),"o15":round(o15/n*100),"o25":round(o25/n*100),"o35":round(o35/n*100),"btts":round(bt/n*100),"corners":round(ct/n,1) if hc else 0.0,"shots_ot":round(stt/n,1) if hs else 0.0,"power":round(pwr,1)}

def get_h2h(df, h, a):
    if df.empty: return pd.DataFrame()
    q = df[((df["HomeTeam"]==h)&(df["AwayTeam"]==a))|((df["HomeTeam"]==a)&(df["AwayTeam"]==h))].tail(5)
    return pd.DataFrame() if q.empty else q[["Date","HomeTeam","FTHG","FTAG","AwayTeam"]].iloc[::-1]

def analyze_fixture(df, home, away, o1=1.85, ox=3.50, o2=4.20):
    ha, aa = get_metrics(df, home, "all", 15), get_metrics(df, away, "all", 15)
    h5, a5 = get_metrics(df, home, "home", 5), get_metrics(df, away, "away", 5)
    if h5["form"] == "-" and ha["form"] != "-": h5 = ha
    if a5["form"] == "-" and aa["form"] != "-": a5 = aa
    if h5["form"] == "-" and a5["form"] == "-" and o1 > 1.01 and ox > 1.01 and o2 > 1.01:
        si = (1/o1) + (1/ox) + (1/o2)
        eh, ea = float(np.clip(0.8 + ((1/o1)/si)*1.9, 0.4, 3.0)), float(np.clip(0.7 + ((1/o2)/si)*1.8, 0.4, 3.0))
    else:
        ahg = max(float(df["FTHG"].mean()), 0.5) if not df.empty else 1.35
        aag = max(float(df["FTAG"].mean()), 0.5) if not df.empty else 1.15
        eh = float(np.clip(((h5["gf"]*0.65+ha["gf"]*0.35)/ahg)*((a5["ga"]*0.65+aa["ga"]*0.35)/ahg)*ahg, 0.25, 4.0))
        ea = float(np.clip(((a5["gf"]*0.65+aa["gf"]*0.35)/aag)*((h5["ga"]*0.65+ha["ga"]*0.35)/aag)*aag, 0.25, 4.0))
    mat = np.array([[poisson.pmf(i, eh)*poisson.pmf(j, ea) for j in range(7)] for i in range(7)])
    p1, px, p2 = float(np.sum(np.tril(mat,-1))), float(np.sum(np.diag(mat))), float(np.sum(np.triu(mat,1)))
    p1x, px2, p12 = p1+px, p2+px, p1+p2
    po15 = float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j>1))
    po25 = float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j>2))
    pu25, pu35 = 1.0-po25, 1.0-float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j>3))
    pbtts = float(sum(mat[i,j] for i in range(1,7) for j in range(1,7))); png = 1.0-pbtts
    ts = [f"{np.unravel_index(k,mat.shape)[0]}:{np.unravel_index(k,mat.shape)[1]} ({mat.ravel()[k]*100:.0f}%)" for k in np.argsort(mat.ravel())[::-1][:3]]
    probs = {"1":p1,"X":px,"2":p2}; bp = max(probs, key=probs.get); bpr = probs[bp]
    if bp == "1" and bpr < 0.52 and p1x >= 0.72: tip, cp = "1X", p1x
    elif bp == "2" and bpr < 0.52 and px2 >= 0.72: tip, cp = "X2", px2
    else: tip, cp = bp, bpr
    conf = int(np.clip(round((cp-0.25)/0.60*9+1), 1, 10))
    safes = {"1X":p1x,"X2":px2,"12":p12,"Over 1.5":po15,"Under 3.5":pu35}
    sn = max(safes, key=safes.get); sp_v = safes[sn]
    if p1 >= 0.55 and po15 >= 0.68: combo = "1 & Over 1.5"
    elif p2 >= 0.55 and po15 >= 0.68: combo = "2 & Over 1.5"
    elif p1x >= 0.72 and pu35 >= 0.65: combo = "1X & Under 3.5"
    elif px2 >= 0.72 and pu35 >= 0.65: combo = "X2 & Under 3.5"
    elif po25 >= 0.55 and pbtts >= 0.55: combo = "Over 2.5 & BTTS"
    else: combo = f"{tip} & {'Over 1.5' if po15>=0.65 else 'Under 3.5'}"
    evs = {"1":p1*o1-1,"X":px*ox-1,"2":p2*o2-1}; bevs = max(evs, key=evs.get); bev = evs[be
