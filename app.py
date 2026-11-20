import streamlit as st
import pandas as pd
from datetime import datetime
import predictor as pr
import sporty_helper as sh
import pages_extra as pe

st.set_page_config(page_title="PitchIQ · Football Analytics", page_icon="⚽", layout="wide", initial_sidebar_state="collapsed")
st.markdown(sh.PRO_CSS, unsafe_allow_html=True)

pr.init_db()
prefs = pr.load_state("prefs", {})
if "daily_list" not in st.session_state: st.session_state.daily_list = pr.load_state("daily_list", [])
if "ai_messages" not in st.session_state: st.session_state.ai_messages = pr.load_state("ai_messages", [])
if "cmd_result" not in st.session_state: st.session_state.cmd_result = ""
if "cmd_games" not in st.session_state: st.session_state.cmd_games = []
if "active_match" not in st.session_state: st.session_state.active_match = pr.load_state("active_match", None)
if "nav_page" not in st.session_state: st.session_state.nav_page = "Dashboard"

# Load keys from Secrets or saved Settings
gkey = pr.get_secret("GOAL_API_KEY") or prefs.get("gkey", "")
okey = pr.get_secret("ODDS_API_KEY") or prefs.get("okey", "")
ai_prov = prefs.get("ai_prov", "Built-in Smart Advisor (No Key)")
ai_key = (pr.get_secret("GROQ_API_KEY") if ai_prov == "Groq (Free AI)" else (pr.get_secret("GEMINI_API_KEY") if ai_prov == "Google Gemini (Free AI)" else "")) or prefs.get("ai_key", "")
odds_events, odds_dict, odds_err = pr.load_the_odds_api(okey)

# Header & Clean 6-Page Navigation
st.markdown('<div class="nav-header"><div><div class="brand-title">PitchIQ Analytics</div><div class="brand-sub">Global Football Probability & Match Intelligence · WAT (UTC+1)</div></div><span class="tag-green">PRO</span></div>', unsafe_allow_html=True)
PAGES = ["Dashboard", "Fixtures", "Predictions", "Leagues", "Analysis", "Settings"]
picked_nav = st.radio("Navigation", PAGES, index=PAGES.index(st.session_state.nav_page) if st.session_state.nav_page in PAGES else 0, horizontal=True, label_visibility="collapsed")
if picked_nav != st.session_state.nav_page:
    st.session_state.nav_page = picked_nav
    st.rerun()
st.divider()

page = st.session_state.nav_page

if page == "Dashboard":
    bdf = pr.load_bets()
    settled = bdf[bdf["status"].isin(["Won", "Lost"])] if not bdf.empty else pd.DataFrame()
    wr = (len(settled[settled["status"] == "Won"]) / len(settled) * 100) if not settled.empty else 0.0
    today_espn, _ = pr.load_espn_by_date(datetime.now().strftime("%Y%m%d"))

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Today's Major Fixtures", len(today_espn))
    k2.metric("Active Slip Legs", len(st.session_state.daily_list))
    k3.metric("Tracked Picks", len(bdf))
    k4.metric("Model Win Rate", f"{wr:.1f}%")

    q1, q2, q3 = st.columns(3)
    if q1.button("Browse Today's Fixtures", use_container_width=True): st.session_state.nav_page = "Fixtures"; st.rerun()
    if q2.button("Run AI Predictions", use_container_width=True): st.session_state.nav_page = "Predictions"; st.rerun()
    if q3.button("Inspect a League", use_container_width=True): st.session_state.nav_page = "Leagues"; st.rerun()

    if st.session_state.cmd_result:
        st.markdown(f'<div class="pro-card"><div class="pro-meta"><span>LATEST AI REPORT</span></div>{st.session_state.cmd_result}</div>', unsafe_allow_html=True)
    if st.session_state.cmd_games:
        st.subheader("Top Ranked Fixtures")
        st.markdown(sh.render_prediction_cards(st.session_state.cmd_games[:4]), unsafe_allow_html=True)
    elif today_espn:
        st.subheader("Featured Today")
        for g in today_espn[:5]:
            if (not g["1"]) and odds_dict:
                fd = pr.find_odds(g["Home"], g["Away"], odds_dict)
                if fd: g["1"], g["X"], g["2"], g["Bookie"] = fd
        st.markdown(sh.render_fixture_cards(today_espn[:5]), unsafe_allow_html=True)

