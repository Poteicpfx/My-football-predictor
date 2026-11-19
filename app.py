import json, sqlite3
from datetime import datetime, timedelta, timezone
import requests
import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson

st.set_page_config(page_title="World Football Predictor Pro", page_icon="⚽", layout="wide")
st.markdown("""<style>
[data-testid="stAppViewContainer"]{background:radial-gradient(circle at 18% 15%,rgba(16,185,129,0.18),transparent 42%),radial-gradient(circle at 85% 20%,rgba(56,189,248,0.14),transparent 40%),linear-gradient(145deg,#040d0a 0%,#091722 50%,#050c14 100%);color:#f1f5f9;}
[data-testid="stHeader"]{background:rgba(4,13,10,0.55);backdrop-filter:blur(8px);}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#06131a 0%,#081c18 100%);border-right:1px solid rgba(16,185,129,0.25);}
.hero-banner{background:linear-gradient(120deg,rgba(16,185,129,0.20),rgba(15,23,42,0.85));border:1px solid rgba(52,211,153,0.35);border-radius:14px;padding:14px 18px;margin-bottom:14px;}
.glass-card{background:rgba(10,22,30,0.80);border:1px solid rgba(52,211,153,0.25);border-radius:12px;padding:12px 16px;margin-bottom:10px;}
[data-testid="stMetric"]{background:rgba(12,27,36,0.85);border:1px solid rgba(52,211,153,0.25);border-radius:10px;padding:8px 10px;}
.stButton>button{background:linear-gradient(90deg,#059669,#10b981);color:#fff;border:none;border-radius:8px;font-weight:700;}
</style>""", unsafe_allow_html=True)

ESPN_CUPS = {"🏆 UEFA Champions League":"uefa.champions","🟠 UEFA Europa League":"uefa.europa","🟢 UEFA Conference League":"uefa.europa.conf","🇪🇺 UEFA Nations League":"uefa.nations","🇪🇸 Spain - Copa del Rey":"esp.copa_del_rey","🇩🇪 Germany - DFB Pokal":"ger.dfb_pokal","🌍 FIFA World Cup":"fifa.world","🌍 CAF AFCON":"caf.nations","🌏 AFC Champions League":"afc.champions","🌎 Copa Libertadores":"conmebol.libertadores","🌎 Copa Sudamericana":"conmebol.sudamericana"}
MAIN_LEAGUES = {"🇬🇧 England - Premier League":"E0","🇬🇧 England - Championship":"E1","🇬🇧 England - League 1":"E2","🇬🇧 England - League 2":"E3","🇬🇧 England - National League":"EC","🏴 Scotland - Premiership":"SC0","🏴 Scotland - Championship":"SC1","🇪🇸 Spain - La Liga":"SP1","🇪🇸 Spain - Segunda":"SP2","🇩🇪 Germany - Bundesliga":"D1","🇩🇪 Germany - 2. Bundesliga":"D2","🇮🇹 Italy - Serie A":"I1","🇮🇹 Italy - Serie B":"I2","🇫🇷 France - Ligue 1":"F1","🇫🇷 France - Ligue 2":"F2","🇳🇱 Netherlands - Eredivisie":"N1","🇧🇪 Belgium - Pro League":"B1","🇵🇹 Portugal - Liga Portugal":"P1","🇹🇷 Turkey - Super Lig":"T1","🇬🇷 Greece - Super League":"G1"}
WORLD_LEAGUES = {"🇦🇷 Argentina - Primera":"ARG","🇧🇷 Brazil - Serie A":"BRA","🇺🇸 USA - MLS":"USA","🇲🇽 Mexico - Liga MX":"MEX","🇯🇵 Japan - J-League":"JPN","🇨🇳 China - Super League":"CHN","🇦🇹 Austria - Bundesliga":"AUT","🇩🇰 Denmark - Superliga":"DNK","🇫🇮 Finland - Veikkausliiga":"FIN","🇮🇪 Ireland - Premier":"IRL","🇳🇴 Norway - Eliteserien":"NOR","🇵🇱 Poland - Ekstraklasa":"POL","🇷🇴 Romania - Liga 1":"ROU","🇷🇺 Russia - Premier":"RUS","🇸🇪 Sweden - Allsvenskan":"SWE","🇨🇭 Switzerland - Super League":"SWZ"}

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

