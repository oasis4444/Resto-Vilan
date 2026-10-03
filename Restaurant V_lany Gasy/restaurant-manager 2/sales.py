from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from extensions import db
from models import MenuItem, Sale, SaleItem, PAYMENT_METHODS, ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_SERVER, ROLE_CASHIER, Settings
from decorators import roles_required

sales_bp = Blueprint("sales", __name__)


@sales_bp.route("/sales/new", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN, ROLE_SERVER, ROLE_CASHIER)
def sale_new():
    """Interface Commande/Caisse — section 2.4 : le serveur choisit les menus,
    quantités, table, mode de paiement. Le stock est décrémenté automatiquement
    selon la recette de chaque menu vendu."""

    items = MenuItem.active().filter_by(available=True).order_by(MenuItem.category, MenuItem.name).all()
    # On ne propose que les menus réellement disponibles (stock suffisant)
    items = [i for i in items if i.is_really_available()]

    if request.method == "POST":
        table_number = request.form.get("table_number", "").strip()
        client_name = request.form.get("client_name", "").strip()
        payment_method = request.form.get("payment_method", "Espèces")

        menu_ids = request.form.getlist("menu_item_id[]")
        quantities = request.form.getlist("quantity[]")

        lines = []
        for mid, qty in zip(menu_ids, quantities):
            try:
                mid_i, qty_i = int(mid), int(float(str(qty).replace(",", ".")))
            except (TypeError, ValueError):
                continue
            if qty_i > 0:
                lines.append((mid_i, qty_i))

        if not lines:
            flash("Veuillez sélectionner au moins un menu avec une quantité.", "danger")
            return render_template("sale_new.html", items=items, payment_methods=PAYMENT_METHODS)

        # Vérification du stock disponible avant de valider la vente
        menu_items = {m.id: m for m in MenuItem.active().filter(MenuItem.id.in_([mid for mid, _ in lines])).all()}
        # Ignore les menus inconnus / supprimés / indisponibles entre-temps
        missing = [mid for mid, _ in lines if mid not in menu_items or not menu_items[mid].available]
        if missing:
            flash("Un menu de la commande n'est plus disponible. Vérifiez la commande et réessayez.", "danger")
            return render_template("sale_new.html", items=items, payment_methods=PAYMENT_METHODS)
        for mid, qty in lines:
            menu = menu_items.get(mid)
            if not menu:
                continue
            for recipe_item in menu.recipe_items:
                needed = recipe_item.quantity_per_portion * qty
                if recipe_item.ingredient.stock_quantity < needed:
                    flash(
                        f"Stock insuffisant pour « {recipe_item.ingredient.name} » "
                        f"(nécessaire pour « {menu.name} »). Vente annulée.",
                        "danger",
                    )
                    return render_template("sale_new.html", items=items, payment_methods=PAYMENT_METHODS)

        sale = Sale(
            table_number=table_number,
            client_name=client_name,
            payment_method=payment_method,
            server_id=current_user.id,
            created_at=datetime.utcnow(),
        )
        db.session.add(sale)
        db.session.flush()

        total = 0
        for mid, qty in lines:
            menu = menu_items[mid]
            db.session.add(
                SaleItem(sale_id=sale.id, menu_item_id=mid, quantity=qty, unit_price=menu.sale_price)
            )
            total += menu.sale_price * qty

            # Décrémentation automatique du stock selon la recette (section 2.4)
            for recipe_item in menu.recipe_items:
                recipe_item.ingredient.stock_quantity -= recipe_item.quantity_per_portion * qty

        sale.total = total
        db.session.commit()

        flash(f"Vente enregistrée ! Total : {total:.0f} Ar", "success")
        auto = Settings.get().auto_print_receipt
        return redirect(url_for("sales.sale_receipt", sale_id=sale.id, **({"print": 1} if auto else {})))

    return render_template("sale_new.html", items=items, payment_methods=PAYMENT_METHODS)


@sales_bp.route("/sales")
@login_required
@roles_required(ROLE_ADMIN, ROLE_CASHIER)
def sale_list():
    sales = Sale.query.order_by(Sale.created_at.desc()).limit(100).all()
    return render_template("sale_list.html", sales=sales)


@sales_bp.route("/sales/<int:sale_id>/receipt")
@login_required
@roles_required(ROLE_ADMIN, ROLE_SERVER, ROLE_CASHIER)
def sale_receipt(sale_id):
    """Ticket de caisse imprimable — section 7."""
    sale = Sale.query.get_or_404(sale_id)
    return render_template("sale_receipt.html", sale=sale, settings=Settings.get(),
                           autoprint=request.args.get("print") == "1")


@sales_bp.route("/sales/<int:sale_id>/invoice")
@login_required
@roles_required(ROLE_ADMIN)
def sale_invoice(sale_id):
    """Facture officielle imprimable (NIF/STAT, coordonnées complètes) — section 7."""
    sale = Sale.query.get_or_404(sale_id)
    return render_template("sale_invoice.html", sale=sale, settings=Settings.get())
