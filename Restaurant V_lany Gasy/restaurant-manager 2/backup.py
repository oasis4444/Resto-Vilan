import json
import os
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
)
from flask_login import login_required, current_user, logout_user

from extensions import db
from models import (
    User, Ingredient, StockAdjustment, MenuItem, RecipeItem, Sale, SaleItem, Purchase, Expense,
    FundingSource, FixedExpense, Settings, ROLE_SUPER_ADMIN,
)
from decorators import roles_required
from seed import ensure_super_admin

backup_bp = Blueprint("backup", __name__, url_prefix="/admin")

# Ordre d'export/suppression : respecte les clés étrangères
MODELS_IN_ORDER = [
    ("settings", Settings),
    ("users", User),
    ("ingredients", Ingredient),
    ("stock_adjustments", StockAdjustment),
    ("funding_sources", FundingSource),
    ("menu_items", MenuItem),
    ("recipe_items", RecipeItem),
    ("fixed_expenses", FixedExpense),
    ("purchases", Purchase),
    ("expenses", Expense),
    ("sales", Sale),
    ("sale_items", SaleItem),
]


def _backup_dir():
    path = os.path.join(current_app.instance_path, "backups")
    os.makedirs(path, exist_ok=True)
    return path


def _serialize_row(row):
    data = {}
    for col in row.__table__.columns:
        value = getattr(row, col.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        data[col.name] = value
    return data


def _build_backup_dict():
    payload = {"exported_at": datetime.utcnow().isoformat(), "tables": {}}
    for key, model in MODELS_IN_ORDER:
        payload["tables"][key] = [_serialize_row(row) for row in model.query.all()]
    return payload


def _wipe_all_tables():
    # Ordre inverse pour respecter les contraintes de clé étrangère
    for _, model in reversed(MODELS_IN_ORDER):
        model.query.delete()
    db.session.commit()


def _restore_from_dict(payload):
    _wipe_all_tables()
    for key, model in MODELS_IN_ORDER:
        rows = payload.get("tables", {}).get(key, [])
        for row_data in rows:
            clean = {}
            for col in model.__table__.columns:
                if col.name not in row_data:
                    continue
                value = row_data[col.name]
                if value is not None and str(col.type) in ("DATETIME",) and isinstance(value, str):
                    try:
                        value = datetime.fromisoformat(value)
                    except ValueError:
                        pass
                clean[col.name] = value
            db.session.add(model(**clean))
    db.session.commit()


# ---------------------------------------------------------------------------
# PAGE PRINCIPALE : sauvegardes locales + restauration + lien reset
# ---------------------------------------------------------------------------
@backup_bp.route("/backups")
@login_required
@roles_required(ROLE_SUPER_ADMIN)
def backups_home():
    files = []
    d = _backup_dir()
    for fname in sorted(os.listdir(d), reverse=True):
        if fname.endswith(".json"):
            full = os.path.join(d, fname)
            files.append({
                "name": fname,
                "size_kb": round(os.path.getsize(full) / 1024, 1),
                "date": datetime.fromtimestamp(os.path.getmtime(full)).strftime("%d/%m/%Y %H:%M"),
            })
    return render_template("backups.html", files=files)


@backup_bp.route("/backups/create", methods=["POST"])
@login_required
@roles_required(ROLE_SUPER_ADMIN)
def backups_create():
    payload = _build_backup_dict()
    filename = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    full_path = os.path.join(_backup_dir(), filename)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    flash(f"Sauvegarde « {filename} » créée avec succès.", "success")
    return redirect(url_for("backup.backups_home"))


@backup_bp.route("/backups/<filename>/download")
@login_required
@roles_required(ROLE_SUPER_ADMIN)
def backups_download(filename):
    full_path = os.path.join(_backup_dir(), filename)
    if not os.path.isfile(full_path):
        flash("Fichier de sauvegarde introuvable.", "danger")
        return redirect(url_for("backup.backups_home"))
    return send_file(full_path, as_attachment=True, download_name=filename)


@backup_bp.route("/backups/<filename>/restore", methods=["POST"])
@login_required
@roles_required(ROLE_SUPER_ADMIN)
def backups_restore(filename):
    full_path = os.path.join(_backup_dir(), filename)
    if not os.path.isfile(full_path):
        flash("Fichier de sauvegarde introuvable.", "danger")
        return redirect(url_for("backup.backups_home"))
    with open(full_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    _restore_from_dict(payload)
    logout_user()
    flash(
        f"Restauration effectuée à partir de « {filename} ». Veuillez vous reconnecter.", "success"
    )
    return redirect(url_for("auth.login"))


@backup_bp.route("/backups/restore-upload", methods=["POST"])
@login_required
@roles_required(ROLE_SUPER_ADMIN)
def backups_restore_upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Veuillez sélectionner un fichier de sauvegarde (.json).", "danger")
        return redirect(url_for("backup.backups_home"))
    try:
        payload = json.load(file)
    except Exception:
        flash("Fichier invalide : ce n'est pas une sauvegarde JSON reconnue.", "danger")
        return redirect(url_for("backup.backups_home"))

    _restore_from_dict(payload)
    logout_user()
    flash("Restauration effectuée à partir du fichier importé. Veuillez vous reconnecter.", "success")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# RÉINITIALISATION À L'ÉTAT D'ORIGINE (Factory Reset) — section 5.5
# ---------------------------------------------------------------------------
@backup_bp.route("/factory-reset", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPER_ADMIN)
def factory_reset():
    if request.method == "POST":
        confirmation = request.form.get("confirmation", "").strip()
        reset_type = request.form.get("reset_type", "total")

        if confirmation != "RÉINITIALISER":
            flash("Confirmation incorrecte. Vous devez taper exactement : RÉINITIALISER", "danger")
            return render_template("factory_reset.html")

        # Sauvegarde "forcée" avant toute réinitialisation (section 5.5)
        payload = _build_backup_dict()
        filename = f"backup_avant_reset_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(os.path.join(_backup_dir(), filename), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

        if reset_type == "total":
            _wipe_all_tables()
            ensure_super_admin(current_app)
            logout_user()
            flash(
                f"Réinitialisation totale effectuée. Une sauvegarde de sécurité « {filename} » "
                "a été conservée sur le serveur. Reconnectez-vous avec le compte Super-Admin "
                "par défaut.",
                "success",
            )
            return redirect(url_for("auth.login"))
        else:
            # Réinitialisation partielle : uniquement les données transactionnelles
            SaleItem.query.delete()
            Sale.query.delete()
            Purchase.query.delete()
            Expense.query.delete()
            db.session.commit()
            flash(
                f"Réinitialisation partielle effectuée (ventes, achats et dépenses supprimés, menu et "
                f"utilisateurs conservés). Sauvegarde de sécurité : « {filename} ».",
                "success",
            )
            return redirect(url_for("main.dashboard"))

    return render_template("factory_reset.html")