elif page == "Fixtures":
    st.subheader("Fixtures")
    f1, f2, f3 = st.columns([1.1, 1.5, 1.4])
    fdate = f1.date_input("Date", value=datetime.now().date())
    ffeed = f2.selectbox("Source", ["Major Fixtures (ESPN Free)", "All 1,000+ Leagues (GOAL API)", "Live Bookmaker Odds (The Odds API)"])
    fsearch = f3.text_input("Search Team", placeholder="e.g. Arsenal, Madrid...")

    fgames, ferr = [], ""
    if ffeed.startswith("Major"): fgames, ferr = pr.load_espn_by_date(fdate.strftime("%Y%m%d"))
    elif ffeed.startswith("All"):
        if not gkey: st.warning("Add your GOAL API key in **Settings** to load all 1,000+ leagues.")
        else: fgames, ferr = pr.load_goal_by_date(fdate.strftime("%Y-%m-%d"), gkey)
    else:
        if not okey: st.warning("Add your The Odds API key in **Settings**.")
        else: fgames = [e for e in odds_events if e["DateTime"].startswith(fdate.strftime("%Y-%m-%d"))] or odds_events

    if ferr: st.warning(ferr)
    if odds_err: st.warning(odds_err)
    for g in fgames:
        if (not g.get("1")) and odds_dict:
            fd = pr.find_odds(g["Home"], g["Away"], odds_dict)
            if fd: g["1"], g["X"], g["2"], g["Bookie"] = fd

    lgs_avail = sorted({g["League"] for g in fgames})
    fc1, fc2 = st.columns([2.2, 1])
    picked_lg = fc1.multiselect("Filter by League / Competition", lgs_avail)
    up_only = fc2.checkbox("Hide Finished", value=True)

    filtered = [g for g in fgames if (not picked_lg or g["League"] in picked_lg) and (not up_only or not g.get("IsFinished")) and (not fsearch.strip() or fsearch.lower() in f"{g['Home']} {g['Away']} {g['League']}".lower())]

    if not filtered:
        st.info("No fixtures match your current filters.")
    else:
        st.caption(f"Showing {min(len(filtered), 40)} of {len(filtered)} fixtures · Times in WAT")
        ml = [f"{g['League']} | {g['Home']} vs {g['Away']}" for g in filtered]
        ac1, ac2, ac3 = st.columns([2.2, 1, 1])
        cm = ac1.selectbox("Select Fixture", ml, label_visibility="collapsed")
        g_sel = filtered[ml.index(cm)]
        if ac2.button("Analyze Match", use_container_width=True):
            am = {"league": g_sel["League"], "home": g_sel["Home"], "away": g_sel["Away"], "o1": float(g_sel.get("1") or 1.85), "ox": float(g_sel.get("X") or 3.50), "o2": float(g_sel.get("2") or 4.20), "src": "goal" if g_sel.get("LeagueId") else "", "cid": g_sel.get("LeagueId") or ""}
            st.session_state.active_match = am; pr.save_state("active_match", am)
            st.session_state.nav_page = "Analysis"; st.rerun()
        if ac3.button("Add to Slip", use_container_width=True):
            df_mh = pr.load_goal_fixtures(g_sel["LeagueId"], gkey)[0] if (g_sel.get("LeagueId") and gkey) else pd.DataFrame()
            rd = pr.analyze_fixture(df_mh, g_sel["Home"], g_sel["Away"], float(g_sel.get("1") or 1.85), float(g_sel.get("X") or 3.50), float(g_sel.get("2") or 4.20))
            rc = {k: v for k, v in rd.items() if k != "_raw"}; rc["Competition"] = g_sel["League"]
            st.session_state.daily_list.append(rc); pr.save_state("daily_list", st.session_state.daily_list)
            st.success("Added to Predictions → Ticket Slip.")
        st.markdown(sh.render_fixture_cards(filtered[:40]), unsafe_allow_html=True)

