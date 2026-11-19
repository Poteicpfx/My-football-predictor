import json, sqlite3
from datetime import datetime, timedelta, timezone
import requests
import streamlit as st
import pandas as pd

ESPN_CUPS = {"🏆 UEFA Champions League": "uefa.champions", "🟠 UEFA Europa League": "uefa.europa", "🟢 UEFA Conference League": "uefa.europa.conf", "🇪🇺 UEFA Nations League": "uefa.nations", "🇪🇸 Spain - Copa del Rey": "esp.copa_del_rey", "🇩🇪 Germany - DFB Pokal": "ger.dfb_pokal", "🌍 FIFA World Cup": "fifa.world", "🌍 CAF AFCON": "caf.nations", "🌏 AFC Champions League": "afc.champions", "🌎 Copa Libertadores": "conmebol.libertadores", "🌎 Copa Sudamericana": "conmebol.sudamericana"}
SCAN_LEAGUES = {"🇬🇧 Premier League": "eng.1", "🇬🇧 Championship": "eng.2", "🇪🇸 La Liga": "esp.1", "🇩🇪 Bundesliga": "ger.1", "🇮🇹 Serie A": "ita.1", "🇫🇷 Ligue 1": "fra.1", "🇳🇱 Eredivisie": "ned.1", "🇵🇹 Liga Portugal": "por.1", "🏆 UEFA Champions League": "uefa.champions", "🟠 UEFA Europa League": "uefa.europa", "🟢 UEFA Conference League": "uefa.europa.conf", "🇪🇺 UEFA Nations League": "uefa.nations", "🇪🇸 Copa del Rey": "esp.copa_del_rey"}
MAIN_LEAGUES = {"🇬🇧 England - Premier League": "E0", "🇬🇧 England - Championship": "E1", "🇬🇧 England - League 1": "E2", "🇬🇧 England - League 2": "E3", "🏴 Scotland - Premiership": "SC0", "🇪🇸 Spain - La Liga": "SP1", "🇪🇸 Spain - Segunda": "SP2", "🇩🇪 Germany - Bundesliga": "D1", "🇩🇪 Germany - 2. Bundesliga": "D2", "🇮🇹 Italy - Serie A": "I1", "🇮🇹 Italy - Serie B": "I2", "🇫🇷 France - Ligue 1": "F1", "🇫🇷 France - Ligue 2": "F2", "🇳🇱 Netherlands - Eredivisie": "N1", "🇧🇪 Belgium - Pro League": "B1", "🇵🇹 Portugal - Liga Portugal": "P1", "🇹🇷 Turkey - Super Lig": "T1", "🇬🇷 Greece - Super League": "G1"}
WORLD_LEAGUES = {"🇦🇷 Argentina - Primera": "ARG", "🇧🇷 Brazil - Serie A": "BRA", "🇺🇸 USA - MLS": "USA", "🇲🇽 Mexico - Liga MX": "MEX", "🇯🇵 Japan - J-League": "JPN", "🇨🇳 China - Super League": "CHN", "🇦🇹 Austria - Bundesliga": "AUT", "🇩🇰 Denmark - Superliga": "DNK", "🇳🇴 Norway - Eliteserien": "NOR", "🇵🇱 Poland - Ekstraklasa": "POL", "🇸🇪 Sweden - Allsvenskan": "SWE", "🇨🇭 Switzerland - Super League": "SWZ"}

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
    c = sqlite3.connect("my_bets.db"); c.execute("INSERT INTO bets (date,league,match_name,tip,confidence,odds,stake) VALUES (?,?,?,?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), lg, m, tip, conf, odds, stake)); c.commit(); c.close()

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
    return o1, ox, o2, ((od.get("provider") or {}).get("name", "ESPN Odds") if o1 else "")

def norm_t(s): return "".join(c for c in s.lower() if c.isalnum() or c == " ").strip()

def find_odds(h, a, od):
    if not od: return None
    nh, na = norm_t(h), norm_t(a)
    if (nh, na) in od: return od[(nh, na)]
    sw = {"fc","cf","sc","ac","afc","club","city","united","real"}
    hw = {w for w in nh.split() if len(w) > 2 and w not in sw}
    aw = {w for w in na.split() if len(w) > 2 and w not in sw}
    for (oh, oa), val in od.items():
        if (nh in oh or oh in nh or (hw and any(w in oh for w in hw))) and (na in oa or oa in na or (aw and any(w in oa for w in aw))):
            return val
    return None

@st.cache_data(ttl=1800)
def load_the_odds_api(key):
    if not key.strip(): return [], {}, ""
    try:
        r = requests.get("https://api.the-odds-api.com/v4/sports/upcoming/odds", params={"apiKey": key.strip(), "regions": "uk,eu", "markets": "h2h", "oddsFormat": "decimal"}, timeout=15)
        if r.status_code != 200: return [], {}, f"The Odds API {r.status_code}: {r.text[:100]}"
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
