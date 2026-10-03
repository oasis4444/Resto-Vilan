"""Mise à jour v2 — à lancer UNE fois dans la console Bash de PythonAnywhere :

    cd restaurant-manager
    python3 mise_a_jour_v2.py

Ce que fait ce script (sans rien supprimer) :
  1. Copie de sécurité de la base : restaurant.db → restaurant_avant_v2_AAAAMMJJ_HHMM.db
  2. Ajoute les nouvelles colonnes/tables (codes ingrédients, dépenses fixes, ticket...)
  3. Donne un code court à chaque ingrédient (Poulet → PLT...)
  4. Met le logo V'lany Gasy et remplace le nom « AORN Group » par « V'lany Gasy »
Il peut être relancé sans danger.
"""
import os
import shutil
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "restaurant.db")

if os.path.isfile(DB):
    copy = os.path.join(BASE, f"restaurant_avant_v2_{datetime.now().strftime('%Y%m%d_%H%M')}.db")
    shutil.copy2(DB, copy)
    print(f"[1/4] Copie de sécurité : {os.path.basename(copy)}")
else:
    print("[1/4] Aucune base existante (elle sera créée).")

from app import app  # noqa: E402  (crée les tables + colonnes au démarrage)
from extensions import db  # noqa: E402
from models import Settings, Ingredient  # noqa: E402
from migrations import ensure_schema, backfill_ingredient_codes  # noqa: E402

with app.app_context():
    added = ensure_schema()
    print("[2/4] Base de données à jour" + (f" (ajouté : {', '.join(added)})" if added else "."))

    n = backfill_ingredient_codes()
    print(f"[3/4] Codes ingrédients : {n} créé(s).")
    for ing in Ingredient.query.order_by(Ingredient.name).all():
        print(f"        {ing.code:<6} {ing.name}")

    s = Settings.get()
    s.logo_filename = None  # → logo V'lany Gasy fourni (static/images/restaurant-logo.png)
    if not s.restaurant_name or "aorn" in s.restaurant_name.lower() or s.restaurant_name == "Restaurant Manager":
        s.restaurant_name = "V'lany Gasy"
    db.session.commit()
    print(f"[4/4] Logo V'lany Gasy activé. Nom du restaurant : {s.restaurant_name}")

print("\nTerminé ! Allez dans l'onglet « Web » et cliquez sur « Reload ».")
