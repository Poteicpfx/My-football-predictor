import sqlite3
from datetime import datetime
import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson

st.set_page_config(page_title="My Football Edge", page_icon="⚽", layout="wide")

LEAGUES = {
    "Premier League (England)": "E0",
    "Championship (England)": "E1",
    "La Liga (Spain)": "SP1",
    "Bundesliga (Germany)": "D1",
    "Serie A (Italy)": "I1",
    "Ligue 1 (France)": "F1",
}

# --- 1. DATABASE FOR PERSONAL BET TRACKING ---
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

# --- 2. LIVE HISTORICAL DATA LOADER (2025/26 + 2026/27) ---
@st.cache_data(ttl=3600)
def load_league_data(code):
    frames = []
    for season in ["2526", "2627"]:
        url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
        try:
            df = pd.read_csv(url, encoding="latin1")
            df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
            df["Season"] = season
            frames.append(df)
        except Exception:
            pass

    if not frames:
        return pd.DataFrame()

    full = pd.concat(frames, ignore_index=True)
    full["FTHG"] = full["FTHG"].astype(int)
    full["FTAG"] = full["FTAG"].astype(int)
    full["DateParsed"] = pd.to_datetime(full["Date"], dayfirst=True, errors="coerce")
    full = full.sort_values("DateParsed").reset_index(drop=True)
    return full

# --- 3. STATS, POWER RANK & H2H ---
def get_team_metrics(df, team, venue="all", last_n=5):
    if venue == "home":
        games = df[df["HomeTeam"] == team].tail(last_n)
    elif venue == "away":
        games = df[df["AwayTeam"] == team].tail(last_n)
    else:
        games = df[(df["HomeTeam"] == team) | (df["AwayTeam"] == team)].tail(last_n)

    if games.empty:
        return {"form": "-", "gf": 1.2, "ga": 1.2, "o15": 60, "o25": 45, "o35": 20, "btts": 50, "corners": 0.0, "shots_ot": 0.0, "power": 50.0}

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
            form_list.append("W"); pts += 3
        elif gf == ga:
            form_list.append("D"); pts += 1
        else:
            form_list.append("L")

        if tot > 1: o15 += 1
        if tot > 2: o25 += 1
        if tot > 3: o35 += 1
        if gf > 0 and ga > 0: btts += 1
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

# --- 4. POISSON PREDICTION ENGINE ---
def analyze_fixture(df, home, away, odds_1, odds_x, odds_2):
    # Blend season-wide strength + recent venue form
    h_all = get_team_metrics(df, home, "all", last_n=15)
    a_all = get_team_metrics(df, away, "all", last_n=15)
    h_last5 = get_team_metrics(df, home, "home", last_n=5)
    a_last5 = get_team_metrics(df, away, "away", last_n=5)

    avg_hg = df["FTHG"].mean()
    avg_ag = df["FTAG"].mean()

    h_att = (h_last5["gf"] * 0.65 + h_all["gf"] * 0.35) / max(avg_hg, 0.5)
    a_def = (a_last5["ga"] * 0.65 + a_all["ga"] * 0.35) / max(avg_hg, 0.5)
    a_att = (a_last5["gf"] * 0.65 + a_all["gf"] * 0.35) / max(avg_ag, 0.5)
    h_def = (h_last5["ga"] * 0.65 + h_all["ga"] * 0.35) / max(avg_ag, 0.5)

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

    # Expected Value (+EV) against your bookmaker odds
    ev_1, ev_x, ev_2 = (p_1 * odds_1) - 1, (p_x * odds_x) - 1, (p_2 * odds_2) - 1
    ev_map = {"1": ev_1, "X": ev_x, "2": ev_2}
    best_ev_side = max(ev_map, key=ev_map.get)
    best_ev = ev_map[best_ev_side]

    # Categories
    tags = []
    pick_odds = {"1": odds_1, "X": odds_x, "2": odds_2}.get(best_pick, 1.45)
    if confidence >= 8 and pick_odds <= 1.65:
        tags.append("🔒 Banker")
    if best_ev >= 0.05:
        tags.append(f"💎 Value ({best_ev_side}: +{best_ev*100:.0f}% EV)")
    if p_x >= 0.29 and abs(h_last5["power"] - a_last5["power"]) <= 12:
        tags.append("⚖️ Draw Watch")

    return {
        "Match": f"{home} vs {away}",
        "Tip": display_pick,
        "Conf": confidence,
        "1": odds_1, "X": odds_x, "2": odds_2,
        "O/U 2.5": f"{'Over' if p_o25 >= 0.52 else 'Under'} ({p_o25*100:.0f}%)",
        "BTTS": f"{p_btts*100:.0f}%",
        "Score": score_tip,
        "Category": " | ".join(tags) if tags else "Standard",
        "_raw": {
            "home": home, "away": away, "exp_hg": exp_hg, "exp_ag": exp_ag,
            "p_1": p_1, "p_x": p_x, "p_2": p_2,
            "p_o15": p_o15, "p_o25": p_o25, "p_o35": p_o35, "p_btts": p_btts,
            "ev": ev_map, "h_last5": h_last5, "a_last5": a_last5, "matrix": matrix
        }
    }

# --- 5. SESSION SLIP FOR DAILY MATCHES ---
if "daily_list" not in st.session_state:
    st.session_state.daily_list = []

# --- 6. APP UI ---
st.title("⚽ My Personal Football Predictor")