init_db()

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

def norm_t(s): return "".join(c for c in s.lower() if c.isalnum() or c == " ").strip()

def find_odds(h, a, od):
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
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"
                continue
            games = []
            for ev in r.json().get("events", []):
                comp = (ev.get("competitions") or [{}])[0]; cs = comp.get("competitors") or []
                hc = next((c for c in cs if c.get("homeAway") == "home"), None)
                ac = next((c for c in cs if c.get("homeAway") == "away"), None)
                if not hc or not ac: continue
                hn, an = (hc.get("team") or {}).get("displayName"), (ac.get("team") or {}).get("displayName")
                if not hn or not an: continue
                sti = (comp.get("status") or {}).get("type") or {}
                odl = comp.get("odds") or []
                o1 = ox = o2 = None; bk = ""
                if odl:
                    od = odl[0]
                    o1, ox, o2 = parse_espn_odd(od.get("homeTeamOdds")), parse_espn_odd(od.get("drawOdds")), parse_espn_odd(od.get("awayTeamOdds"))
                    bk = (od.get("provider") or {}).get("name", "ESPN Odds")
                lgl = ev.get("leagues") or []
                lgn = lgl[0].get("name") if lgl and isinstance(lgl[0], dict) else None
                lg = (ev.get("season") or {}).get("slug") or lgn or "Soccer"
                games.append({"DateTime": (ev.get("date") or "")[:16].replace("T", " "), "League": lg, "Home": hn, "Away": an, "Status": sti.get("shortDetail", "Scheduled"), "1": o1, "X": ox, "2": o2, "Bookie": bk if o1 else "", "LeagueId": None})
            return games, ""
        except Exception as e:
            last_err = str(e)
    return [], f"Could not reach ESPN daily scoreboard ({last_err})."

@st.cache_data(ttl=1800)
def load_espn(slug):
    base = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"
    seen, fin, up = set(), [], []
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
                elif st_s == "pre": up.append((dt, hn, an))
        except Exception: pass
    df = pd.DataFrame(fin)
    if not df.empty:
        df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("DateParsed").reset_index(drop=True)
    return df, sorted(set(up), key=lambda x: x[0])[:35], ""

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
        h = (m.get("homeTeam") or {}).get("name") or m.get("homeTeamName")
        a = (m.get("awayTeam") or {}).get("name") or m.get("awayTeamName")
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
        elif not isf and (dt, h, a) not in su: su.add((dt, h, a)); up.append((dt, h, a))
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
    po05 = float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j>0))
    po15 = float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j>1))
    po25 = float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j>2))
    po35 = float(sum(mat[i,j] for i in range(7) for j in range(7) if i+j>3))
    pu25, pu35 = 1.0-po25, 1.0-po35
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
    evs = {"1":p1*o1-1,"X":px*ox-1,"2":p2*o2-1}; bevs = max(evs, key=evs.get); bev = evs[bevs]
    tags = []
    if conf >= 8 and {"1":o1,"X":ox,"2":o2}.get(bp,1.45) <= 1.65: tags.append("🔒 Banker")
    if bev >= 0.05: tags.append(f"💎 Value ({bevs}: +{bev*100:.0f}% EV)")
    if px >= 0.29 and abs(h5["power"]-a5["power"]) <= 12: tags.append("⚖️ Draw Watch")
    verdict = f"{home} xG {eh:.2f} vs {away} {ea:.2f}. Safest: {sn} ({sp_v*100:.0f}%) | Combo: {combo}."
    return {"Match":f"{home} vs {away}","Tip":tip,"Conf":conf,"Safest":f"{sn} ({sp_v*100:.0f}%)","Combo":combo,"1":o1,"X":ox,"2":o2,"O/U 2.5":f"{'Over' if po25>=0.52 else 'Under'} ({po25*100:.0f}%)","BTTS":f"{pbtts*100:.0f}%","Score":ts[0].split(" ")[0],"Category":" | ".join(tags) if tags else "Standard","_raw":{"home":home,"away":away,"eh":eh,"ea":ea,"p1":p1,"px":px,"p2":p2,"p1x":p1x,"px2":px2,"p12":p12,"po05":po05,"po15":po15,"po25":po25,"po35":po35,"pu25":pu25,"pu35":pu35,"pbtts":pbtts,"png":png,"top_scores":ts,"verdict":verdict,"ev":evs,"h5":h5,"a5":a5}}

