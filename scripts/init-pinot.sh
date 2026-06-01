#!/bin/bash
# ──────────────────────────────────────────────────────────────
# init-pinot.sh — Initialise les schemas et tables Apache Pinot
# Usage : bash scripts/init-pinot.sh
# ──────────────────────────────────────────────────────────────
PINOT="http://localhost:9000"
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "⏳ Attente que Pinot Controller soit prêt..."
until curl -sf "$PINOT/health" > /dev/null 2>&1; do
  printf "."
  sleep 3
done
echo -e "\n✅ Pinot Controller prêt"

# ── Schemas ──────────────────────────────────────────────────
echo ""
echo "📋 Création des schemas..."
for f in "$BASE_DIR/pinot/schemas/"*.json; do
  name=$(basename "$f" _schema.json)
  CODE=$(curl -s -o /tmp/pinot_out.txt -w "%{http_code}" \
    -X POST "$PINOT/schemas" \
    -H "Content-Type: application/json" \
    -d @"$f")
  if [ "$CODE" = "200" ] || [ "$CODE" = "201" ]; then
    echo "  ✅ Schema '$name'"
  else
    echo "  ⚠️  Schema '$name' — HTTP $CODE : $(cat /tmp/pinot_out.txt)"
  fi
done

# ── Tables ───────────────────────────────────────────────────
echo ""
echo "📦 Création des tables..."
for f in "$BASE_DIR/pinot/tables/"*.json; do
  name=$(basename "$f" _table.json)
  CODE=$(curl -s -o /tmp/pinot_out.txt -w "%{http_code}" \
    -X POST "$PINOT/tables" \
    -H "Content-Type: application/json" \
    -d @"$f")
  if [ "$CODE" = "200" ] || [ "$CODE" = "201" ]; then
    echo "  ✅ Table '$name'"
  else
    echo "  ⚠️  Table '$name' — HTTP $CODE : $(cat /tmp/pinot_out.txt)"
  fi
done

echo ""
echo "🎉 Initialisation Pinot terminée !"
echo ""
echo "URLs utiles :"
echo "  Pinot UI     → http://localhost:9000"
echo "  Kafka UI     → http://localhost:8080"
echo "  API Swagger  → http://localhost:8000/docs"
echo "  Dashboard    → http://localhost:8501"
