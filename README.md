# Optimisation des stocks en temps réel — Apache Pinot + Kafka + Debezium

## Architecture

```
PostgreSQL (stock) ──► Debezium CDC ──► Kafka ◄── POS simulé (ventes)
                                          │
                                    Apache Pinot (in-memory OLAP)
                                          │
                                    API REST (FastAPI + Redis cache)
                                          │
                                    Dashboard (Streamlit)
```

## Stack technique

| Composant       | Rôle                                      |
|----------------|-------------------------------------------|
| Apache Kafka    | Bus de messages temps réel                |
| Apache Pinot    | Base OLAP in-memory, requêtes sub-secondes |
| PostgreSQL      | Source de vérité pour les niveaux de stock |
| Debezium        | CDC : capture les changements PostgreSQL   |
| Redis           | Cache des recommandations API              |
| FastAPI         | API REST de réapprovisionnement            |
| Streamlit       | Dashboard réactif temps réel              |

## Prérequis

- Docker 29+ et Docker Compose v2
- Python 3.10+

## Démarrage complet

### 1. Lancer tous les services

```bash
docker compose up -d
docker compose ps   # tous les services doivent être "healthy"
```

> Attendre ~2-3 minutes que Pinot et Debezium soient complètement démarrés.

### 2. Initialiser les schémas et tables Pinot

```bash
bash scripts/init-pinot.sh
```

### 3. Enregistrer le connecteur Debezium (CDC PostgreSQL → Kafka)

```bash
pip install requests
python scripts/register_debezium.py
```

Ce script enregistre le connecteur qui surveille la table `stock` dans PostgreSQL
et publie chaque changement dans le topic Kafka `cdc.public.stock`.

### 4. Démarrer le générateur de données (ventes simulées)

```bash
cd data-generator
pip install -r requirements.txt
python producer.py
# Options : --interval 0.2 --burst-prob 0.1
```

### 5. Lancer l'API REST

```bash
cd api
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 6. Lancer le dashboard

```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```

## URLs des services

| Service         | URL                          |
|----------------|------------------------------|
| Pinot UI        | http://localhost:9000         |
| Kafka UI        | http://localhost:8080         |
| Debezium REST   | http://localhost:8083         |
| API Swagger     | http://localhost:8000/docs    |
| Dashboard       | http://localhost:8501         |
| Redis           | localhost:6379                |
| PostgreSQL      | localhost:5432                |

## Requêtes SQL Pinot utiles

```sql
-- Ventes par produit (dernière heure)
SELECT product_id, SUM(qty) AS sold, SUM(price) AS revenue
FROM ventes
WHERE store_id = 'S01' AND ts > (NOW() - 3600000)
GROUP BY product_id ORDER BY sold DESC

-- Stock actuel par magasin
SELECT store_id, product_id, LAST(level) AS stock
FROM stock
WHERE ts > (NOW() - 120000)
GROUP BY store_id, product_id

-- Tendance ventes (tranches 5 min)
SELECT DATETIMECONVERT(ts,'1:MILLISECONDS:EPOCH','1:MILLISECONDS:EPOCH','5:MINUTES') AS t,
       SUM(qty) AS sold
FROM ventes
WHERE ts > (NOW() - 3600000)
GROUP BY t ORDER BY t
```

## Tests de performance et tolérance aux pannes

```bash
python scripts/test_tolerance.py
```

Ce script teste automatiquement :
- **Test 1** — Latence des requêtes Pinot (objectif < 200ms)
- **Test 2** — Cache Redis (gain de performance mesuré)
- **Test 3** — Tolérance aux pannes : arrêt/redémarrage de pinot-server

### Test manuel du cache Redis

```bash
# Premier appel (depuis Pinot, ~100-300ms)
curl http://localhost:8000/recommendations/S01

# Deuxième appel dans les 30s (depuis Redis, <5ms)
curl http://localhost:8000/recommendations/S01

# Inspecter le cache
redis-cli KEYS "reco:*"
redis-cli TTL "reco:S01:60"
```

## Arrêter tous les services

```bash
docker compose down
# Avec suppression des volumes :
docker compose down -v
```