def build_ctx(res, h2h, comp):
    r = res["_raw"]; h5, a5 = r["h5"], r["a5"]
    return f"Comp: {comp} | Match: {res['Match']} | Odds 1={res['1']} X={res['X']} 2={res['2']}\nxG: {r['home']} {r['eh']:.2f} - {r['ea']:.2f} {r['away']} | 1={r['p1']*100:.1f}% X={r['px']*100:.1f}% 2={r['p2']*100:.1f}%\nDC: 1X={r['p1x']*100:.1f}% X2={r['px2']*100:.1f}% | O1.5={r['po15']*100:.1f}% O2.5={r['po25']*100:.1f}% BTTS={r['pbtts']*100:.1f}%\nSafest: {res['Safest']} | Combo: {res['Combo']} | Scores: {', '.join(r['top_scores'])}\nH-L5: {h5['form']} Pwr={h5['power']} | A-L5: {a5['form']} Pwr={a5['power']}\nH2H:\n{'None' if h2h.empty else h2h.to_string(index=False)}"

def smart_advisor(res, q):
    r = res["_raw"]
    mkts = sorted([(f"{r['home']} (1)",r["p1"]),("Draw (X)",r["px"]),(f"{r['away']} (2)",r["p2"]),("1X",r["p1x"]),("X2",r["px2"]),("Over 1.5",r["po15"]),("Over 2.5",r["po25"]),("Under 2.5",r["pu25"]),("Under 3.5",r["pu35"]),("BTTS Yes",r["pbtts"]),("BTTS No",r["png"])], key=lambda x:x[1], reverse=True)
    bevs = max(r["ev"], key=r["ev"].get)
    return f"**Smart Analysis: {res['Match']}**\n\n🎯 **Best Pick:** **{mkts[0][0]}** (`{mkts[0][1]*100:.1f}%`) | **Combo:** `{res['Combo']}`\n\n1. **{mkts[0][0]}** — `{mkts[0][1]*100:.1f}%`\n2. **{mkts[1][0]}** — `{mkts[1][1]*100:.1f}%`\n3. **{mkts[2][0]}** — `{mkts[2][1]*100:.1f}%`\n\n💎 **Best Value:** `{bevs}` (`{r['ev'][bevs]*100:+.1f}%` EV) | **Scores:** {', '.join(r['top_scores'])}"

def ask_llm(prov, key, ctx, hist, q):
    sys_p = f"You are an expert football betting analyst. Use ONLY these stats to pick the best option, backup, and risk:\n{ctx}"
    k = key.strip()
    if prov == "Groq (Free AI)":
        msgs = [{"role":"system","content":sys_p}] + [{"role":m["role"],"content":m["content"]} for m in hist[-6:]] + [{"role":"user","content":q}]
        err = ""
        for m in ["openai/gpt-oss-120b","openai/gpt-oss-20b","qwen/qwen3.8-27b"]:
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"}, json={"model":m,"messages":msgs,"temperature":0.3}, timeout=25)
                if r.status_code == 200: return r.json()["choices"][0]["message"]["content"]
                err = f"Groq Error {r.status_code}: {r.text[:150]}"
            except Exception as e: err = str(e)
        return err
    contents = [{"role":"user" if m["role"]=="user" else "model","parts":[{"text":m["content"]}]} for m in hist[-6:]] + [{"role":"user","parts":[{"text":q}]}]
    err = ""
    for m in ["gemini-3.8-flash","gemini-3.5-flash-lite","gemini-3.6-flash","gemini-flash-latest"]:
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}", headers={"Content-Type":"application/json"}, json={"system_instruction":{"parts":[{"text":sys_p}]},"contents":contents,"generationConfig":{"temperature":0.3}}, timeout=25)
            if r.status_code == 200: return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            err = f"Gemini Error {r.status_code}: {r.text[:150]}"
        except Exception as e: err = str(e)
    return err