tab_analyze, tab_daily, tab_tracker = st.tabs(["🔍 Match Analyzer", "🔥 Daily Tips & Categories", "📒 My Bet Tracker"])

with tab_analyze:
    league_name = st.selectbox("Select League", list(LEAGUES.keys()))
    league_code = LEAGUES[league_name]
    df_league = load_league_data(league_code)

    if df_league.empty:
        st.error("Could not fetch league data right now. Check your internet connection.")
    else:
        teams = sorted(df_league["HomeTeam"].unique())
        c1, c2 = st.columns(2)
        home_team = c1.selectbox("Home Team", teams, index=0)
        away_team = c2.selectbox("Away Team", teams, index=min(1, len(teams)-1))

        st.markdown("**Enter Your Bookmaker Odds (for +EV Value & Banker Check):**")
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

            # Top Summary Banner (SoccerVital Style)
            st.divider()
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Confidence", f"{res['Conf']}/10", res["Tip"])
            m2.metric("O/U 2.5 Goals", res["O/U 2.5"])
            m3.metric("BTTS (GG)", res["BTTS"])
            m4.metric("Score Tip", res["Score"])
            m5.metric("Power Rank (H / A)", f"{raw['h_last5']['power']} / {raw['a_last5']['power']}")

            st.info(f"**Classification:** {res['Category']}  |  **Expected Goals:** {home_team} `{raw['exp_hg']:.2f}` — `{raw['exp_ag']:.2f}` {away_team}")

            # Action Buttons
            b1, b2 = st.columns(2)
            if b1.button("➕ Add to Today's Tips List", use_container_width=True):
                res_copy = {k: v for k, v in res.items() if k != "_raw"}
                res_copy["League"] = league_name
                st.session_state.daily_list.append(res_copy)
                st.success("Added to Daily Tips tab!")

            pick_odds_for_save = {"1": o1, "X": ox, "2": o2, "1X": round(1/(1/o1 + 1/ox), 2), "X2": round(1/(1/o2 + 1/ox), 2)}.get(res["Tip"], o1)
            if b2.button("💾 Save Pick to My Bet Tracker", use_container_width=True):
                save_bet(league_name, res["Match"], res["Tip"], res["Conf"], pick_odds_for_save, stake_amt)
                st.success("Saved to My Bet Tracker!")

            # Deep Stats Breakdown
            st.subheader("📊 Match Breakdown (Last 5 Home vs Last 5 Away)")
            col_h, col_a = st.columns(2)
            with col_h:
                h5 = raw["h_last5"]
                st.markdown(f"**🏠 {home_team} (Last 5 Home)** — Form: `{h5['form']}`")
                st.write(f"Goals Scored/Conceded: **{h5['gf']}** / **{h5['ga']}** | Corners Avg: **{h5['corners']}** | Shots OT: **{h5['shots_ot']}**")
                st.write(f"Trends: Over 1.5: **{h5['o15']}%** | Over 2.5: **{h5['o25']}%** | Over 3.5: **{h5['o35']}%** | BTTS: **{h5['btts']}%**")
            with col_a:
                a5 = raw["a_last5"]
                st.markdown(f"**✈️ {away_team} (Last 5 Away)** — Form: `{a5['form']}`")
                st.write(f"Goals Scored/Conceded: **{a5['gf']}** / **{a5['ga']}** | Corners Avg: **{a5['corners']}** | Shots OT: **{a5['shots_ot']}**")
                st.write(f"Trends: Over 1.5: **{a5['o15']}%** | Over 2.5: **{a5['o25']}%** | Over 3.5: **{a5['o35']}%** | BTTS: **{a5['btts']}%**")

            st.markdown("**Model Probabilities & Bookmaker Value (+EV)**")
            ev_df = pd.DataFrame({
                "Outcome": ["Home (1)", "Draw (X)", "Away (2)"],
                "Model Prob": [f"{raw['p_1']*100:.1f}%", f"{raw['p_x']*100:.1f}%", f"{raw['p_2']*100:.1f}%"],
                "Fair Odds": [round(1/max(raw["p_1"], 0.01), 2), round(1/max(raw["p_x"], 0.01), 2), round(1/max(raw["p_2"], 0.01), 2)],
                "Your Odds": [o1, ox, o2],
                "Value (EV)": [f"{raw['ev']['1']*100:+.1f}%", f"{raw['ev']['X']*100:+.1f}%", f"{raw['ev']['2']*100:+.1f}%"],
            })
            st.dataframe(ev_df, hide_index=True, use_container_width=True)

            h2h_df = get_h2h(df_league, home_team, away_team)
            if not h2h_df.empty:
                st.markdown("**🤝 Head-to-Head (Recent Meetings)**")
                st.dataframe(h2h_df, hide_index=True, use_container_width=True)

with tab_daily:
    st.subheader("🔥 Today's Curated Tips")
    if not st.session_state.daily_list:
        st.info("Use the **Match Analyzer** tab and click **'Add to Today's Tips List'** to build today's card.")
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
        st.info("No saved picks yet. Save picks from the Match Analyzer to track your real performance.")
    else:
        settled = bets_df[bets_df["status"].isin(["Won", "Lost"])]
        total_staked = settled["stake"].sum() if not settled.empty else 0.0
        total_profit = settled["profit"].sum() if not settled.empty else 0.0
        win_rate = (len(settled[settled["status"] == "Won"]) / len(settled) * 100) if not settled.empty else 0.0
        roi = (total_profit / total_staked * 100) if total_staked > 0 else 0.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Saved Picks", len(bets_df))
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
