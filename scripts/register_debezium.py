"""
register_debezium.py — Enregistre le connecteur Debezium CDC
Surveille la table stock dans PostgreSQL et publie dans Kafka

Usage :
    python register_debezium.py
"""
import requests
import time
import json

DEBEZIUM_URL = "http://localhost:8083"

CONNECTOR_CONFIG = {
    "name": "stock-postgres-connector",
    "config": {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "database.hostname": "postgres",
        "database.port": "5432",
        "database.user": "retail_user",
        "database.password": "retail_pass",
        "database.dbname": "retail_db",
        "database.server.name": "retail",
        "table.include.list": "public.stock",
        "topic.prefix": "cdc",
        "plugin.name": "pgoutput",
        "publication.name": "debezium_pub",
        "slot.name": "debezium_slot",
        "transforms": "unwrap",
        "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
        "transforms.unwrap.drop.tombstones": "false",
        "key.converter": "org.apache.kafka.connect.json.JsonConverter",
        "value.converter": "org.apache.kafka.connect.json.JsonConverter",
        "key.converter.schemas.enable": "false",
        "value.converter.schemas.enable": "false"
    }
}


def wait_for_debezium():
    print("⏳ Attente que Debezium soit prêt...")
    for _ in range(30):
        try:
            r = requests.get(f"{DEBEZIUM_URL}/connectors", timeout=5)
            if r.ok:
                print("✅ Debezium prêt")
                return True
        except Exception:
            pass
        time.sleep(5)
        print("   ...")
    return False


def register_connector():
    # Supprimer l'ancien connecteur s'il existe
    try:
        requests.delete(
            f"{DEBEZIUM_URL}/connectors/stock-postgres-connector",
            timeout=5
        )
        print("🗑️  Ancien connecteur supprimé")
        time.sleep(2)
    except Exception:
        pass

    # Enregistrer le nouveau connecteur
    print("📡 Enregistrement du connecteur Debezium...")
    r = requests.post(
        f"{DEBEZIUM_URL}/connectors",
        headers={"Content-Type": "application/json"},
        data=json.dumps(CONNECTOR_CONFIG),
        timeout=10
    )

    if r.status_code in (200, 201):
        print("✅ Connecteur enregistré avec succès !")
        print(f"   Topic Kafka : cdc.public.stock")
        print(f"   PostgreSQL  : retail_db.public.stock")
    else:
        print(f"⚠️  Erreur HTTP {r.status_code} : {r.text}")


def check_status():
    time.sleep(3)
    r = requests.get(
        f"{DEBEZIUM_URL}/connectors/stock-postgres-connector/status",
        timeout=5
    )
    if r.ok:
        status = r.json()
        state = status.get("connector", {}).get("state", "UNKNOWN")
        print(f"\n📊 Statut du connecteur : {state}")
        tasks = status.get("tasks", [])
        for t in tasks:
            print(f"   Task {t['id']} : {t['state']}")


if __name__ == "__main__":
    if wait_for_debezium():
        register_connector()
        check_status()
        print("\n🎉 Debezium CDC opérationnel !")
        print("   Chaque modification dans PostgreSQL stock")
        print("   sera publiée dans Kafka automatiquement.")
    else:
        print("❌ Debezium non disponible — vérifie docker compose up -d")
