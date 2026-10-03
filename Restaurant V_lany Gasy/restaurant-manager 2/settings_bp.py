import os
import uuid

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required

from extensions import db
import json

from models import Settings, ROLES, ROLE_ADMIN
from decorators import roles_required

settings_bp = Blueprint("settings", __name__)

ALLOWED_LOGO_EXT = {"png", "jpg", "jpeg", "svg", "webp"}


@settings_bp.route("/settings", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN)
def settings_page():
    settings = Settings.get()

    if request.method == "POST":
        settings.restaurant_name = request.form.get("restaurant_name", "").strip() or settings.restaurant_name
        settings.address = request.form.get("address", "").strip()
        settings.phone = request.form.get("phone", "").strip()
        settings.nif = request.form.get("nif", "").strip()
        settings.stat = request.form.get("stat", "").strip()
        settings.primary_color = request.form.get("primary_color", settings.primary_color)

        # Ticket : un seul message de remerciement + largeur du papier
        settings.receipt_message = request.form.get("receipt_message", "").strip()[:255] or None
        width = request.form.get("receipt_width", "80")
        settings.receipt_width = width if width in ("58", "80") else "80"
        settings.auto_print_receipt = request.form.get("auto_print_receipt") == "1"

        # Noms des rôles personnalisés (vide = nom par défaut)
        custom = {}
        for code, default_label in ROLES:
            value = " ".join(request.form.get(f"role_label_{code}", "").split())[:40]
            if value and value != default_label:
                custom[code] = value
        settings.role_labels_json = json.dumps(custom, ensure_ascii=False) if custom else None

        if request.form.get("reset_logo") == "1":
            settings.logo_filename = None

        logo = request.files.get("logo")
        if logo and logo.filename:
            ext = logo.filename.rsplit(".", 1)[-1].lower()
            if ext in ALLOWED_LOGO_EXT:
                upload_dir = os.path.join(current_app.root_path, "static", "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                new_name = f"logo_{uuid.uuid4().hex[:8]}.{ext}"
                logo.save(os.path.join(upload_dir, new_name))
                settings.logo_filename = new_name
            else:
                flash("Format de logo non supporté (utilisez PNG, JPG, SVG ou WEBP).", "danger")

        db.session.commit()
        flash("Paramètres du restaurant mis à jour avec succès !", "success")
        return redirect(url_for("settings.settings_page"))

    return render_template("settings.html", settings=settings, default_roles=ROLES,
                           custom_roles=settings.custom_role_labels())