# --- STATE & SIDEBAR ---
prefs = load_state("prefs", {})
if "daily_list" not in st.session_state: st.session_state.daily_list = load_state("daily_list", [])
if "ai_messages" not in st.session_state: st.session_state.ai_messages = load_state("ai_messages", [])

st.sidebar.header("🔑 Keys (Auto-Loaded from Secrets)")
gkey = st.sidebar.text_input("GOAL API Key (1,000+ Leagues)", value=get_secret("GOAL_API_KEY", prefs.get("gkey", "")), type="password")
okey = st.sidebar.text_input("The Odds API Key (Live Bookie Odds)", value=get_secret("ODDS_API_KEY", prefs.get("okey", "")), type="password")

st.sidebar.divider()
st.sidebar.header("🌍 League Analyzer Source")
modes = ["🏆 UEFA, CAF, AFC, FIFA & Cups (No Key)", "⚽ 36 Global Leagues (No Key)", "🔎 All 1,000+ Competitions (GOAL API Key)"]
sm = prefs.get("mode", modes[0])
mode = st.sidebar.radio("Category", modes, index=modes.index(sm) if sm in modes else 0)

df_league, upcoming_fixtures, selected_comp, load_err = pd.DataFrame(), [], "", ""
if mode == modes[0]:
    ks = list(ESPN_CUPS.keys()); sc = prefs.get("comp", ks[0])
    selected_comp = st.sidebar.selectbox("Tournament", ks, index=ks.index(sc) if sc in ks else 0)
    custom = st.sidebar.text_input("Or custom ESPN slug", placeholder="e.g. eng.1, esp.1")
    slug = custom.strip() if custom.strip() else ESPN_CUPS[selected_comp]
    if custom.strip(): selected_comp = f"Custom ({slug})"
    df_league, upcoming_fixtures, load_err = load_espn(slug)
elif mode == modes[1]:
    all_l = {**MAIN_LEAGUES, **WORLD_LEAGUES}; ks = list(all_l.keys()); sc = prefs.get("comp", ks[0])
    selected_comp = st.sidebar.selectbox("League", ks, index=ks.index(sc) if sc in ks else 0)
    code = all_l[selected_comp]
    df_league, upcoming_fixtures, load_err = load_main_csv(code) if selected_comp in MAIN_LEAGUES else load_world_csv(code)
else:
    presets = ["Custom Search","Copa del Rey","CAF Champions League","NPFL","UEFA Champions League","UEFA Europa League","AFC Champions League"]
    qp = st.sidebar.selectbox("Presets", presets)
    sq = st.sidebar.text_input("Search ANY Competition", value=prefs.get("sq","Premier League") if qp=="Custom Search" else qp)
    if gkey and sq:
        found = search_goal_leagues(sq, gkey)
        if found:
            opts = {f"{x.get('name')} ({(x.get('country') or {}).get('name','Intl')})": x.get("id") for x in found}
            oks = list(opts.keys()); sc = prefs.get("comp", oks[0])
            selected_comp = st.sidebar.selectbox("Pick Competition", oks, index=oks.index(sc) if sc in oks else 0)
            df_league, upcoming_fixtures, load_err = load_goal_fixtures(opts[selected_comp], gkey)
        else: st.sidebar.warning("No competition matched.")
    else: st.sidebar.info("Enter GOAL API Key above.")

