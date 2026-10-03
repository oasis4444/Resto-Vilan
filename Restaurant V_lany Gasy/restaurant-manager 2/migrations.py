"""Mise à jour automatique de la base de données (sans perte de données).

`db.create_all()` crée les NOUVELLES tables, mais n'ajoute pas les nouvelles
colonnes aux tables déjà existantes. Ce module ajoute les colonnes manquantes
(ALTER TABLE ... ADD COLUMN) à chaque démarrage : c'est sans danger, car une
colonne déjà présente est simplement ignorée.
"""
from sqlalchemy import inspect, text

from extensions import db

# table -> [(colonne, définition SQL)]
NEW_COLUMNS = {
    "ingredients": [
        ("code", "VARCHAR(10)"),
    ],
    "expenses": [
        ("expense_type", "VARCHAR(20) NOT NULL DEFAULT 'variable'"),
        ("fixed_expense_id", "INTEGER"),
        ("period", "VARCHAR(7)"),
    ],
    "settings": [
        ("receipt_message", "VARCHAR(255)"),
        ("receipt_width", "VARCHAR(5) DEFAULT '80'"),
        ("role_labels_json", "TEXT"),
        ("auto_print_receipt", "BOOLEAN DEFAULT 0"),
    ],
    "menu_items": [
        ("is_archived", "BOOLEAN NOT NULL DEFAULT 0"),
    ],
}


def ensure_schema():
    """Ajoute les colonnes manquantes. Retourne la liste des ajouts faits."""
    added = []
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    for table, columns in NEW_COLUMNS.items():
        if table not in existing_tables:
            continue
        present = {c["name"] for c in inspector.get_columns(table)}
        for name, ddl in columns:
            if name not in present:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                added.append(f"{table}.{name}")
    if added:
        db.session.commit()
    return added


def backfill_ingredient_codes():
    """Donne un code court (PLT, YRT...) aux ingrédients qui n'en ont pas."""
    from models import Ingredient
    from utils import suggest_code, unique_code

    ingredients = Ingredient.query.order_by(Ingredient.id).all()
    taken = {i.code.upper() for i in ingredients if i.code}
    changed = 0
    for ing in ingredients:
        if not ing.code:
            ing.code = unique_code(suggest_code(ing.name), taken)
            taken.add(ing.code)
            changed += 1
    if changed:
        db.session.commit()
    return changed
