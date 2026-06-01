"""
main.py — API REST de réapprovisionnement
Interroge Apache Pinot et met les résultats en cache Redis.

Usage :
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
"""
import json
import time
from typing import Optional

import redis
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import pinotdb

# ── Config ────────────────────────────────────────────────────
PINOT_HOST  = "localhost"
PINOT_PORT  = 8099
REDIS_HOST  = "localhost"
REDIS_PORT  = 6379
CACHE_TTL   = 30       # secondes
ALERT_HOURS = 2.0      # seuil d'alerte (stock restant < N heures)

# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="Stock BI — API de réapprovisionnement",
    description="Recommandations temps réel basées sur Apache Pinot",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

cache = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def get_cursor():
    conn = pinotdb.connect(host=PINOT_HOST, port=PINOT_PORT)
    return conn.cursor()


# ── Endpoints ─────────────────────────────────────────────────

@app.get("/health")
def health():
    """Vérification de l'état de l'API."""
    try:
        cache.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return {"status": "ok", "redis": redis_ok}


@app.get("/recommendations/{store_id}")
def recommendations(
    store_id: str,
    window_min: int = Query(60, description="Fenêtre d'analyse en minutes"),
):
    """
    Recommandations de réapprovisionnement pour un magasin.
    Retourne les produits triés par urgence (heures de stock restantes).
    """
    cache_key = f"reco:{store_id}:{window_min}"
    cached = cache.get(cache_key)
    if cached:
        result = json.loads(cached)
        return {"source": "cache", "store_id": store_id, "data": result}

    window_ms = window_min * 60 * 1000
    t0 = time.time()

    try:
        cur = get_cursor()

        # ── Vitesse d'écoulement sur la fenêtre ──
        cur.execute(
            f"""
            SELECT product_id,
                   SUM(qty)   AS sold,
                   SUM(price) AS revenue
            FROM   ventes
            WHERE  store_id   = '{store_id}'
              AND  ts         > (NOW() - {window_ms})
            GROUP  BY product_id
            """
        )
        sales = {row[0]: {"sold": row[1], "revenue": row[2]} for row in cur.fetchall()}

        # ── Stock actuel (dernière valeur connue) ──
        cur.execute(
            f"""
            SELECT product_id,
                   LAST(level) AS current_stock
            FROM   stock
            WHERE  store_id = '{store_id}'
              AND  ts       > (NOW() - 120000)
            GROUP  BY product_id
            """
        )
        stock_rows = cur.fetchall()

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Pinot unavailable: {e}")

    # ── Calcul des recommandations ────────────────────────────
    result = []
    for product_id, current_stock in stock_rows:
        s     = sales.get(product_id, {"sold": 0, "revenue": 0})
        sold  = s["sold"]
        # Taux d'écoulement par heure
        rate_per_hour = (sold / window_min) * 60 if window_min > 0 else 0
        hours = (current_stock / rate_per_hour) if rate_per_hour > 0 else 9999

        result.append({
            "product_id":       product_id,
            "current_stock":    current_stock,
            "sold_in_window":   sold,
            "rate_per_hour":    round(rate_per_hour, 1),
            "hours_remaining":  round(min(hours, 9999), 1),
            "revenue_window":   round(s["revenue"], 2),
            "reorder_needed":   hours < ALERT_HOURS,
            "urgency":          "HIGH" if hours < 1 else "MEDIUM" if hours < ALERT_HOURS else "OK",
        })

    result.sort(key=lambda x: x["hours_remaining"])
    cache.setex(cache_key, CACHE_TTL, json.dumps(result))

    latency_ms = round((time.time() - t0) * 1000)
    return {
        "source":     "pinot",
        "store_id":   store_id,
        "latency_ms": latency_ms,
        "data":       result,
    }


@app.get("/stores")
def list_stores():
    """Liste des magasins avec données actives."""
    try:
        cur = get_cursor()
        cur.execute("SELECT DISTINCT store_id FROM ventes LIMIT 50")
        stores = [row[0] for row in cur.fetchall()]
        return {"stores": stores}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/stats/global")
def global_stats():
    """KPIs globaux — toutes les ventes de la dernière heure."""
    cache_key = "stats:global"
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    try:
        cur = get_cursor()
        cur.execute("""
            SELECT store_id,
                   COUNT(*)   AS nb_transactions,
                   SUM(qty)   AS total_qty,
                   SUM(price) AS total_revenue
            FROM   ventes
            WHERE  ts > (NOW() - 3600000)
            GROUP  BY store_id
            ORDER  BY total_revenue DESC
        """)
        rows = [
            {"store_id": r[0], "transactions": r[1],
             "qty": r[2], "revenue": round(r[3], 2)}
            for r in cur.fetchall()
        ]
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    cache.setex(cache_key, 15, json.dumps(rows))
    return rows