st.sidebar.divider()
st.sidebar.header("🤖 AI Space Settings")
ai_provs = ["Built-in Smart Advisor (No Key)", "Groq (Free AI)", "Google Gemini (Free AI)"]
sp = prefs.get("ai_prov", ai_provs[0])
ai_prov = st.sidebar.selectbox("AI Engine", ai_provs, index=ai_provs.index(sp) if sp in ai_provs else 0)
sec_ai = get_secret("GROQ_API_KEY") if ai_prov=="Groq (Free AI)" else (get_secret("GEMINI_API_KEY") if ai_prov=="Google Gemini (Free AI)" else "")
ai_key = st.sidebar.text_input("Paste Free AI Key", value=sec_ai, type="password") if ai_prov != ai_provs[0] else ""
odds_events, odds_dict, odds_err = load_the_odds_api(okey)

# --- MAIN UI ---
st.markdown('<div class="hero-banner"><h2 style="margin:0;color:#ecfdf5;">⚽ World Football Predictor Pro</h2><div style="color:#a7f3d0;font-size:0.9rem;">Games by Date • Auto Bookmaker Odds • Persistent Memory • AI Advisor</div></div>', unsafe_allow_html=True)
tab_date, tab_board, tab_ai, tab_daily, tab_track = st.tabs(["📅 Games by Date (Auto-Odds)", "🔍 League Analyzer", "🤖 AI Space", "🔥 Daily Tips", "📒 Bet Tracker"])
cur_res, cur_h2h, cur_comp = None, pd.DataFrame(), selected_comp

