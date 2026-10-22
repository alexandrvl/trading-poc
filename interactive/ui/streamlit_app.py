from __future__ import annotations

import json
import os
import threading
import time
from queue import Empty, Queue

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import websocket

API_URL = os.getenv("TRADING_API_URL", "http://localhost:8000")

st.set_page_config(page_title="Tradic interactive PoC", layout="wide")
st.title("Tradic interactive PoC")
st.caption(
    "Generated VPP / forecast / ETRM simulation. Physics knobs live in "
    "`interactive/config/sim.yaml`. dbt and Iceberg flush run on a schedule from that file."
)


def api(method: str, path: str, **kwargs):
    url = f"{API_URL}{path}"
    try:
        response = httpx.request(method, url, timeout=180.0, **kwargs)
        response.raise_for_status()
        if response.content:
            return response.json()
        return {}
    except httpx.HTTPError as exc:
        st.error(f"{method} {path} failed: {exc}")
        return None


def _ensure_ws() -> Queue:
    if st.session_state.get("ws_started"):
        return st.session_state.ws_queue
    queue: Queue = Queue(maxsize=100)
    stop = threading.Event()
    ws_url = API_URL.replace("https://", "wss://").replace("http://", "ws://") + "/ws"

    def on_message(_ws, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if queue.full():
            try:
                queue.get_nowait()
            except Empty:
                pass
        try:
            queue.put_nowait(data)
        except Exception:
            return

    def run() -> None:
        app = websocket.WebSocketApp(ws_url, on_message=on_message)
        while not stop.is_set():
            app.run_forever(ping_interval=20, ping_timeout=10)
            if not stop.is_set():
                time.sleep(2)

    thread = threading.Thread(target=run, daemon=True, name="trading-ws")
    thread.start()
    st.session_state.ws_started = True
    st.session_state.ws_queue = queue
    st.session_state.ws_stop = stop
    st.session_state.ws_thread = thread
    st.session_state.afrr_events = []
    return queue


def _drain_ws(queue: Queue) -> None:
    events = st.session_state.setdefault("afrr_events", [])
    while True:
        try:
            msg = queue.get_nowait()
        except Empty:
            break
        if msg.get("type") == "afrr":
            events.extend(msg.get("rows") or [])
            st.session_state.afrr_events = events[-40:]


ws_queue = _ensure_ws()
_drain_ws(ws_queue)

state = api("GET", "/state") or {}
assets = state.get("assets") or []
asset_ids = [a["asset_id"] for a in assets] or ["WT-EE-N-01"]

with st.sidebar:
    st.header("Clock")
    st.write(f"Sim time: **{state.get('sim_ts', '—')}**")
    st.write(f"ISP start: {state.get('isp_start', '—')}")
    st.write("Status: **running**" if state.get("running") else "Status: paused")
    cols = st.columns(2)
    if cols[0].button("Start", use_container_width=True):
        api("POST", "/sim/start")
        st.rerun()
    if cols[1].button("Pause", use_container_width=True):
        api("POST", "/sim/pause")
        st.rerun()
    speed = st.slider(
        "Speed (sim min / wall s)",
        1,
        240,
        int(state.get("speed_factor") or 60),
        key="speed",
    )
    if st.button("Apply speed"):
        api("POST", "/sim/speed", json={"speed_factor": speed})
        st.rerun()

    st.header("Dispatch")
    asset_id = st.selectbox("Asset", asset_ids, key="asset_id")
    selected = next((a for a in assets if a["asset_id"] == asset_id), {})
    available = st.toggle("Available", value=bool(selected.get("available", True)), key="available")
    if st.button("Set availability"):
        api("POST", f"/assets/{asset_id}/availability", json={"available": available})
        st.rerun()
    default_setpoint = float(selected.get("setpoint_limit_kw") or selected.get("nominal_kw") or 0)
    setpoint = st.number_input("Setpoint limit kW", min_value=0.0, value=default_setpoint, key="setpoint")
    if st.button("Apply setpoint"):
        api("POST", f"/assets/{asset_id}/setpoint", json={"setpoint_limit_kw": setpoint})
        st.rerun()
    duration = st.slider("Down-regulation minutes (sim)", 10, 45, 20, key="dr_min")
    if st.button("Send down-regulation", type="primary"):
        nominal = float(selected.get("nominal_kw") or setpoint or 1)
        limit = setpoint if setpoint < 0.5 * nominal else nominal * 0.2
        api(
            "POST",
            "/market/down-regulation",
            json={"asset_id": asset_id, "setpoint_limit_kw": limit, "duration_minutes": duration},
        )
        st.rerun()

    st.header("Bid")
    market = st.selectbox(
        "Market",
        ["NP_DA_EE", "ELERING_mFRR_DOWN", "ELERING_mFRR_UP", "ELERING_aFRR_UP", "CAPACITY_MARKET_BALTIC"],
        key="market",
    )
    volume = st.number_input("Volume MW", min_value=0.1, value=1.0, key="volume")
    price = st.number_input("Price EUR", value=80.0, key="price")
    if st.button("Place / accept bid"):
        api(
            "POST",
            "/market/bids",
            json={
                "portfolio_id": selected.get("portfolio_id") or "Wind_EE_North",
                "market_code": market,
                "price_eur": price,
                "volume_mw": volume,
                "accept": True,
            },
        )
        st.rerun()


@st.fragment(run_every=2)
def live_panel() -> None:
    _drain_ws(st.session_state.ws_queue)
    latest = api("GET", "/telemetry/latest") or {}
    samples = latest.get("samples") or []
    prices = latest.get("last_prices") or {}
    kpis = st.columns(5)
    kpis[0].metric("Sim time", str(latest.get("sim_ts") or "—")[11:19])
    kpis[1].metric("DA EUR/MWh", f"{float(prices.get('NP_DA_EE') or 0):.1f}")
    kpis[2].metric("mFRR down EUR/MWh", f"{float(prices.get('ELERING_mFRR_DOWN') or 0):.1f}")
    total_kw = sum(float(s.get("active_power_kw") or 0) for s in samples)
    kpis[3].metric("VPP kW", f"{total_kw:.0f}")
    afrr_rows = st.session_state.get("afrr_events") or latest.get("last_afrr") and [latest["last_afrr"]] or []
    last = afrr_rows[-1] if afrr_rows else latest.get("last_afrr")
    kpis[4].metric(
        "PICASSO 4s",
        (last or {}).get("wall_ts", "—")[-12:] if last else "—",
        help="Last aFRR setpoint wall time. One WebSocket per session.",
    )

    history = api("GET", "/telemetry/history?minutes=120") or []
    hist = pd.DataFrame(history)
    if hist.empty:
        st.info("Start the clock to stream generated telemetry.")
        return
    hist["event_ts"] = pd.to_datetime(hist["event_ts"])
    power = hist.groupby("event_ts", as_index=False)["active_power_kw"].sum()
    setpoint_df = hist.groupby("event_ts", as_index=False)["setpoint_limit_kw"].sum()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=power["event_ts"], y=power["active_power_kw"], name="Active power kW"))
    fig.add_trace(
        go.Scatter(x=setpoint_df["event_ts"], y=setpoint_df["setpoint_limit_kw"], name="Setpoint kW")
    )
    fig.add_trace(
        go.Scatter(
            x=power["event_ts"],
            y=[float(prices.get("NP_DA_EE") or 80)] * len(power),
            name="DA EUR/MWh",
            yaxis="y2",
            line=dict(dash="dot"),
        )
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        height=360,
        yaxis=dict(title="kW"),
        yaxis2=dict(title="EUR/MWh", overlaying="y", side="right"),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(pd.DataFrame(latest.get("assets") or assets), use_container_width=True, hide_index=True)
    if afrr_rows:
        st.caption(f"{len(afrr_rows)} aFRR setpoints on this WebSocket (period {latest.get('afrr_period_seconds', 4)} s).")
        st.dataframe(pd.DataFrame(afrr_rows[-8:]), use_container_width=True, hide_index=True)


live_panel()

events = state.get("recent_events") or []
if events:
    st.subheader("Recent sim events")
    st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)

