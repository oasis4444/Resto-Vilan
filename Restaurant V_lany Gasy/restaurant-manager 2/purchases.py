from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from extensions import db
from models import Ingredient, Purchase, FundingSource, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_SUPER_ADMIN
from decorators import roles_required
from utils import parse_float

purchases_bp = Blueprint("purchases", __name__)


# ---------------------------------------------------------------------------
# ACHAT — section 2.1
# ---------------------------------------------------------------------------
@purchases_bp.route("/purchases")
@login_required
@roles_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def purchase_list():
    purchases = Purchase.query.order_by(Purchase.date.desc()).limit(100).all()
    return render_template("purchase_list.html", purchases=purchases)


@purchases_bp.route("/purchases/add", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def purchase_add():
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    funding_sources = FundingSource.query.order_by(FundingSource.name).all()

    if request.method == "POST":
        ingredient_name = request.form.get("ingredient_name", "").strip()
        new_unit = request.form.get("new_unit", "pièce").strip() or "pièce"
        quantity = parse_float(request.form.get("quantity"), default=0)
        unit_price = parse_float(request.form.get("unit_price"), default=0)
        supplier = request.form.get("supplier", "").strip()
        funding_source_id = request.form.get("funding_source_id") or None

        if not ingredient_name or quantity <= 0:
            flash("Veuillez indiquer un ingrédient et une quantité valide.", "danger")
            return render_template(
                "purchase_add.html", ingredients=ingredients, funding_sources=funding_sources
            )

        # Recherche l'ingrédient par son nom (insensible à la casse) ; s'il
        # n'existe pas encore, on le crée automatiquement dans le Stock.
        ingredient = Ingredient.query.filter(
            db.func.lower(Ingredient.name) == ingredient_name.lower()
        ).first()

        if ingredient is None:
            ingredient = Ingredient(
                name=ingredient_name,
                category="",
                unit=new_unit,
                stock_quantity=0,
                alert_threshold=0,
                unit_price=unit_price,
            )
            db.session.add(ingredient)
            db.session.flush()  # pour obtenir ingredient.id

        purchase = Purchase(
            date=datetime.utcnow(),
            ingredient_id=ingredient.id,
            quantity=quantity,
            unit_price=unit_price,
            supplier=supplier,
            funding_source_id=int(funding_source_id) if funding_source_id else None,
            created_by_id=current_user.id,
        )
        db.session.add(purchase)

        # Lien direct avec le Stock : mise à jour automatique de la quantité (section 2.1)
        ingredient.stock_quantity += quantity

        db.session.commit()
        flash(
            f"Achat enregistré : {quantity} {ingredient.unit} de « {ingredient.name} » "
            f"ajouté(s) au stock.",
            "success",
        )
        return redirect(url_for("purchases.purchase_list"))

    return render_template("purchase_add.html", ingredients=ingredients, funding_sources=funding_sources)


@purchases_bp.route("/purchases/<int:purchase_id>/cancel", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def purchase_cancel(purchase_id):
    """Annule un achat (au lieu de le supprimer) : le stock ajouté par cet
    achat est retiré, et l'achat reste visible avec un badge "Annulé" pour
    garder la traçabilité (qui a annulé, quand, pourquoi)."""
    purchase = Purchase.query.get_or_404(purchase_id)

    if purchase.is_cancelled:
        flash("Cet achat est déjà annulé.", "warning")
        return redirect(url_for("purchases.purchase_list"))

    reason = request.form.get("reason", "").strip()

    # On retire du stock la quantité que cet achat avait ajoutée, sans jamais
    # descendre en dessous de 0 (au cas où une partie a déjà été consommée
    # entre-temps par des ventes).
    purchase.ingredient.stock_quantity = max(0, purchase.ingredient.stock_quantity - purchase.quantity)

    purchase.is_cancelled = True
    purchase.cancelled_at = datetime.utcnow()
    purchase.cancelled_by_id = current_user.id
    purchase.cancel_reason = reason or None
    db.session.commit()

    flash(f"Achat « {purchase.ingredient.name} » annulé. Le stock a été ajusté en conséquence.", "success")
    return redirect(url_for("purchases.purchase_list"))


# ---------------------------------------------------------------------------
# SOURCE DE FINANCEMENT — section 2.2
# ---------------------------------------------------------------------------
@purchases_bp.route("/funding-sources")
@login_required
@roles_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def funding_source_list():
    sources = FundingSource.query.order_by(FundingSource.name).all()
    return render_template("funding_source_list.html", sources=sources)


@purchases_bp.route("/funding-sources/add", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN)
def funding_source_add():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        initial_balance = parse_float(request.form.get("initial_balance"), default=0)

        if not name:
            flash("Le nom de la source de financement est requis.", "danger")
            return render_template("funding_source_add.html")

        source = FundingSource(name=name, initial_balance=initial_balance)
        db.session.add(source)
        db.session.commit()
        flash(f"Source de financement « {name} » créée avec succès !", "success")
        return redirect(url_for("purchases.funding_source_list"))

    return render_template("funding_source_add.html")
