-- ─────────────────────────────────────────────────────────────
-- init.sql — Initialisation de la base PostgreSQL retail_db
-- Crée la table stock et active la réplication logique pour CDC
-- ─────────────────────────────────────────────────────────────

-- Activer l'extension pgoutput pour Debezium
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table des niveaux de stock
CREATE TABLE IF NOT EXISTS stock (
    id          SERIAL PRIMARY KEY,
    store_id    VARCHAR(10)  NOT NULL,
    product_id  VARCHAR(10)  NOT NULL,
    level       INT          NOT NULL DEFAULT 0,
    updated_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (store_id, product_id)
);

-- Données initiales (stocks de départ)
INSERT INTO stock (store_id, product_id, level) VALUES
    ('S01', 'P001', 150), ('S01', 'P002', 120), ('S01', 'P003', 200),
    ('S01', 'P004', 80),  ('S01', 'P005', 175), ('S01', 'P006', 90),
    ('S02', 'P001', 130), ('S02', 'P002', 160), ('S02', 'P003', 110),
    ('S02', 'P004', 95),  ('S02', 'P005', 140), ('S02', 'P006', 185),
    ('S03', 'P001', 200), ('S03', 'P002', 75),  ('S03', 'P003', 165),
    ('S03', 'P004', 120), ('S03', 'P005', 90),  ('S03', 'P006', 145)
ON CONFLICT (store_id, product_id) DO NOTHING;

-- Publication pour Debezium CDC (réplication logique)
CREATE PUBLICATION debezium_pub FOR TABLE stock;

-- Fonction pour mettre à jour updated_at automatiquement
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER stock_updated_at
    BEFORE UPDATE ON stock
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
