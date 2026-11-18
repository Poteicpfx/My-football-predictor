import sqlite3
from datetime import datetime
import requests
import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson

st.set_page_config(page_title="World Football Predictor + AI", page_icon="🌍", layout="wide")

# --- 1. COMPETITIONS CATALOG ---
ESPN_CUPS_AND_INTL = {
    "🏆 UEFA Champions League": "uefa.champions",
    "🟠 UEFA Europa League": "uefa.europa",
    "🟢 UEFA Conference League": "uefa.europa.conf",
    "🇪🇺 UEFA Nations League": "uefa.nations",
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
    upcoming = sorted(set(upcoming), key=lambda x: x[0])[:20]
    return df, upcoming


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
        return pd.DataFrame(), []
    full = pd.concat(frames, ignore_index=True)
    full["FTHG"] = full["FTHG"].astype(int)
    full["FTAG"] = full["FTAG"].astype(int)
    full["DateParsed"] = pd.to_datetime(full["Date"], dayfirst=True, errors="coerce")
    full = full.sort_values("DateParsed").reset_index(drop=True)
    return full, []


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
        return df, []
    except Exception:
        return pd.DataFrame(), []


@st.cache_data(ttl=3600)
def search_goal_api_leagues(query, api_key):
    try:
        r = requests.get(
            "https://api.goal-api.com/v1/leagues",
            params={"search": query, "limit": 50},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        return r.json().get("data", []) if r.status_code == 200 else []
    except Exception:
        return []


@st.cache_data(ttl=1800)
def load_goal_api_fixtures(league_id, api_key):
    try:
        r = requests.get(
            f"https://api.goal-api.com/v1/leagues/{league_id}/fixtures",
            params={"limit": 300},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if r.status_code != 200:
            return pd.DataFrame(), []
        items = r.json().get("data", [])
        finished = []
        upcoming = []
        for m in items:
            h = m.get("homeTeamName")
            a = m.get("awayTeamName")
            if not h or not a:
                continue
            dt = (m.get("kickoffUtc") or "")[:10]
            hs = m.get("homeTeamScore")
            as_ = m.get("awayTeamScore")
            status = str(m.get("matchStatus") or "").upper()
            if hs is not None and as_ is not None and status in ("FINISHED", "FT", "AET", "PEN"):
                try:
                    finished.append({"Date": dt, "HomeTeam": h, "AwayTeam": a, "FTHG": int(float(hs)), "FTAG": int(float(as_))})
                except ValueError:
                    pass
            elif status in ("SCHEDULED", "NOT_STARTED", "NS", "TIMED", "UPCOMING"):
                upcoming.append((dt, h, a))
        df = pd.DataFrame(finished)
        if not df.empty:
            df["DateParsed"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.sort_values("DateParsed").reset_index(drop=True)
        return df, upcoming[:20]
    except Exception:
        return pd.DataFrame(), []


# --- 4. STATS, POWER RANK & H2H ---
def get_team_metrics(df, team, venue="all", last_n=5):
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
    h2h = df[((df["HomeTeam"] == home) & (df["AwayTeam"] == away)) | ((df["HomeTeam"] == away) & (df["AwayTeam"] == home))].tail(last_n)
    if h2h.empty:
        return pd.DataFrame()
    return h2h[["Date", "HomeTeam", "FTHG", "FTAG", "AwayTeam"]].iloc[::-1]


# --- 5. POISSON PREDICTION ENGINE ---
def analyze_fixture(df, home, away, odds_1, odds_x, odds_2):
    h_all = get_team_metrics(df, home, "all", last_n=15)
    a_all = get_team_metrics(df, away, "all", last_n=15)
    h_last5 = get_team_metrics(df, home, "home", last_n=5)
    a_last5 = get_team_metrics(df, away, "away", last_n=5)

    if h_last5["form"] == "-" and h_all["form"] != "-":
        h_last5 = h_all
    if a_last5["form"] == "-" and a_all["form"] != "-":
        a_last5 = a_all

    avg_hg = max(float(df["FTHG"].mean()), 0.5)
    avg_ag = max(float(df["FTAG"].mean()), 0.5)

    h_att = (h_last5["gf"] * 0.65 + h_all["gf"] * 0.35) / avg_hg
    a_def = (a_last5["ga"] * 0.65 + a_all["ga"] * 0.35) / avg_hg
    a_att = (a_last5["gf"] * 0.65 + a_all["gf"] * 0.35) / avg_ag
    h_def = (h_last5["ga"] * 0.65 + h_all["ga"] * 0.35) / avg_ag

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

    p_o15 = float(sum(matrix[i, j] for i in range(max_g) for j in range(max_g) if i + j > 1))
    p_o25 = float(sum(matrix[i, j] for i in range(max_g) for j in range(max_g) if i + j > 2))
    p_o35 = float(sum(matrix[i, j] for i in range(max_g) for j in range(max_g) if i + j > 3))
    p_btts = float(sum(matrix[i, j] for i in range(1, max_g) for j in range(1, max_g)))

    bi, bj = np.unravel_index(np.argmax(matrix), matrix.shape)
    score_tip = f"{bi}:{bj}"

    probs = {"1": p_1, "X": p_x, "2": p_2}
    best_pick = max(probs, key=probs.get)
    best_prob = probs[best_pick]

    if best_pick == "1" and best_prob < 0.52 and (p_1 + p_x) >= 0.72:
        display_pick, conf_prob = "1X", p_1 + p_x
    elif best_pick == "2" and best_prob < 0.52 and (p_2 + p_x) >= 0.72:
        display_pick, conf_prob = "X2", p_2 + p_x
    else:
        display_pick, conf_prob = best_pick, best_prob

    confidence = int(np.clip(round((conf_prob - 0.25) / 0.60 * 9 + 1), 1, 10))

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

    return {
        "Match": f"{home} vs {away}",
        "Tip": display_pick,
        "Conf": confidence,
        "1": odds_1,
        "X": odds_x,
        "2": odds_2,
        "O/U 2.5": f"{ou_label} ({p_o25*100:.0f}%)",
        "BTTS": f"{p_btts*100:.0f}%",
        "Score": score_tip,
        "Category": " | ".join(tags) if tags else "Standard",
        "_raw": {
            "home": home, "away": away, "exp_hg": exp_hg, "exp_ag": exp_ag,
            "p_1": p_1, "p_x": p_x, "p_2": p_2,
            "p_o15": p_o15, "p_o25": p_o25, "p_o35": p_o35, "p_btts": p_btts,
            "ev": ev_map, "h_last5": h_last5, "a_last5": a_last5,
        },
    }


# --- 6. AI ADVISOR ENGINE (BUILT-IN + GROQ + GEMINI WITH AUTO-FALLBACK) ---
def build_match_context(res, h2h_df, comp_label):
    raw = res["_raw"]
    h5 = raw["h_last5"]
    a5 = raw["a_last5"]
    h2h_txt = "No recent H2H found." if h2h_df.empty else h2h_df.to_string(index=False)

    return f"""Competition: {comp_label}
Match: {raw['home']} (Home) vs {raw['away']} (Away)
Bookmaker Odds: Home(1)={res['1']}, Draw(X)={res['X']}, Away(2)={res['2']}
Poisson Expected Goals: {raw['home']} {raw['exp_hg']:.2f} - {raw['exp_ag']:.2f} {raw['away']}
Model Probabilities:
- Home Win (1): {raw['p_1']*100:.1f}% (EV: {raw['ev']['1']*100:+.1f}%)
- Draw (X): {raw['p_x']*100:.1f}% (EV: {raw['ev']['X']*100:+.1f}%)
- Away Win (2): {raw['p_2']*100:.1f}% (EV: {raw['ev']['2']*100:+.1f}%)
- Home or Draw (1X): {(raw['p_1']+raw['p_x'])*100:.1f}%
- Away or Draw (X2): {(raw['p_2']+raw['p_x'])*100:.1f}%
- Over 1.5 Goals: {raw['p_o15']*100:.1f}%
- Over 2.5 Goals: {raw['p_o25']*100:.1f}% | Under 2.5 Goals: {(1-raw['p_o25'])*100:.1f}%
- Over 3.5 Goals: {raw['p_o35']*100:.1f}% | Under 3.5 Goals: {(1-raw['p_o35'])*100:.1f}%
- BTTS Yes (GG): {raw['p_btts']*100:.1f}% | BTTS No (NG): {(1-raw['p_btts'])*100:.1f}%
- Most Likely Score: {res['Score']}
- Model Top Tip: {res['Tip']} (Confidence: {res['Conf']}/10, Tag: {res['Category']})

Home Last 5 (Home Only): Form={h5['form']}, GF={h5['gf']}, GA={h5['ga']}, PowerRank={h5['power']}, Over2.5={h5['o25']}%, BTTS={h5['btts']}%, Corners={h5['corners']}, ShotsOT={h5['shots_ot']}
Away Last 5 (Away Only): Form={a5['form']}, GF={a5['gf']}, GA={a5['ga']}, PowerRank={a5['power']}, Over2.5={a5['o25']}%, BTTS={a5['btts']}%, Corners={a5['corners']}, ShotsOT={a5['shots_ot']}

Recent H2H:
{h2h_txt}"""


def builtin_smart_advisor(res, question):
    raw = res["_raw"]
    markets = {
        f"{raw['home']} Win (1)": raw["p_1"],
        "Draw (X)": raw["p_x"],
        f"{raw['away']} Win (2)": raw["p_2"],
        f"{raw['home']} or Draw (1X)": raw["p_1"] + raw["p_x"],
        f"{raw['away']} or Draw (X2)": raw["p_2"] + raw["p_x"],
        "Over 1.5 Goals": raw["p_o15"],
        "Over 2.5 Goals": raw["p_o25"],
        "Under 2.5 Goals": 1 - raw["p_o25"],
        "Under 3.5 Goals": 1 - raw["p_o35"],
        "BTTS Yes (GG)": raw["p_btts"],
        "BTTS No (NG)": 1 - raw["p_btts"],
    }
    ranked = sorted(markets.items(), key=lambda x: x[1], reverse=True)
    safest_1, p1 = ranked[0]
    safest_2, p2 = ranked[1]
    safest_3, p3 = ranked[2]

    best_ev_side = max(raw["ev"], key=raw["ev"].get)
    best_ev_val = raw["ev"][best_ev_side]
    q = question.lower()

    if "value" in q or "odds" in q or "high" in q:
        if best_ev_val > 0:
            focus = f"💎 **Best Value Pick:** `{best_ev_side}` (`{best_ev_val*100:+.1f}%` EV against your odds)."
        else:
            focus = "⚠️ None of the 1X2 odds show positive value (+EV) right now—bookmaker margins are tight."
    elif "goal" in q or "over" in q or "under" in q or "btts" in q or "gg" in q:
        goal_markets = [(k, v) for k, v in ranked if ("Goals" in k or "BTTS" in k)]
        exp_tot = raw["exp_hg"] + raw["exp_ag"]
        focus = f"⚽ **Best Goals Option:** **{goal_markets[0][0]}** (`{goal_markets[0][1]*100:.1f}%` probability) | Expected total goals: `{exp_tot:.2f}`."
    else:
        focus = f"🎯 **Top Overall Recommendation:** **{safest_1}** (`{p1*100:.1f}%` probability)."

    return (
        f"**Built-in Smart Analysis for {res['Match']}**\n\n"
        f"{focus}\n\n"
        f"**Top 3 Highest-Probability Markets:**\n"
        f"1. **{safest_1}** — `{p1*100:.1f}%`\n"
        f"2. **{safest_2}** — `{p2*100:.1f}%`\n"
        f"3. **{safest_3}** — `{p3*100:.1f}%`\n\n"
        f"**Value Check:** Best 1X2 edge is `{best_ev_side}` (`{best_ev_val*100:+.1f}%` EV) | **Projected Score:** `{res['Score']}`\n\n"
        "*(Paste a free Groq or Gemini key in the sidebar to chat with a live AI model.)*"
    )


def ask_live_ai(provider, api_key, match_context, chat_history, user_question):
    system_prompt = (
        "You are an expert, disciplined football betting analyst inside the user's personal prediction app. "
        "Base your answer strictly on the match stats, Poisson probabilities, Power Ranks, H2H, and bookmaker odds provided below. "
        "Never invent stats or injuries not in the data. Always recommend the single best option (and an accumulator-safe backup if helpful), "
        "clearly explain why using the numbers, and state the main risk. Keep answers crisp and practical.\n\n"
        f"--- CURRENT MATCH DATA ---\n{match_context}"
    )

    clean_key = api_key.strip()

    if provider == "Groq (Free AI)":
        msgs = [{"role": "system", "content": system_prompt}]
        for m in chat_history[-6:]:
            msgs.append({"role": m["role"], "content": m["content"]})
        msgs.append({"role": "user", "content": user_question})

        groq_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
        last_err = ""
        for model_name in groq_models:
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {clean_key}", "Content-Type": "application/json"},
                    json={"model": model_name, "messages": msgs, "temperature": 0.3},
                    timeout=25,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
                last_err = f"Groq ({model_name}) Error {r.status_code}: {r.text}"
                if r.status_code == 401:
                    return "❌ Invalid Groq API key. Check that you copied the full `gsk_...` key from console.groq.com."
            except Exception as e:
                last_err = f"Connection error: {e}"
        return last_err

    elif provider == "Google Gemini (Free AI)":
        contents = []
        for m in chat_history[-6:]:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        contents.append({"role": "user", "parts": [{"text": user_question}]})

        gemini_models = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash"]
        last_err = ""
        for model_name in gemini_models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={clean_key}"
                r = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "system_instruction": {"parts": [{"text": system_prompt}]},
                        "contents": contents,
                        "generationConfig": {"temperature": 0.3},
                    },
                    timeout=25,
                )
                if r.status_code == 200:
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                last_err = f"Gemini ({model_name}) Error {r.status_code}: {r.text}"
                if r.status_code in (400, 403) and "API_KEY_INVALID" in r.text:
                    return "❌ Invalid Gemini API key. Check that you copied the full `AIza...` key from aistudio.google.com."
            except Exception as e:
                last_err = f"Connection error: {e}"
        return last_err

    return "Unknown AI provider selected."


# --- 7. SESSION STATE & SIDEBAR ---
if "daily_list" not in st.session_state:
    st.session_state.daily_list = []
if "ai_messages" not in st.session_state:
    st.session_state.ai_messages = []

st.sidebar.header("🌍 Select Competition")
mode = st.sidebar.radio(
    "Category",
    [
        "🏆 UEFA, CAF, AFC & FIFA Cups (Free, No Key)",
        "⚽ 36 Global Domestic Leagues (Free, No Key)",
        "🔎 All 1,000+ Competitions (Free GOAL API Key)",
    ],
)

df_league = pd.DataFrame()
upcoming_fixtures = []
selected_comp_label = ""

if mode == "🏆 UEFA, CAF, AFC & FIFA Cups (Free, No Key)":
    selected_comp_label = st.sidebar.selectbox("Select Tournament", list(ESPN_CUPS_AND_INTL.keys()))
    custom_slug = st.sidebar.text_input("Or type any ESPN slug (optional)", placeholder="e.g. eng.1, esp.1, usa.1")
    slug = custom_slug.strip() if custom_slug.strip() else ESPN_CUPS_AND_INTL[selected_comp_label]
    if custom_slug.strip():
        selected_comp_label = f"Custom ({slug})"
    df_league, upcoming_fixtures = load_espn_competition(slug)

elif mode == "⚽ 36 Global Domestic Leagues (Free, No Key)":
    all_builtin = {**MAIN_CSV_LEAGUES, **WORLD_CSV_LEAGUES}
    selected_comp_label = st.sidebar.selectbox("Select League", list(all_builtin.keys()))
    code = all_builtin[selected_comp_label]
    if selected_comp_label in MAIN_CSV_LEAGUES:
        df_league, upcoming_fixtures = load_main_csv_league(code)
    else:
        df_league, upcoming_fixtures = load_world_csv_league(code)

else:
    goal_key = st.sidebar.text_input("GOAL API Key (Free at goal-api.com)", type="password")
    quick_pick = st.sidebar.selectbox(
        "Quick Search Presets",
        ["Custom Search", "CAF Champions League", "CAF Confederation Cup", "NPFL", "AFC Champions League", "FIFA Club World Cup", "Saudi Pro League"],
    )
    default_q = "" if quick_pick == "Custom Search" else quick_pick
    search_q = st.sidebar.text_input("Search ANY of 1,000+ Leagues", value=default_q, placeholder="Type league or cup name...")
    if goal_key and search_q:
        found = search_goal_api_leagues(search_q, goal_key)
        if found:
            options = {f"{item.get('name')} ({(item.get('country') or {}).get('name', 'Intl')})": item.get("id") for item in found}
            selected_comp_label = st.sidebar.selectbox("Pick Competition", list(options.keys()))
            df_league, upcoming_fixtures = load_goal_api_fixtures(options[selected_comp_label], goal_key)
        else:
            st.sidebar.warning("No competition matched.")
    else:
        st.sidebar.info("Get a free key (1,000 req/day, no card) at goal-api.com.")

st.sidebar.divider()
st.sidebar.header("🤖 AI Space Settings")
ai_provider = st.sidebar.selectbox(
    "AI Engine",
    ["Built-in Smart Advisor (No Key)", "Groq (Free AI)", "Google Gemini (Free AI)"],
)
ai_api_key = ""
if ai_provider != "Built-in Smart Advisor (No Key)":
    ai_api_key = st.sidebar.text_input("Paste Free AI Key", type="password")
    if not ai_api_key:
        st.sidebar.caption("Get a free key (no card) at console.groq.com or aistudio.google.com")


# --- 8. MAIN DASHBOARD ---
st.title("🌍 My World Football Predictor + AI")
tab_analyze, tab_ai, tab_daily, tab_tracker = st.tabs(["🔍 Match Analyzer", "🤖 AI Space", "🔥 Daily Tips & Categories", "📒 My Bet Tracker"])

current_res = None
current_h2h = pd.DataFrame()

with tab_analyze:
    if df_league.empty:
        st.info("Select a competition in the left sidebar to load teams and upcoming matches.")
    else:
        st.caption(f"Loaded **{len(df_league)}** matches for **{selected_comp_label}**")
        teams = sorted(set(df_league["HomeTeam"].unique()) | set(df_league["AwayTeam"].unique()))

        default_h_idx = 0
        default_a_idx = min(1, len(teams) - 1)
        if upcoming_fixtures:
            fix_labels = ["-- Manual Pick --"] + [f"{dt} | {h} vs {a}" for dt, h, a in upcoming_fixtures]
            picked_fix = st.selectbox("📅 Upcoming Fixtures Found (Click to Auto-Select)", fix_labels)
            if picked_fix != "-- Manual Pick --":
                idx = fix_labels.index(picked_fix) - 1
                _, fh, fa = upcoming_fixtures[idx]
                if fh in teams and fa in teams:
                    default_h_idx = teams.index(fh)
                    default_a_idx = teams.index(fa)
                else:
                    st.warning(f"One of these teams ({fh} or {fa}) has no finished match history in this tournament yet.")

        c1, c2 = st.columns(2)
        home_team = c1.selectbox("Home Team", teams, index=default_h_idx)
        away_team = c2.selectbox("Away Team", teams, index=default_a_idx)

        st.markdown("**Enter Bookmaker Odds (to check +EV Value & Bankers):**")
        oc1, oc2, oc3, oc4 = st.columns([1, 1, 1, 1.5])
        o1 = oc1.number_input("Home (1)", min_value=1.01, value=1.85, step=0.05)
        ox = oc2.number_input("Draw (X)", min_value=1.01, value=3.50, step=0.05)
        o2 = oc3.number_input("Away (2)", min_value=1.01, value=4.20, step=0.05)
        stake_amt = oc4.number_input("Stake Amount", min_value=1.0, value=1000.0, step=100.0)

        if home_team == away_team:
            st.warning("Pick two different teams.")
        else:
            res = analyze_fixture(df_league, home_team, away_team, o1, ox, o2)
            raw = res["_raw"]
            current_res = res
            current_h2h = get_h2h(df_league, home_team, away_team)

            st.divider()
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Confidence", f"{res['Conf']}/10", res["Tip"])
            m2.metric("O/U 2.5 Goals", res["O/U 2.5"])
            m3.metric("BTTS (GG)", res["BTTS"])
            m4.metric("Score Tip", res["Score"])
            m5.metric("Power Rank (H / A)", f"{raw['h_last5']['power']} / {raw['a_last5']['power']}")

            st.info(f"**Classification:** {res['Category']}  |  **Expected Goals:** {home_team} `{raw['exp_hg']:.2f}` — `{raw['exp_ag']:.2f}` {away_team}")

            b1, b2 = st.columns(2)
            if b1.button("➕ Add to Today's Tips List", use_container_width=True):
                res_copy = {k: v for k, v in res.items() if k != "_raw"}
                res_copy["Competition"] = selected_comp_label
                st.session_state.daily_list.append(res_copy)
                st.success("Added to Daily Tips tab!")

            dc_1x = round(1 / (1 / o1 + 1 / ox), 2)
            dc_x2 = round(1 / (1 / o2 + 1 / ox), 2)
            pick_odds = {"1": o1, "X": ox, "2": o2, "1X": dc_1x, "X2": dc_x2}.get(res["Tip"], o1)
            if b2.button("💾 Save Pick to My Bet Tracker", use_container_width=True):
                save_bet(selected_comp_label, res["Match"], res["Tip"], res["Conf"], pick_odds, stake_amt)
                st.success("Saved to My Bet Tracker!")

            st.subheader("📊 Last 5 Home vs Last 5 Away Breakdown")
            col_h, col_a = st.columns(2)
            with col_h:
                h5 = raw["h_last5"]
                st.markdown(f"**🏠 {home_team} (Last 5 Home)** — Form: `{h5['form']}`")
                st.write(f"Goals Scored/Conceded: **{h5['gf']}** / **{h5['ga']}** | Corners: **{h5['corners']}** | Shots OT: **{h5['shots_ot']}**")
                st.write(f"Over 1.5: **{h5['o15']}%** | Over 2.5: **{h5['o25']}%** | Over 3.5: **{h5['o35']}%** | BTTS: **{h5['btts']}%**")
            with col_a:
                a5 = raw["a_last5"]
                st.markdown(f"**✈️ {away_team} (Last 5 Away)** — Form: `{a5['form']}`")
                st.write(f"Goals Scored/Conceded: **{a5['gf']}** / **{a5['ga']}** | Corners: **{a5['corners']}** | Shots OT: **{a5['shots_ot']}**")
                st.write(f"Over 1.5: **{a5['o15']}%** | Over 2.5: **{a5['o25']}%** | Over 3.5: **{a5['o35']}%** | BTTS: **{a5['btts']}%**")

            ev_df = pd.DataFrame({
                "Outcome": ["Home (1)", "Draw (X)", "Away (2)"],
                "Model Prob": [f"{raw['p_1']*100:.1f}%", f"{raw['p_x']*100:.1f}%", f"{raw['p_2']*100:.1f}%"],
                "Fair Odds": [
                    round(1 / max(raw["p_1"], 0.01), 2),
                    round(1 / max(raw["p_x"], 0.01), 2),
                    round(1 / max(raw["p_2"], 0.01), 2),
                ],
                "Your Odds": [o1, ox, o2],
                "Value (EV)": [
                    f"{raw['ev']['1']*100:+.1f}%",
                    f"{raw['ev']['X']*100:+.1f}%",
                    f"{raw['ev']['2']*100:+.1f}%",
                ],
            })
            st.dataframe(ev_df, hide_index=True, use_container_width=True)

            if not current_h2h.empty:
                st.markdown("**🤝 Head-to-Head (Recent Meetings)**")
                st.dataframe(current_h2h, hide_index=True, use_container_width=True)

with tab_ai:
    st.subheader("🤖 AI Betting Advisor Space")
    if current_res is None:
        st.info("Pick a competition and two different teams in **Match Analyzer** first, then come here to ask the AI.")
    else:
        st.success(f"**Active Match:** {current_res['Match']} ({selected_comp_label}) | **Odds:** 1=`{current_res['1']}` X=`{current_res['X']}` 2=`{current_res['2']}`")
        match_ctx = build_match_context(current_res, current_h2h, selected_comp_label)

        st.markdown("**Quick Questions:**")
        q_cols = st.columns(4)
        quick_q = None
        if q_cols[0].button("🎯 Best Overall Pick", use_container_width=True):
            quick_q = "Select the single best betting option for this match and explain why."
        if q_cols[1].button("🔒 Safest for Accumulator", use_container_width=True):
            quick_q = "What is the safest, lowest-risk option for an accumulator ticket?"
        if q_cols[2].button("💎 Best Value (+EV)", use_container_width=True):
            quick_q = "Which option gives the best value against the bookmaker odds I entered?"
        if q_cols[3].button("⚽ Goals / BTTS Verdict", use_container_width=True):
            quick_q = "Should I bet Over/Under goals or BTTS (GG/NG) here? Pick the best goal market."

        with st.form("ai_chat_form", clear_on_submit=True):
            typed_q = st.text_input("Or ask your own question:", placeholder="e.g. Is Home Win risky? Should I play 1X + Over 1.5 instead?")
            submitted = st.form_submit_button("Ask AI 🚀")

        user_prompt = quick_q if quick_q else (typed_q.strip() if submitted and typed_q.strip() else None)

        if user_prompt:
            st.session_state.ai_messages.append({"role": "user", "content": user_prompt})
            with st.spinner("Analyzing match data..."):
                if ai_provider == "Built-in Smart Advisor (No Key)" or not ai_api_key.strip():
                    reply = builtin_smart_advisor(current_res, user_prompt)
                else:
                    reply = ask_live_ai(ai_provider, ai_api_key, match_ctx, st.session_state.ai_messages[:-1], user_prompt)
            st.session_state.ai_messages.append({"role": "assistant", "content": reply})

        for msg in reversed(st.session_state.ai_messages):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if st.session_state.ai_messages and st.button("🧹 Clear AI Chat"):
            st.session_state.ai_messages = []
            st.rerun()

with tab_daily:
    st.subheader("🔥 Today's Curated Tips")
    if not st.session_state.daily_list:
        st.info("Analyze matches and click **'Add to Today's Tips List'** to build today's card.")
    else:
        df_daily = pd.DataFrame(st.session_state.daily_list)
        st.dataframe(df_daily, hide_index=True, use_container_width=True)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("### 🔒 Bankers")
            st.dataframe(df_daily[df_daily["Category"].str.contains("Banker")][["Match", "Tip", "Conf"]], hide_index=True)
        with c2:
            st.markdown("### 💎 Value Bets (+EV)")
            st.dataframe(df_daily[df_daily["Category"].str.contains("Value")][["Match", "Category", "Score"]], hide_index=True)
        with c3:
            st.markdown("### ⚖️ Draws of the Day")
            st.dataframe(df_daily[df_daily["Category"].str.contains("Draw")][["Match", "X", "Score"]], hide_index=True)
        if st.button("🗑️ Clear Today's List"):
            st.session_state.daily_list = []
            st.rerun()

with tab_tracker:
    st.subheader("📒 My Bet History & ROI")
    bets_df = load_bets()
    if bets_df.empty:
        st.info("No saved picks yet.")
    else:
        settled = bets_df[bets_df["status"].isin(["Won", "Lost"])]
        total_staked = settled["stake"].sum() if not settled.empty else 0.0
        total_profit = settled["profit"].sum() if not settled.empty else 0.0
        win_rate = (len(settled[settled["status"] == "Won"]) / len(settled) * 100) if not settled.empty else 0.0
        roi = (total_profit / total_staked * 100) if total_staked > 0 else 0.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Saved Picks", len(bets_df))
        k2.metric("Win Rate", f"{win_rate:.1f}%")
        k3.metric("Net Profit/Loss", f"{total_profit:+,.2f}")
        k4.metric("ROI", f"{roi:+.1f}%")

        st.divider()
        for _, row in bets_df.iterrows():
            cols = st.columns([3, 1.5, 1, 1, 1.2, 1.2])
            cols[0].write(f"**{row['match_name']}** ({row['date']})")
            cols[1].write(f"Tip: `{row['tip']}` ({row['confidence']}/10) @ **{row['odds']}**")
            cols[2].write(f"Stake: {row['stake']:.0f}")
            cols[3].write(f"**{row['status']}** ({row['profit']:+.0f})")
            if row["status"] == "Pending":
                if cols[4].button("✅ Won", key=f"won_{row['id']}"):
                    update_bet_status(row["id"], "Won")
                    st.rerun()
                if cols[5].button("❌ Lost", key=f"lost_{row['id']}"):
                    update_bet_status(row["id"], "Lost")
                    st.rerun()
