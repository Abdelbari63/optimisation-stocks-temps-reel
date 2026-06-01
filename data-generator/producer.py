"""
producer.py — Générateur de données simulées
Topics Kafka : ventes (transactions POS) et stock (niveaux)

Usage :
    pip install kafka-python
    python producer.py
    python producer.py --brokers localhost:9092 --interval 0.2 --burst-prob 0.1
"""
import json
import random
import time
import argparse
from datetime import datetime
from kafka import KafkaProducer

PRODUCTS = ["P001", "P002", "P003", "P004", "P005", "P006"]
STORES   = ["S01",  "S02",  "S03"]
PRICES   = {
    "P001": 12.99, "P002": 45.50, "P003":  8.75,
    "P004": 99.99, "P005": 23.00, "P006":  5.50,
}

# État interne des stocks (simulé en mémoire)
stocks = {
    (s, p): random.randint(50, 200)
    for s in STORES for p in PRODUCTS
}


def get_producer(brokers: str) -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=brokers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",
        retries=3,
    )


def make_sale(store: str, product: str) -> dict:
    qty = random.randint(1, 5)
    stocks[(store, product)] = max(0, stocks[(store, product)] - qty)
    return {
        "ts":         int(datetime.now().timestamp() * 1000),
        "store_id":   store,
        "product_id": product,
        "qty":        qty,
        "price":      round(PRICES[product] * qty, 2),
    }


def make_stock_event(store: str, product: str) -> dict:
    return {
        "ts":         int(datetime.now().timestamp() * 1000),
        "store_id":   store,
        "product_id": product,
        "level":      stocks[(store, product)],
    }


def main():
    ap = argparse.ArgumentParser(description="Producteur Kafka — retail BI")
    ap.add_argument("--brokers",    default="localhost:9092",
                    help="Bootstrap servers Kafka")
    ap.add_argument("--interval",   type=float, default=0.5,
                    help="Secondes entre chaque cycle")
    ap.add_argument("--burst-prob", type=float, default=0.05,
                    help="Probabilité d'un burst de ventes (pic de soldes)")
    args = ap.parse_args()

    producer = get_producer(args.brokers)
    print(f"🚀 Producteur démarré — brokers: {args.brokers}")
    print(f"   Intervalle: {args.interval}s | Burst prob: {args.burst_prob}")
    count = 0

    try:
        while True:
            store   = random.choice(STORES)
            product = random.choice(PRODUCTS)

            # Burst de ventes (simule un pic pendant les soldes)
            nb = random.randint(3, 10) if random.random() < args.burst_prob else 1

            for _ in range(nb):
                sale = make_sale(store, product)
                producer.send("ventes", key=f"{store}_{product}", value=sale)

            # Événement de stock après chaque cycle de ventes
            stock_evt = make_stock_event(store, product)
            producer.send("stock", key=f"{store}_{product}", value=stock_evt)

            count += nb
            if count % 100 == 0:
                lvl = stocks[(store, product)]
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"{count} ventes envoyées | "
                    f"{store}/{product} stock={lvl}"
                )

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n⛔ Arrêt — {count} événements envoyés au total")
    finally:
        producer.flush()
        producer.close()


if __name__ == "__main__":
    main()