with tab_date:
    st.subheader("📅 Select Any Date — Auto-Loaded Games & Odds")
    dc1, dc2, dc3 = st.columns([1.2, 2, 0.8])
    picked_date = dc1.date_input("Choose Match Date", value=datetime.now().date())
    date_feed = dc2.selectbox("Date Feed", ["🌍 Major Games & Auto Odds (ESPN Free, No Key)", "🔎 All 1,000+ Leagues on This Date (GOAL API Key)", "💎 Pure Live Bookmaker Card (The Odds API Key)"])
    if dc3.button("🔄 Refresh"):
        st.cache_data.clear(); st.rerun()
    date_games, d_err = [], ""
    if date_feed.startswith("🌍"): date_games, d_err = load_espn_by_date(picked_date.strftime("%Y%m%d"))
    elif date_feed.startswith("🔎"):
        if not gkey: st.warning("Paste your GOAL API Key in the sidebar (or Secrets).")
        else: date_games, d_err = load_goal_by_date(picked_date.strftime("%Y-%m-%d"), gkey)
    else:
        if not okey: st.warning("Paste your The Odds API key in the sidebar (or Secrets).")
        else:
            dtp = picked_date.strftime("%Y-%m-%d")
            date_games = [e for e in odds_events if e["DateTime"].startswith(dtp)] or odds_events
    if d_err: st.error(d_err)
    if odds_err: st.warning(odds_err)
    for g in date_games:
        if (not g["1"] or not g["X"] or not g["2"]) and odds_dict:
            fd = find_odds(g["Home"], g["Away"], odds_dict)
            if fd: g["1"], g["X"], g["2"], g["Bookie"] = fd
    if not date_games: st.info("No matches found for this date on the selected feed.")
    else:
        st.caption(f"Found **{len(date_games)}** matches for **{picked_date.strftime('%Y-%m-%d')}**")
        st.dataframe(pd.DataFrame([{"Time":g["DateTime"][11:] or g["DateTime"],"Competition":g["League"],"Home":g["Home"],"Away":g["Away"],"Status":g.get("Status","Scheduled"),"1":g["1"] or "-","X":g["X"] or "-","2":g["2"] or "-","Source":g["Bookie"] or "-"} for g in date_games]), hide_index=True, use_container_width=True)
        st.divider()
        ml = ["-- Pick a Match From This Date to Analyze --"] + [f"{g['League']} | {g['Home']} vs {g['Away']} (1:{g['1'] or '?'} X:{g['X'] or '?'} 2:{g['2'] or '?'})" for g in date_games]
        cm = st.selectbox("🎯 Analyze Any Match Above (Odds Auto-Filled!)", ml)
        if cm != ml[0]:
            g = date_games[ml.index(cm)-1]
            df_mh = load_goal_fixtures(g["LeagueId"], gkey)[0] if (g.get("LeagueId") and gkey) else pd.DataFrame()
            o1a, oxa, o2a = float(g["1"] or 1.90), float(g["X"] or 3.40), float(g["2"] or 3.90)
            rd = analyze_fixture(df_mh, g["Home"], g["Away"], o1a, oxa, o2a); rwd = rd["_raw"]
            cur_res, cur_h2h, cur_comp = rd, get_h2h(df_mh, g["Home"], g["Away"]), g["League"]
            m1,m2,m3,m4,m5 = st.columns(5)
            m1.metric("Best Tip", f"{rd['Tip']} ({rd['Conf']}/10)"); m2.metric("Safest Pick", rd["Safest"]); m3.metric("Combo", rd["Combo"]); m4.metric("Goals & BTTS", f"{rd['O/U 2.5']} | {rd['BTTS']}"); m5.metric("Auto Odds", f"{o1a}/{oxa}/{o2a}")
            st.markdown(f'<div class="glass-card"><b>🧠 Verdict ({rd["Category"]}):</b> {rwd["verdict"]}<br><b>Top 3 Scores:</b> {", ".join(rwd["top_scores"])}</div>', unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            if b1.button("➕ Add Match to Daily Tips", key="d_add", use_container_width=True):
                rc = {k:v for k,v in rd.items() if k!="_raw"}; rc["Competition"] = g["League"]
                st.session_state.daily_list.append(rc); save_state("daily_list", st.session_state.daily_list); st.success("Added!")
            pod = {"1":o1a,"X":oxa,"2":o2a,"1X":round(1/(1/o1a+1/oxa),2),"X2":round(1/(1/o2a+1/oxa),2)}.get(rd["Tip"], o1a)
            if b2.button("💾 Save Match to Bet Tracker", key="d_save", use_container_width=True):
                save_bet(g["League"], rd["Match"], rd["Tip"], rd["Conf"], pod, float(prefs.get("stake", 1000.0))); st.success("Saved!")

with tab_board:
    if load_err: st.error(load_err)
    ht = (set(df_league["HomeTeam"].unique()) | set(df_league["AwayTeam"].unique())) if not df_league.empty else set()
    teams = sorted(ht | {t for _, fh, fa in upcoming_fixtures for t in (fh, fa)})
    if not teams: st.info("Pick a league/cup in the left sidebar.")
    else:
        st.caption(f"**{selected_comp}** — Finished: **{len(df_league)}** | Upcoming: **{len(upcoming_fixtures)}**")
        if upcoming_fixtures:
            rows = []
            for dt, fh, fa in upcoming_fixtures:
                fo = find_odds(fh, fa, odds_dict) if odds_dict else None
                u1, ux, u2 = (fo[0], fo[1], fo[2]) if fo else (1.85, 3.50, 4.20)
                a = analyze_fixture(df_league, fh, fa, u1, ux, u2)
                rows.append({"Date":dt,"Match":a["Match"],"1/X/2":f"{u1}/{ux}/{u2}" if fo else "-","Tip":f"{a['Tip']} ({a['Conf']}/10)","Safest":a["Safest"],"Combo":a["Combo"],"O/U 2.5":a["O/U 2.5"],"BTTS":a["BTTS"],"Score":a["Score"]})
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True); st.divider()
        dh = teams.index(prefs["home_t"]) if prefs.get("home_t") in teams else 0
        da = teams.index(prefs["away_t"]) if prefs.get("away_t") in teams else min(1, len(teams)-1)
        if upcoming_fixtures:
            lbs = ["-- Keep Selected / Manual --"] + [f"{dt} | {h} vs {a}" for dt, h, a in upcoming_fixtures]
            pk = st.selectbox("📅 Auto-Select Any Match Above", lbs)
            if pk != lbs[0]:
                _, fh, fa = upcoming_fixtures[lbs.index(pk)-1]
                if fh in teams and fa in teams: dh, da = teams.index(fh), teams.index(fa)
        c1, c2 = st.columns(2)
        home_t = c1.selectbox("Home Team", teams, index=dh)
        away_t = c2.selectbox("Away Team", teams, index=da)
        ao = find_odds(home_t, away_t, odds_dict) if odds_dict else None
        do1, dox, do2 = (ao[0], ao[1], ao[2]) if ao else (float(prefs.get("o1",1.85)), float(prefs.get("ox",3.50)), float(prefs.get("o2",4.20)))
        if ao: st.success(f"⚡ Auto-loaded live odds from **{ao[3]}**: `1={do1}` | `X={dox}` | `2={do2}`")
        oc1, oc2, oc3, oc4 = st.columns([1,1,1,1.3])
        o1 = oc1.number_input("Odds 1", min_value=1.01, value=float(do1), step=0.05)
        ox = oc2.number_input("Odds X", min_value=1.01, value=float(dox), step=0.05)
        o2 = oc3.number_input("Odds 2", min_value=1.01, value=float(do2), step=0.05)
        stake = oc4.number_input("Stake", min_value=1.0, value=float(prefs.get("stake",1000.0)), step=100.0)
        nprefs = {"mode":mode,"comp":selected_comp,"home_t":home_t,"away_t":away_t,"o1":o1,"ox":ox,"o2":o2,"stake":stake,"ai_prov":ai_prov}
        if mode == modes[2]: nprefs["sq"] = sq
        if nprefs != prefs: save_state("prefs", nprefs)
        if home_t != away_t:
            res = analyze_fixture(df_league, home_t, away_t, o1, ox, o2); raw = res["_raw"]
            if cur_res is None: cur_res, cur_h2h, cur_comp = res, get_h2h(df_league, home_t, away_t), selected_comp
            m1,m2,m3,m4,m5 = st.columns(5)
            m1.metric("Best Tip", f"{res['Tip']} ({res['Conf']}/10)"); m2.metric("Safest Pick", res["Safest"]); m3.metric("Combo", res["Combo"]); m4.metric("Goals & BTTS", f"{res['O/U 2.5']} | {res['BTTS']}"); m5.metric("Score", res["Score"])
            st.markdown(f'<div class="glass-card"><b>🧠 Verdict ({res["Category"]}):</b> {raw["verdict"]}<br><b>Top 3 Scores:</b> {", ".join(raw["top_scores"])}</div>', unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            if b1.button("➕ Add to Daily Tips", use_container_width=True):
                rc = {k:v for k,v in res.items() if k!="_raw"}; rc["Competition"] = selected_comp
                st.session_state.daily_list.append(rc); save_state("daily_list", st.session_state.daily_list); st.success("Added!")
            podds = {"1":o1,"X":ox,"2":o2,"1X":round(1/(1/o1+1/ox),2),"X2":round(1/(1/o2+1/ox),2)}.get(res["Tip"], o1)
            if b2.button("💾 Save to Bet Tracker", use_container_width=True):
                save_bet(selected_comp, res["Match"], res["Tip"], res["Conf"], podds, stake); st.success("Saved!")
            ch, ca = st.columns(2); h5, a5 = raw["h5"], raw["a5"]
            ch.info(f"🏠 **{home_t} (L5 Home):** `{h5['form']}` | Power `{h5['power']}` | GF `{h5['gf']}` GA `{h5['ga']}` | Corners `{h5['corners']}`")
            ca.info(f"✈️ **{away_t} (L5 Away):** `{a5['form']}` | Power `{a5['power']}` | GF `{a5['gf']}` GA `{a5['ga']}` | Corners `{a5['corners']}`")

with tab_ai:
    st.subheader("🤖 AI Betting Advisor Space")
    if cur_res is None: st.info("Select a match in **Games by Date** or **League Analyzer** first.")
    else:
        st.success(f"**Active Match:** {cur_res['Match']} ({cur_comp}) | Tip: `{cur_res['Tip']}` | Odds: `{cur_res['1']}/{cur_res['X']}/{cur_res['2']}`")
        ctx = build_ctx(cur_res, cur_h2h, cur_comp)
        qc = st.columns(4); qq = None
        if qc[0].button("🎯 Best Pick", use_container_width=True): qq = "Select the single best option and explain why."
        if qc[1].button("🔒 Safest Acca", use_container_width=True): qq = "What is the safest option for an accumulator?"
        if qc[2].button("💎 Value (+EV)", use_container_width=True): qq = "Which option gives the best value against these odds?"
        if qc[3].button("⚽ Goals/BTTS", use_container_width=True): qq = "Pick the best Over/Under or BTTS option."
        with st.form("ai_form", clear_on_submit=True):
            tq = st.text_input("Ask AI anything:", placeholder="e.g. Is 1X & Under 3.5 safe here?")
            sub = st.form_submit_button("Ask AI 🚀")
        prompt = qq if qq else (tq.strip() if sub and tq.strip() else None)
        if prompt:
            st.session_state.ai_messages.append({"role":"user","content":prompt})
            with st.spinner("Analyzing..."):
                rep = smart_advisor(cur_res, prompt) if (ai_prov==ai_provs[0] or not ai_key.strip()) else ask_llm(ai_prov, ai_key, ctx, st.session_state.ai_messages[:-1], prompt)
            st.session_state.ai_messages.append({"role":"assistant","content":rep}); save_state("ai_messages", st.session_state.ai_messages[-20:])
        for m in reversed(st.session_state.ai_messages):
            with st.chat_message(m["role"]): st.markdown(m["content"])
        if st.session_state.ai_messages and st.button("🧹 Clear Chat"):
            st.session_state.ai_messages = []; save_state("ai_messages", []); st.rerun()

with tab_daily:
    st.subheader("🔥 Daily Curated Tips")
    if not st.session_state.daily_list: st.info("Click **Add to Daily Tips** on any match.")
    else:
        st.dataframe(pd.DataFrame(st.session_state.daily_list), hide_index=True, use_container_width=True)
        if st.button("🗑️ Clear Daily List"):
            st.session_state.daily_list = []; save_state("daily_list", []); st.rerun()

with tab_track:
    st.subheader("📒 My Bet History & ROI")
    bdf = load_bets()
    if bdf.empty: st.info("No saved picks yet.")
    else:
        st_df = bdf[bdf["status"].isin(["Won","Lost"])]
        stk = st_df["stake"].sum() if not st_df.empty else 0.0
        prf = st_df["profit"].sum() if not st_df.empty else 0.0
        wr = (len(st_df[st_df["status"]=="Won"])/len(st_df)*100) if not st_df.empty else 0.0
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Picks", len(bdf)); k2.metric("Win Rate", f"{wr:.1f}%"); k3.metric("Profit/Loss", f"{prf:+,.2f}"); k4.metric("ROI", f"{(prf/stk*100 if stk>0 else 0.0):+.1f}%")
        st.divider()
        for _, row in bdf.iterrows():
            cols = st.columns([3,1.5,1,1,1.1,1.1])
            cols[0].write(f"**{row['match_name']}** ({row['date']})")
            cols[1].write(f"`{row['tip']}` ({row['confidence']}/10) @ **{row['odds']}**")
            cols[2].write(f"{row['stake']:.0f}"); cols[3].write(f"**{row['status']}** ({row['profit']:+.0f})")
            if row["status"] == "Pending":
                if cols[4].button("✅ Won", key=f"w_{row['id']}"): update_bet(row["id"], "Won"); st.rerun()
                if cols[5].button("❌ Lost", key=f"l_{row['id']}"): update_bet(row["id"], "Lost"); st.rerun()
