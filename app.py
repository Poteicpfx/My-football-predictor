import sqlite3
from datetime import datetime, timedelta, timezone
import requests
import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson

st.set_page_config(page_title="World Football Predictor Pro", page_icon="⚽", layout="wide")

# --- 0. CUSTOM STADIUM BACKGROUND & GLASS UI THEME ---
st.markdown(
    """
    <style>
    /* Stadium night emerald & midnight gradient background */
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 18% 15%, rgba(16, 185, 129, 0.18), transparent 42%),
            radial-gradient(circle at 85% 20%, rgba(56, 189, 248, 0.14), transparent 40%),
            radial-gradient(circle at 50% 90%, rgba(34, 197, 94, 0.12), transparent 45%),
            linear-gradient(145deg, #040d0a 0%, #091722 50%, #050c14 100%);
        color: #f1f5f9;
    }

    [data-testid="stHeader"] {
        background: rgba(4, 13, 10, 0.55);
        backdrop-filter: blur(8px);
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #06131a 0%, #081c18 100%);
        border-right: 1px solid rgba(16, 185, 129, 0.25);
    }

    /* Glassmorphism cards */
    .hero-banner {
        background: linear-gradient(120deg, rgba(16, 185, 129, 0.20), rgba(15, 23, 42, 0.85));
        border: 1px solid rgba(52, 211, 153, 0.35);
        border-radius: 16px;
        padding: 18px 22px;
        margin-bottom: 16px;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
    }
    .hero-title {
        font-size: 1.7rem;
        font-weight: 800;
        color: #ecfdf5;
        margin: 0;
    }
    .hero-sub {
        font-size: 0.92rem;
        color: #a7f3d0;
        margin-top: 4px;
    }
    .glass-card {
        background: rgba(10, 22, 30, 0.78);
        border: 1px solid rgba(52, 211, 153, 0.25);
        border-radius: 14px;
        padding: 14px 18px;
        margin-bottom: 12px;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.28);
    }
    .pill-green {
        display: inline-block;
        background: rgba(16, 185, 129, 0.22);
        color: #6ee7b7;
        border: 1px solid rgba(16, 185, 129, 0.5);
        border-radius: 999px;
        padding: 3px 10px;
        font-size: 0.82rem;
        font-weight: 700;
    }
    .pill-gold {
        display: inline-block;
        background: rgba(245, 158, 11, 0.20);
        color: #fcd34d;
        border: 1px solid rgba(245, 158, 11, 0.5);
        border-radius: 999px;
        padding: 3px 10px;
        font-size: 0.82rem;
        font-weight: 700;
    }

    /* Metric & Button polish */
    [data-testid="stMetric"] {
        background: rgba(12, 27, 36, 0.82);
        border: 1px solid rgba(52, 211, 153, 0.25);
        border-radius: 12px;
        padding: 10px 12px;
    }
    .stButton > button {
        background: linear-gradient(90deg, #059669, #10b981);
        color: #ffffff;
        border: none;
        border-radius: 10px;
        font-weight: 700;
    }
    .stButton > button:hover {
        background: linear-gradient(90deg, #10b981, #34d399);
        color: #022c22;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 1. COMPETITIONS CATALOG ---
ESPN_CUPS_AND_INTL = {
    "🏆 UEFA Champions League": "uefa.champions",
    "🟠 UEFA Europa League": "uefa.europa",
    "🟢 UEFA Conference League": "uefa.europa.conf",
    "🇪🇺 UEFA Nations League": "uefa.nations",
    "🇪🇸 Spain - Copa del Rey": "esp.copa_del_rey",
    "🇩🇪 Germany - DFB Pokal": "ger.dfb_pokal",
    "🌍 FIFA World Cup": "fifa.world",
    "🌍 CAF Africa Cup of Nations (AFCON)": "caf.nations",
    "🌏 AFC Champions League Elite": "afc.champions",
    "🌎 CONMEBOL Copa Libertadores": "conmebol.libertadores",
    "🌎 CONMEBOL Copa Sudamericana": "conmebol.sudamericana",
}

MAIN_CSV_LEAGUES = {
    "🇬🇧 England - Premier League": "E0",
    "🇬🇧 England - Championship": "E1",
    "🇬🇧 England - League 1": "E2",
    "🇬🇧 England - League 2": "E3",
    "🇬🇧 England - National League": "EC",
    "🏴 Scotland - Premiership": "SC0",
    "🏴 Scotland - Championship": "SC1",
    "🇪🇸 Spain - La Liga": "SP1",
    "🇪🇸 Spain - Segunda": "SP2",
    "🇩🇪 Germany - Bundesliga": "D1",
    "🇩🇪 Germany - 2. Bundesliga": "D2",
    "🇮🇹 Italy - Serie A": "I1",
    "🇮🇹 Italy - Serie B": "I2",
    "🇫🇷 France - Ligue 1": "F1",
    "🇫🇷 France - Ligue 2": "F2",
    "🇳🇱 Netherlands - Eredivisie": "N1",
    "🇧🇪 Belgium - Pro League": "B1",
    "🇵🇹 Portugal - Liga Portugal": "P1",
    "🇹🇷 Turkey - Super Lig": "T1",
    "🇬🇷 Greece - Super League": "G1",
}

WORLD_CSV_LEAGUES = {
    "🇦🇷 Argentina - Primera Division": "ARG",
    "🇧🇷 Brazil - Serie A": "BRA",
    "🇺🇸 USA - MLS": "USA",
    "🇲🇽 Mexico - Liga MX": "MEX",
    "🇯🇵 Japan - J-League": "JPN",
    "🇨🇳 China - Super League": "CHN",
    "🇦🇹 Austria - Bundesliga": "AUT",
    "🇩🇰 Denmark - Superliga": "DNK",
    "🇫🇮 Finland - Veikkausliiga": "FIN",
    "🇮🇪 Ireland - Premier Division": "IRL",
    "🇳🇴 Norway - Eliteserien": "NOR",
    "🇵🇱 Poland - Ekstraklasa": "POL",
    "🇷🇴 Romania - Liga 1": "ROU",
    "🇷🇺 Russia - Premier League": "RUS",
    "🇸🇪 Sweden - Allsvenskan": "SWE",
    "🇨🇭 Switzerland - Super League": "SWZ",
}


# --- 2. DATABASE FOR PERSONAL BET TRACKING ---
def init_db():
    conn = sqlite3.connect("my_bets.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            league TEXT,
            match_name TEXT,
            tip TEXT,
            confidence INTEGER,
            odds REAL,
            stake REAL,
            status TEXT DEFAULT 'Pending',
            profit REAL DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()


def save_bet(league, match_name, tip, confidence, odds, stake):
    conn = sqlite3.connect("my_bets.db")
    conn.execute(
        "INSERT INTO bets (date, league, match_name, tip, confidence, odds, stake) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), league, match_name, tip, confidence, odds, stake),
    )
    conn.commit()
    conn.close()


def update_bet_status(bet_id, status):
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
    conn.close()
    return df


init_db()


# --- 3. DATA LOADERS ---
@st.cache_data(ttl=1800)
def load_espn_competition(slug):
    base = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"
    date_windows = [None, "20260801-20270131", "20260101-20260731", "20250801-20251231"]
    seen_ids = set()
    finished = []
    upcoming = []
    headers = {"User-Agent": "Mozilla/5.0"}

    for win in date_windows:
        url = base if win is None else f"{base}?dates={win}&limit=400"
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                continue
            for ev in r.json().get("events", []):
                eid = ev.get("id")
                if eid in seen_ids:
                    continue
                seen_ids.add(eid)
                comps = ev.get("competitions") or []
                if not comps:
                    continue
                comp = comps[0]
                competitors = comp.get("competitors") or []
                home_c = next((c for c in competitors if c.get("homeAway") == "home"), None)
                away_c = next((c for c in competitors if c.get("homeAway") == "away"), None)
                if not home_c or not away_c:
                    continue
                h_name = (home_c.get("team") or {}).get("displayName")
                a_name = (away_c.get("team") or {}).get("displayName")
                if not h_name or not a_name:
                    continue
                dt = (ev.get("date") or "")[:10]
                state = ((comp.get("status") or {}).get("type") or {}).get("state", "")
                if state == "post":
                    try:
                        hg = int(float(home_c.get("score") or 0))
                        ag = int(float(away_c.get("score") or 0))
                        finished.append({"Date": dt, "HomeTeam": h_name, "AwayTeam": a_name, "FTHG": hg, "FTAG": ag})
                    except (ValueError, TypeError):
                        pass
                elif state == "pre":
                    upcoming.append((dt, h_name, a_name))
        except Exception:
            pass

    df = pd.DataFrame(finished)
    if not df.empty:
        df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("DateParsed").reset_index(drop=True)
    upcoming = sorted(set(upcoming), key=lambda x: x[0])[:30]
    return df, upcoming, ""


@st.cache_data(ttl=3600)
def load_main_csv_league(code):
    frames = []
    for season in ["2526", "2627"]:
        url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
        try:
            df = pd.read_csv(url, encoding="latin1")
            df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
            frames.append(df)
        except Exception:
            pass
    if not frames:
        return pd.DataFrame(), [], "Could not download CSV from football-data.co.uk."
    full = pd.concat(frames, ignore_index=True)
    full["FTHG"] = full["FTHG"].astype(int)
    full["FTAG"] = full["FTAG"].astype(int)
    full["DateParsed"] = pd.to_datetime(full["Date"], dayfirst=True, errors="coerce")
    full = full.sort_values("DateParsed").reset_index(drop=True)
    return full, [], ""


@st.cache_data(ttl=3600)
def load_world_csv_league(code):
    url = f"https://www.football-data.co.uk/new/{code}.csv"
    try:
        df = pd.read_csv(url, encoding="latin1")
        df = df.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG"})
        df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"]).tail(800)
        df["FTHG"] = df["FTHG"].astype(int)
        df["FTAG"] = df["FTAG"].astype(int)
        df["DateParsed"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        df = df.sort_values("DateParsed").reset_index(drop=True)
        return df, [], ""
    except Exception:
        return pd.DataFrame(), [], "Could not download CSV from football-data.co.uk."


@st.cache_data(ttl=3600)
def search_goal_api_leagues(query, api_key):
    try:
        r = requests.get(
            "https://api.goal-api.com/v1/leagues",
            params={"search": query, "limit": 50},
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            timeout=15,
        )
        return r.json().get("data", []) if r.status_code == 200 else []
    except Exception:
        return []


@st.cache_data(ttl=1800)
def load_goal_api_fixtures(league_id, api_key):
    headers = {"Authorization": f"Bearer {api_key.strip()}"}
    all_items = []
    any_success = False
    last_err = ""

    now_utc = datetime.now(timezone.utc)
    from_dt = (now_utc - timedelta(days=90)).strftime("%Y-%m-%d")
    to_dt = (now_utc + timedelta(days=21)).strftime("%Y-%m-%d")

    requests_plan = [
        (f"https://api.goal-api.com/v1/leagues/{league_id}/fixtures", {"limit": 100}),
        (f"https://api.goal-api.com/v1/leagues/{league_id}/results", {"limit": 100}),
        ("https://api.goal-api.com/v1/fixtures", {"leagueId": league_id, "from": from_dt, "to": to_dt, "limit": 100}),
    ]

    for url, base_params in requests_plan:
        for offset in [0, 100]:
            params = {**base_params, "offset": offset}
            try:
                r = requests.get(url, params=params, headers=headers, timeout=15)
                if r.status_code == 401:
                    return pd.DataFrame(), [], "❌ Invalid GOAL API key. Check your key from goal-api.com."
                if r.status_code != 200:
                    last_err = f"API {r.status_code}: {r.text[:140]}"
                    break
                any_success = True
                payload = r.json()
                items = payload.get("data") or []
                all_items.extend(items)
                has_more = (payload.get("pagination") or {}).get("hasMore", False)
                if not has_more or len(items) < 100:
                    break
            except Exception as e:
                last_err = f"Connection error: {e}"
                break

    finished = []
    upcoming = []
    seen_fin = set()
    seen_up = set()

    for m in all_items:
        h = (m.get("homeTeam") or {}).get("name") or m.get("homeTeamName")
        a = (m.get("awayTeam") or {}).get("name") or m.get("awayTeamName")
        if not h or not a:
            continue

        dt = (m.get("kickoffUtc") or m.get("matchDate") or "")[:10]
        hs = m.get("homeScore") if m.get("homeScore") is not None else m.get("homeTeamScore")
        as_ = m.get("awayScore") if m.get("awayScore") is not None else m.get("awayTeamScore")

        period = str(m.get("matchPeriod") or "").upper()
        status = str(m.get("matchStatus") or "").upper()
        is_finished = (
            period == "FINISHED"
            or status in ("FINISHED", "FT", "AET", "PEN", "AFTER PEN.", "PLAYED")
        )
        is_upcoming = (
            period in ("NOT_STARTED", "SCHEDULED")
            or status in ("SCHEDULED", "NOT_STARTED", "NS", "TIMED", "UPCOMING", "")
        )

        if hs is not None and as_ is not None and (is_finished or (not is_upcoming and period != "NOT_STARTED")):
            try:
                key = (dt, h, a)
                if key not in seen_fin:
                    seen_fin.add(key)
                    finished.append({
                        "Date": dt,
                        "HomeTeam": h,
                        "AwayTeam": a,
                        "FTHG": int(float(hs)),
                        "FTAG": int(float(as_)),
                    })
            except (ValueError, TypeError):
                pass
        elif not is_finished:
            key = (dt, h, a)
            if key not in seen_up:
                seen_up.add(key)
                upcoming.append((dt, h, a))

    df = pd.DataFrame(finished)
    if not df.empty:
        df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("DateParsed").reset_index(drop=True)
    upcoming = sorted(upcoming, key=lambda x: x[0])[:40]
    err_out = "" if any_success else last_err
    return df, upcoming, err_out


# --- 4. STATS, POWER RANK & H2H ---
def get_team_metrics(df, team, venue="all", last_n=5):
    if df.empty:
        return {
            "form": "-", "gf": 1.2, "ga": 1.2,
            "o15": 60, "o25": 45, "o35": 20, "btts": 50,
            "corners": 0.0, "shots_ot": 0.0, "power": 50.0,
        }

    if venue == "home":
        games = df[df["HomeTeam"] == team].tail(last_n)
    elif venue == "away":
        games = df[df["AwayTeam"] == team].tail(last_n)
    else:
        games = df[(df["HomeTeam"] == team) | (df["AwayTeam"] == team)].tail(last_n)

    if games.empty:
        return {
            "form": "-", "gf": 1.2, "ga": 1.2,
            "o15": 60, "o25": 45, "o35": 20, "btts": 50,
            "corners": 0.0, "shots_ot": 0.0, "power": 50.0,
        }

    form_list = []
    gf_tot = ga_tot = o15 = o25 = o35 = btts = corners_tot = sot_tot = pts = 0
    has_corners = "HC" in games.columns and "AC" in games.columns
    has_sot = "HST" in games.columns and "AST" in games.columns

    for _, r in games.iterrows():
        is_h = r["HomeTeam"] == team
        gf = r["FTHG"] if is_h else r["FTAG"]
        ga = r["FTAG"] if is_h else r["FTHG"]
        gf_tot += gf
        ga_tot += ga
        tot = gf + ga
        if gf > ga:
            form_list.append("W")
            pts += 3
        elif gf == ga:
            form_list.append("D")
            pts += 1
        else:
            form_list.append("L")

        if tot > 1:
            o15 += 1
        if tot > 2:
            o25 += 1
        if tot > 3:
            o35 += 1
        if gf > 0 and ga > 0:
            btts += 1
        if has_corners and pd.notna(r["HC"]) and pd.notna(r["AC"]):
            corners_tot += r["HC"] if is_h else r["AC"]
        if has_sot and pd.notna(r["HST"]) and pd.notna(r["AST"]):
            sot_tot += r["HST"] if is_h else r["AST"]

    n = len(games)
    pts_pct = (pts / (n * 3)) * 100
    gd_avg = (gf_tot - ga_tot) / n
    power = float(np.clip(pts_pct * 0.65 + (gd_avg * 10) + 18, 10, 99))

    return {
        "form": "".join(form_list),
        "gf": round(gf_tot / n, 2),
        "ga": round(ga_tot / n, 2),
        "o15": round((o15 / n) * 100),
        "o25": round((o25 / n) * 100),
        "o35": round((o35 / n) * 100),
        "btts": round((btts / n) * 100),
        "corners": round(corners_tot / n, 1) if has_corners else 0.0,
        "shots_ot": round(sot_tot / n, 1) if has_sot else 0.0,
        "power": round(power, 1),
    }


def get_h2h(df, home, away, last_n=5):
    if df.empty:
        return pd.DataFrame()
    h2h = df[((df["HomeTeam"] == home) & (df["AwayTeam"] == away)) | ((df["HomeTeam"] == away) & (df["AwayTeam"] == home))].tail(last_n)
    if h2h.empty:
        return pd.DataFrame()
    return h2h[["Date", "HomeTeam", "FTHG", "FTAG", "AwayTeam"]].iloc[::-1]


# --- 5. POISSON PREDICTION ENGINE (FULL ANALYZED OPTIONS) ---
def analyze_fixture(df, home, away, odds_1=1.85, odds_x=3.50, odds_2=4.20):
    h_all = get_team_metrics(df, home, "all", last_n=15)
    a_all = get_team_metrics(df, away, "all", last_n=15)
    h_last5 = get_team_metrics(df, home, "home", last_n=5)
    a_last5 = get_team_metrics(df, away, "away", last_n=5)

    if h_last5["form"] == "-" and h_all["form"] != "-":
        h_last5 = h_all
    if a_last5["form"] == "-" and a_all["form"] != "-":
        a_last5 = a_all

    avg_hg = max(float(df["FTHG"].mean()), 0.5) if not df.empty else 1.35
    avg_ag = max(float(df["FTAG"].mean()), 0.5) if not df.empty else 1.15

    h_att = (h_last5["gf"] * 0.65 + h_all["gf"] * 0.35) / avg_hg
    a_def = (a_last5["ga"] * 0.65 + a_all["ga"] * 0.35) / avg_hg
    a_att = (a_last5["gf"] * 0.65 + a_all["gf"] * 0.35) / avg_ag
    h_def = (h_last5["ga"] * 0.65 + a_all["ga"] * 0.35) / avg_ag

    exp_hg = float(np.clip(h_att * a_def * avg_hg, 0.25, 4.0))
    exp_ag = float(np.clip(a_att * h_def * avg_ag, 0.25, 4.0))

    max_g = 7
    matrix = np.zeros((max_g, max_g))
    for i in range(max_g):
        for j in range(max_g):
            matrix[i, j] = poisson.pmf(i, exp_hg) * poisson.pmf(j, exp_ag)

    p_1 = float(np.sum(np.tril(matrix, -1)))
    p_x = float(np.sum(np.diag(matrix)))
    p_2 = float(np.sum(np.triu(matrix, 1)))
    p_1x = p_1 + p_x
    p_x2 = p_2 + p_x
    p_12 = p_1 + p_2

    p_o05 = float(sum(matrix[i, j] for i in range(max_g) for j in range(max_g) if i + j > 0))
    p_o15 = float(sum(matrix[i, j] for i in range(max_g) for j in range(max_g) if i + j > 1))
    p_o25 = float(sum(matrix[i, j] for i in range(max_g) for j in range(max_g) if i + j > 2))
    p_o35 = float(sum(matrix[i, j] for i in range(max_g) for j in range(max_g) if i + j > 3))
    p_u25 = 1.0 - p_o25
    p_u35 = 1.0 - p_o35
    p_btts = float(sum(matrix[i, j] for i in range(1, max_g) for j in range(1, max_g)))
    p_ng = 1.0 - p_btts

    # Top 3 Exact Scores
    flat_idx = np.argsort(matrix.ravel())[::-1][:3]
    top_scores = []
    for idx in flat_idx:
        si, sj = np.unravel_index(idx, matrix.shape)
        top_scores.append(f"{si}:{sj} ({matrix[si, sj]*100:.0f}%)")
    score_tip = top_scores[0].split(" ")[0]

    probs = {"1": p_1, "X": p_x, "2": p_2}
    best_pick = max(probs, key=probs.get)
    best_prob = probs[best_pick]

    if best_pick == "1" and best_prob < 0.52 and p_1x >= 0.72:
        display_pick, conf_prob = "1X", p_1x
    elif best_pick == "2" and best_prob < 0.52 and p_x2 >= 0.72:
        display_pick, conf_prob = "X2", p_x2
    else:
        display_pick, conf_prob = best_pick, best_prob

    confidence = int(np.clip(round((conf_prob - 0.25) / 0.60 * 9 + 1), 1, 10))

    # Safest Accumulator Option & Combo Option
    safe_candidates = {
        "1X (Home/Draw)": p_1x,
        "X2 (Away/Draw)": p_x2,
        "12 (Either Wins)": p_12,
        "Over 1.5 Goals": p_o15,
        "Under 3.5 Goals": p_u35,
    }
    safest_name = max(safe_candidates, key=safe_candidates.get)
    safest_prob = safe_candidates[safest_name]

    if p_1 >= 0.55 and p_o15 >= 0.68:
        combo_pick = "1 & Over 1.5"
    elif p_2 >= 0.55 and p_o15 >= 0.68:
        combo_pick = "2 & Over 1.5"
    elif p_1x >= 0.72 and p_u35 >= 0.65:
        combo_pick = "1X & Under 3.5"
    elif p_x2 >= 0.72 and p_u35 >= 0.65:
        combo_pick = "X2 & Under 3.5"
    elif p_o25 >= 0.55 and p_btts >= 0.55:
        combo_pick = "Over 2.5 & BTTS Yes"
    else:
        combo_pick = f"{display_pick} & {'Over 1.5' if p_o15 >= 0.65 else 'Under 3.5'}"

    ev_1 = (p_1 * odds_1) - 1
    ev_x = (p_x * odds_x) - 1
    ev_2 = (p_2 * odds_2) - 1
    ev_map = {"1": ev_1, "X": ev_x, "2": ev_2}
    best_ev_side = max(ev_map, key=ev_map.get)
    best_ev = ev_map[best_ev_side]

    tags = []
    pick_odds = {"1": odds_1, "X": odds_x, "2": odds_2}.get(best_pick, 1.45)
    if confidence >= 8 and pick_odds <= 1.65:
        tags.append("🔒 Banker")
    if best_ev >= 0.05:
        tags.append(f"💎 Value ({best_ev_side}: +{best_ev*100:.0f}% EV)")
    if p_x >= 0.29 and abs(h_last5["power"] - a_last5["power"]) <= 12:
        tags.append("⚖️ Draw Watch")

    ou_label = "Over" if p_o25 >= 0.52 else "Under"
    pwr_diff = round(h_last5["power"] - a_last5["power"], 1)
    verdict = (
        f"{home} carries {exp_hg:.2f} expected goals vs {away}'s {exp_ag:.2f}. "
        f"Power Rank edge is {pwr_diff:+.1f} toward {home if pwr_diff >= 0 else away}. "
        f"Top safe angle: {safest_name} ({safest_prob*100:.0f}%); Combo angle: {combo_pick}."
    )

    return {
        "Match": f"{home} vs {away}",
        "Tip": display_pick,
        "Conf": confidence,
        "Safest": f"{safest_name} ({safest_prob*100:.0f}%)",
        "Combo": combo_pick,
        "1": odds_1,
        "X": odds_x,
        "2": odds_2,
        "O/U 2.5": f"{ou_label} ({p_o25*100:.0f}%)",
        "BTTS": f"{p_btts*100:.0f}%",
        "Score": score_tip,
        "Category": " | ".join(tags) if tags else "Standard",
        "_raw": {
            "home": home, "away": away, "exp_hg": exp_hg, "exp_ag": exp_ag,
            "p_1": p_1, "p_x": p_x, "p_2": p_2, "p_1x": p_1x, "p_x2": p_x2, "p_12": p_12,
            "p_o05": p_o05, "p_o15": p_o15, "p_o25": p_o25, "p_o35": p_o35,
            "p_u25": p_u25, "p_u35": p_u35, "p_btts": p_btts, "p_ng": p_ng,
            "top_scores": top_scores, "safest_name": safest_name, "safest_prob": safest_prob,
            "combo_pick": combo_pick, "verdict": verdict,
            "ev": ev_map, "h_last5": h_last5, "a_last5": a_last5,
        },
    }


# --- 6. AI ADVISOR ENGINE ---
def build_match_context(res, h2h_df, comp_label):
    raw = res["_raw"]
    h5 = raw["h_la