st.header("dbt reports")
st.write(
    "After a down-regulation, wait until the 15-minute ISP closes (at speed 60 that is ~15 wall seconds), "
    "then wait for the scheduled dbt job (`dbt.run_every_minutes` in sim.yaml). "
    "Open **mart_curtailment_compensation** — lost energy should appear for the curtailed asset. "
    "Iceberg appends on `iceberg.flush_seconds` / `iceberg.flush_rows`; there is no manual flush."
)
report_names = api("GET", "/reports") or {
    "mart_curtailment_compensation": "information_mart.mart_curtailment_compensation"
}
choice = st.selectbox(
    "Report",
    list(report_names.keys()),
    index=list(report_names.keys()).index("mart_curtailment_compensation")
    if "mart_curtailment_compensation" in report_names
    else 0,
    key="report",
)
if st.button("Reload table"):
    st.rerun()

rows = api("GET", f"/reports/{choice}?limit=200")
if rows is None:
    st.warning("No report rows yet. Wait for the scheduled dbt job after the first ISP settles.")
elif not rows:
    st.info("Report is empty. Send down-regulation, wait for ISP close, then wait for scheduled dbt.")
else:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

last_dbt = state.get("last_dbt") or {}
if last_dbt.get("status") and last_dbt.get("status") != "never":
    st.caption(
        f"Last dbt: {last_dbt.get('status')} in {last_dbt.get('duration_s')}s at {last_dbt.get('started_at')}"
    )