elif page == "Predictions":
    sub = st.radio("Section", ["AI Predictions Scanner", "Ticket Slip Builder", "Bet Tracker"], horizontal=True, label_visibility="collapsed")
    if sub == "AI Predictions Scanner":
        sc_mode = st.radio("Scan Source", ["Daily 1,000+ Leagues (GOAL API)", "Top Competitions (ESPN Free)"], horizontal=True)
        if sc_mode.startswith("Daily"):
            if not gkey: st.warning("Add your GOAL API key in **Settings**.")
            else:
                dt_sc = st.date_input("Date", value=datetime.now().date(), key="pr_dt")
                raw_d, derr = pr.load_goal_by_date(dt_sc.strftime("%Y-%m-%d"), gkey)
                if derr: st.warning(derr)
                av_up = [g for g in raw_d if not g.get("IsFinished")]
                av_lgs = sorted({g["League"] for g in av_up})
                st.caption(f"{len(av_up)} upcoming matches across {len(av_lgs)} competitions")
                pk_lgs = st.multiselect("Filter Competitions (leave blank to auto-scan top 20)", av_lgs, key="pr_dlgs")
                b1, b2, b3 = st.columns(3); qcmd = None
                if b1.button("Top 5 Picks", use_container_width=True): qcmd = "Select the 5 highest-probability matches and best market for each."
                if b2.button("4-Leg Safe Acca", use_container_width=True): qcmd = "Build a 4-leg conservative accumulator using Double Chance or Over 1.5."
                if b3.button("Goals & BTTS", use_container_width=True): qcmd = "Select the best Over 1.5, Over 2.5, or BTTS picks."
                with st.form("pr_cmd_form"):
                    tcmd = st.text_input("Custom Request", placeholder="e.g. Select 4 safest picks from today's schedule")
                    sub_b = st.form_submit_button("Analyze & Predict")
                ctxt = qcmd if qcmd else (tcmd.strip() if sub_b and tcmd.strip() else None)
                if ctxt:
                    with st.spinner("Analyzing team metrics..."):
                        gms, gerr = pr.scan_goal_date_games(dt_sc.strftime("%Y-%m-%d"), gkey, odds_dict, pk_lgs or None, True, 20)
                        if gerr: st.error(gerr)
                        st.session_state.cmd_games = gms
                        st.session_state.cmd_result = pr.command_ai_multi(ai_prov, ai_key, gms, ctxt)
        else:
            pk_espn = st.multiselect("Select Competitions", list(pr.SCAN_LEAGUES.keys()), default=["🇬🇧 Premier League", "🇪🇸 La Liga", "🏆 UEFA Champions League", "🟠 UEFA Europa League"])
            b1, b2, b3 = st.columns(3); qcmd = None
            if b1.button("Top 3 Picks", use_container_width=True, key="ep1"): qcmd = "Select the 3 strongest picks across these competitions."
            if b2.button("4-Leg Safe Acca", use_container_width=True, key="ep2"): qcmd = "Build a 4-leg conservative accumulator."
            if b3.button("Value Picks", use_container_width=True, key="ep3"): qcmd = "Identify the best value picks."
            with st.form("ep_cmd_form"):
                tcmd = st.text_input("Custom Request", placeholder="e.g. Pick 3 safest games")
                sub_b = st.form_submit_button("Analyze Competitions")
            ctxt = qcmd if qcmd else (tcmd.strip() if sub_b and tcmd.strip() else None)
            if ctxt and pk_espn:
                with st.spinner("Scanning competitions..."):
                    gms = pr.scan_selected_leagues(pk_espn, odds_dict)
                    st.session_state.cmd_games = gms
                    st.session_state.cmd_result = pr.command_ai_multi(ai_prov, ai_key, gms, ctxt)

        if st.session_state.cmd_result:
            st.markdown(f'<div class="pro-card">{st.session_state.cmd_result}</div>', unsafe_allow_html=True)
        if st.session_state.cmd_games:
            s1, s2 = st.columns([1, 2])
            ln = s1.number_input("Slip Legs", min_value=2, max_value=8, value=4)
            if s2.button("Send Top Picks to Ticket Slip", use_container_width=True):
                st.session_state.daily_list = st.session_state.cmd_games[:int(ln)]
                pr.save_state("daily_list", st.session_state.daily_list)
                st.success(f"Sent {int(ln)} picks to Ticket Slip Builder.")
            st.markdown(sh.render_prediction_cards(st.session_state.cmd_games[:25]), unsafe_allow_html=True)

    elif sub == "Ticket Slip Builder":
        if not st.session_state.daily_list:
            st.info("No picks in your slip yet. Add matches from **Fixtures**, **Leagues**, or **AI Predictions Scanner**.")
        else:
            s1, s2, s3 = st.columns([2, 1, 1])
            tst = s1.selectbox("Strategy", ["Safest Acca (DC / Over 1.5)", "Best Tip (1X2 / DC)", "Combo Boost", "Goals & GG"])
            mxl = s2.number_input("Max Legs", min_value=1, max_value=10, value=min(5, len(st.session_state.daily_list)))
            stk = s3.number_input("Stake (₦)", min_value=50.0, value=float(prefs.get("stake", 1000.0)), step=100.0)
            legs, toto, estw, cprob, stxt = sh.build_sporty_ticket(st.session_state.daily_list, tst, int(mxl), float(stk))
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Legs", len(legs)); m2.metric("Combined Hit %", f"{cprob}%"); m3.metric("Est. Odds", toto); m4.metric("Est. Return", f"₦{estw:,.0f}")
            st.markdown(sh.render_sporty_cards(legs), unsafe_allow_html=True)
            st.code(stxt, language=None)
            c1, c2 = st.columns(2)
            c1.link_button("Open SportyBet NG", "https://www.sportybet.com/ng/", use_container_width=True)
            if c2.button("Clear Slip", use_container_width=True):
                st.session_state.daily_list = []; pr.save_state("daily_list", []); st.rerun()

    else:
        bdf = pr.load_bets()
        if bdf.empty: st.info("No tracked picks yet.")
        else:
            st_df = bdf[bdf["status"].isin(["Won", "Lost"])]
            stk = st_df["stake"].sum() if not st_df.empty else 0.0
            prf = st_df["profit"].sum() if not st_df.empty else 0.0
            wr = (len(st_df[st_df["status"] == "Won"]) / len(st_df) * 100) if not st_df.empty else 0.0
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Picks", len(bdf)); k2.metric("Win Rate", f"{wr:.1f}%"); k3.metric("Net P/L", f"₦{prf:+,.0f}"); k4.metric("ROI", f"{(prf/stk*100 if stk>0 else 0.0):+.1f}%")
            st.divider()
            for _, row in bdf.iterrows():
                cols = st.columns([3, 1.5, 1, 1, 1, 1])
                cols[0].write(f"**{row['match_name']}** · {row['date']}")
                cols[1].write(f"`{row['tip']}` ({row['confidence']}/10) @ {row['odds']}")
                cols[2].write(f"₦{row['stake']:.0f}"); cols[3].write(f"**{row['status']}**")
                if row["status"] == "Pending":
                    if cols[4].button("Won", key=f"w_{row['id']}"): pr.update_bet(row["id"], "Won"); st.rerun()
                    if cols[5].button("Lost", key=f"l_{row['id']}"): pr.update_bet(row["id"], "Lost"); st.rerun()

elif page == "Leagues":
    pe.render_leagues_page(prefs, gkey, odds_dict)

elif page == "Analysis":
    pe.render_analysis_page(prefs, gkey, odds_dict, ai_prov, ai_key)

elif page == "Settings":
    pe.render_settings_page(prefs)
