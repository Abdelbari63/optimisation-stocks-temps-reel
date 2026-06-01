"""
app.py — Dashboard Streamlit temps réel (corrigé)
- Fix axe X graphique de tendance (timestamps lisibles)
- Interroge Apache Pinot directement + API REST pour les alertes

Usage :
    streamlit run app.py
"""
import time
from datetime import datetime

import requests
import streamlit as st
import plotly.express as px
import pandas as pd
import pinotdb

PINOT_HOST = "localhost"
PINOT_PORT = 8099
API_BASE   = "http://localhost:8000"

st.set_page_config(
    page_title="Stock BI — Temps réel",
    page_icon="📦",
    layout="wide",
)

# ── Sidebar ───────────────────────────────────────────────────
st.sidebar.title("⚙️ Paramètres")
store   = st.sidebar.selectbox("Magasin", ["S01", "S02", "S03"])
window  = st.sidebar.slider("Fenêtre d'analyse (min)", 10, 120, 60, step=10)
refresh = st.sidebar.slider("Rafraîchissement (s)", 3, 30, 5)
st.sidebar.markdown("---")
st.sidebar.caption(f"Dernière MAJ : {datetime.now().strftime('%H:%M:%S')}")

st.title("📦 Optimisation des stocks — Temps réel")
st.caption(f"Magasin **{store}** · Fenêtre **{window} min** · Pinot + Kafka")

ph_kpi    = st.empty()
ph_charts = st.empty()
ph_alerts = st.empty()
ph_table  = st.empty()


def query_pinot(sql: str):
    try:
        conn = pinotdb.connect(host=PINOT_HOST, port=PINOT_PORT)
        cur  = conn.cursor()
        cur.execute(sql)
        return cur.fetchall()
    except Exception as e:
        st.warning(f"Pinot: {e}")
        return []


def fetch_recommendations(store_id: str, win: int):
    try:
        r = requests.get(
            f"{API_BASE}/recommendations/{store_id}",
            params={"window_min": win},
            timeout=5,
        )
        if r.ok:
            return r.json().get("data", [])
    except Exception:
        pass
    return []


while True:
    window_ms = window * 60 * 1000

    # ── KPIs ────────────────────────────────────────────────
    rows_kpi = query_pinot(f"""
        SELECT COUNT(*) AS nb_tx,
               SUM(qty)   AS total_qty,
               SUM(price) AS total_rev
        FROM   ventes
        WHERE  store_id = '{store}'
          AND  ts       > (NOW() - {window_ms})
    """)
    nb_tx, total_qty, total_rev = rows_kpi[0] if rows_kpi else (0, 0, 0.0)

    with ph_kpi.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Transactions",    int(nb_tx))
        c2.metric("Unités vendues",  int(total_qty))
        c3.metric("CA (fenêtre)",    f"{float(total_rev):,.2f} €")
        c4.metric("Heure",           datetime.now().strftime("%H:%M:%S"))

    # ── Graphiques ──────────────────────────────────────────
    rows_prod = query_pinot(f"""
        SELECT product_id, SUM(qty) AS sold
        FROM   ventes
        WHERE  store_id = '{store}'
          AND  ts       > (NOW() - {window_ms})
        GROUP  BY product_id
        ORDER  BY sold DESC
    """)

    # ── FIX axe X : convertir timestamp milliseconds → datetime lisible ──
    rows_time = query_pinot(f"""
        SELECT
          DATETIMECONVERT(
            ts,
            '1:MILLISECONDS:EPOCH',
            '1:MILLISECONDS:EPOCH',
            '5:MINUTES'
          ) AS t5m,
          SUM(qty) AS sold
        FROM   ventes
        WHERE  store_id = '{store}'
          AND  ts       > (NOW() - {window_ms})
        GROUP  BY t5m
        ORDER  BY t5m ASC
    """)

    with ph_charts.container():
        col_bar, col_line = st.columns(2)

        with col_bar:
            if rows_prod:
                df_bar = pd.DataFrame(rows_prod, columns=["Produit", "Ventes"])
                fig = px.bar(
                    df_bar, x="Produit", y="Ventes",
                    color="Ventes", color_continuous_scale="Teal",
                    title=f"Ventes par produit — {window} min",
                )
                fig.update_layout(margin=dict(t=40, b=0), height=300)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("En attente de données Pinot...")

        with col_line:
            if rows_time:
                # ✅ FIX : convertir ms → datetime Python lisible
                df_line = pd.DataFrame(rows_time, columns=["ts_ms", "Ventes"])
                df_line["Heure"] = pd.to_datetime(
                    df_line["ts_ms"], unit="ms"
                ).dt.strftime("%H:%M")

                fig2 = px.line(
                    df_line, x="Heure", y="Ventes",
                    title="Tendance des ventes (tranches 5 min)",
                    markers=True,
                )
                fig2.update_layout(
                    margin=dict(t=40, b=0),
                    height=300,
                    xaxis_title="Heure",
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("En attente de données temporelles...")

    # ── Alertes ─────────────────────────────────────────────
    recos = fetch_recommendations(store, window)

    with ph_alerts.container():
        alerts = [r for r in recos if r.get("reorder_needed")]
        if alerts:
            st.error(f"🚨 {len(alerts)} produit(s) nécessitent un réapprovisionnement urgent")
            for a in alerts:
                icon = "🔴" if a.get("urgency") == "HIGH" else "🟡"
                st.warning(
                    f"{icon} **{a['product_id']}** — "
                    f"stock : **{a['current_stock']}** unités · "
                    f"autonomie : **{a['hours_remaining']} h** · "
                    f"rythme : {a['rate_per_hour']} u/h"
                )
        else:
            st.success("✅ Tous les stocks sont suffisants")

    with ph_table.container():
        if recos:
            st.subheader("Détail des stocks")
            st.dataframe(
                recos,
                column_config={
                    "product_id":      "Produit",
                    "current_stock":   "Stock actuel",
                    "sold_in_window":  "Vendus (fenêtre)",
                    "rate_per_hour":   "Rythme (u/h)",
                    "hours_remaining": "Autonomie (h)",
                    "revenue_window":  "CA (€)",
                    "urgency":         "Urgence",
                    "reorder_needed":  "Alerte",
                },
                use_container_width=True,
                hide_index=True,
            )

    time.sleep(refresh)
