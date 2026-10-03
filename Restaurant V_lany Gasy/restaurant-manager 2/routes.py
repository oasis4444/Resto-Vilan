import os
import uuid

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from extensions import db
from models import (
    Ingredient,
    MenuItem,
    RecipeItem,
    StockAdjustment,
    User,
    Sale,
    SaleItem,
    Purchase,
    Expense,
    FundingSource,
    ROLES,
    role_choices,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_STOCK_MANAGER,
    ROLE_SERVER,
    ROLE_CASHIER,
    ROLE_ACCOUNTANT,
)
from decorators import roles_required
from utils import parse_float, now_local, local_today_start_utc, suggest_code, unique_code, normalize_code

main_bp = Blueprint("main", __name__)


FRENCH_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
FRENCH_MONTHS_LOWER = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                       "août", "septembre", "octobre", "novembre", "décembre"]


# ---------------------------------------------------------------------------
# ACCUEIL — première page après la connexion. AUCUN chiffre financier ici :
# le propriétaire ne veut pas que les montants s'affichent dès le login.
# Les chiffres ne s'affichent qu'en cliquant sur « Tableau de bord ».
# ---------------------------------------------------------------------------
@main_bp.route("/")
@login_required
def home():
    if current_user.must_change_password:
        return redirect(url_for("auth.change_password"))

    n = now_local()
    if n.hour < 12:
        greeting = "Bonjour"
    elif n.hour < 18:
        greeting = "Bon après-midi"
    else:
        greeting = "Bonsoir"
    date_label = f"{FRENCH_DAYS[n.weekday()]} {n.day} {FRENCH_MONTHS_LOWER[n.month]} {n.year}"

    available_menus = [m for m in MenuItem.active().order_by(MenuItem.category, MenuItem.name).all()
                       if m.is_really_available()]
    total_menus = MenuItem.active().count()

    low_stock_count = 0
    if current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STOCK_MANAGER):
        low_stock_count = sum(1 for i in Ingredient.query.all() if i.is_low_stock())

    return render_template(
        "home.html",
        greeting=greeting,
        date_label=date_label,
        available_menus=available_menus,
        total_menus=total_menus,
        low_stock_count=low_stock_count,
    )


# ---------------------------------------------------------------------------
# Tableau de bord — chiffres et graphiques (uniquement quand on clique dessus)
# ---------------------------------------------------------------------------
@main_bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.must_change_password:
        return redirect(url_for("auth.change_password"))

    now = datetime.utcnow()
    today_start = local_today_start_utc()
    week_start = local_today_start_utc(6)  # 7 derniers jours (inclus aujourd'hui)
    month_start = local_today_start_utc(29)

    stats = {}
    can_see_stock = current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STOCK_MANAGER)
    can_see_money = current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_ACCOUNTANT)
    can_see_sales = current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_CASHIER, ROLE_ACCOUNTANT)

    if can_see_stock:
        stats["total_menus"] = MenuItem.active().count()
        stats["total_ingredients"] = Ingredient.query.count()
        stats["low_stock"] = [i for i in Ingredient.query.all() if i.is_low_stock()]

    if current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN):
        stats["total_users"] = User.query.count()

    if can_see_sales or can_see_money:
        all_sales = Sale.query.order_by(Sale.created_at.desc()).all()
        today_sales = [s for s in all_sales if s.created_at and s.created_at >= today_start]
        week_sales = [s for s in all_sales if s.created_at and s.created_at >= week_start]

        stats["revenue_today"] = sum(s.total for s in today_sales)
        stats["sales_count_today"] = len(today_sales)
        stats["recent_sales"] = all_sales[:5]

        # Graphique "Évolution des ventes" — 7 derniers jours
        chart_labels, chart_revenue = [], []
        for i in range(6, -1, -1):
            day = today_start - timedelta(days=i)
            day_end = day + timedelta(days=1)
            day_total = sum(s.total for s in week_sales if day <= s.created_at < day_end)
            chart_labels.append((now_local() - timedelta(days=i)).strftime("%d/%m"))
            chart_revenue.append(round(day_total))
        stats["chart_labels"] = chart_labels
        stats["chart_revenue"] = chart_revenue

        # Graphique "Répartition par catégorie" — 30 derniers jours
        month_sales = [s for s in all_sales if s.created_at and s.created_at >= month_start]
        category_totals = {}
        for s in month_sales:
            for item in s.items:
                cat = item.menu_item.category or "Autres"
                category_totals[cat] = category_totals.get(cat, 0) + item.line_total
        stats["category_labels"] = list(category_totals.keys())
        stats["category_values"] = [round(v) for v in category_totals.values()]

        # Produits les plus vendus (30 jours)
        qty_by_menu = {}
        for s in month_sales:
            for item in s.items:
                qty_by_menu[item.menu_item_id] = qty_by_menu.get(item.menu_item_id, 0) + item.quantity
        top = sorted(qty_by_menu.items(), key=lambda x: x[1], reverse=True)[:5]
        stats["top_products"] = [
            {"name": MenuItem.query.get(mid).name, "quantity": qty}
            for mid, qty in top if MenuItem.query.get(mid)
        ]

    if can_see_money:
        all_purchases = Purchase.query.filter_by(is_cancelled=False).order_by(Purchase.date.desc()).all()
        all_expenses = Expense.query.filter_by(is_cancelled=False).order_by(Expense.date.desc()).all()
        today_purchases = [p for p in all_purchases if p.date and p.date >= today_start]
        today_expenses = [e for e in all_expenses if e.date and e.date >= today_start]
        stats["expenses_today"] = sum(p.total for p in today_purchases) + sum(e.amount for e in today_expenses)
        stats["recent_purchases"] = all_purchases[:5]
        stats["total_purchases_all"] = sum(p.total for p in all_purchases) + sum(e.amount for e in all_expenses)
        stats["total_sales_all"] = sum(s.total for s in Sale.query.all())
        stats["estimated_profit_today"] = stats.get("revenue_today", 0) - stats["expenses_today"]

    return render_template("dashboard.html", stats=stats, now=now)


# ---------------------------------------------------------------------------
# MENU (section 2.3) — consultable par tous, modifiable par Admin/Super-Admin
# ---------------------------------------------------------------------------
@main_bp.route("/menu")
@login_required
def menu_list():
    items = MenuItem.active().order_by(MenuItem.category, MenuItem.name).all()
    archived = MenuItem.query.filter(MenuItem.is_archived.is_(True)).order_by(MenuItem.name).all()
    return render_template("menu.html", items=items, archived=archived)


@main_bp.route("/menu/<int:menu_id>/toggle-availability", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN, ROLE_STOCK_MANAGER)
def menu_toggle_availability(menu_id):
    """Marquer un menu disponible/indisponible manuellement (ex : plat en
    rupture pour la journée même si le stock des ingrédients existe encore)."""
    item = MenuItem.query.get_or_404(menu_id)
    item.available = not item.available
    db.session.commit()
    state = "disponible" if item.available else "indisponible"
    flash(f"« {item.name} » marqué comme {state}.", "success")
    return redirect(url_for("main.menu_list"))


@main_bp.route("/menu/add", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN)
def menu_add():
    ingredients = Ingredient.query.order_by(Ingredient.name).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        sale_price = parse_float(request.form.get("sale_price"), default=0)

        if not name:
            flash("Le nom du menu est requis.", "danger")
            return render_template("menu_add.html", ingredients=ingredients)

        item = MenuItem(name=name, category=category, sale_price=sale_price)

        # Photo du plat (optionnelle)
        new_photo = _save_menu_photo(request.files.get("photo"))
        if new_photo is False:
            flash("Format de photo non supporté (utilisez PNG, JPG ou WEBP). Menu créé sans photo.", "warning")
        elif new_photo:
            item.photo_filename = new_photo

        db.session.add(item)
        db.session.flush()  # pour obtenir item.id avant le commit

        _save_recipe(item)

        db.session.commit()
        flash(f"Menu « {name} » créé avec succès ! Vous pouvez imprimer sa fiche ci-dessous.", "success")
        return redirect(url_for("main.menu_detail", menu_id=item.id))

    return render_template("menu_add.html", ingredients=ingredients)


ALLOWED_PHOTO_EXT = {"png", "jpg", "jpeg", "webp"}


def _menu_upload_dir():
    return os.path.join(current_app.root_path, "static", "uploads", "menu")


def _save_menu_photo(photo):
    """Enregistre la photo envoyée. Retourne le nom du fichier, None s'il n'y a
    pas de photo, ou False si le format n'est pas accepté."""
    if not photo or not photo.filename:
        return None
    ext = photo.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_PHOTO_EXT:
        return False
    os.makedirs(_menu_upload_dir(), exist_ok=True)
    new_name = f"menu_{uuid.uuid4().hex[:10]}.{ext}"
    photo.save(os.path.join(_menu_upload_dir(), new_name))
    return new_name


def _delete_menu_photo_file(filename):
    """Efface VRAIMENT le fichier photo du serveur (pas seulement le lien)."""
    if not filename:
        return
    path = os.path.join(_menu_upload_dir(), os.path.basename(filename))
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _save_recipe(item):
    """Lit les lignes de recette du formulaire (ingrédient + quantité).
    Un même ingrédient choisi deux fois → quantités additionnées."""
    lines = {}
    for ing_id, qty_raw in zip(request.form.getlist("ingredient_id[]"), request.form.getlist("quantity[]")):
        qty = parse_float(qty_raw)
        try:
            ing_id = int(ing_id)
        except (TypeError, ValueError):
            continue
        if qty is not None and qty > 0 and Ingredient.query.get(ing_id):
            lines[ing_id] = lines.get(ing_id, 0) + qty
    for ing_id, qty in lines.items():
        db.session.add(RecipeItem(menu_item_id=item.id, ingredient_id=ing_id, quantity_per_portion=qty))


@main_bp.route("/menu/<int:menu_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN)
def menu_edit(menu_id):
    """Modifier un menu : nom, catégorie, prix, photo (changer / supprimer), recette."""
    item = MenuItem.query.get_or_404(menu_id)
    ingredients = Ingredient.query.order_by(Ingredient.name).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Le nom du menu est requis.", "danger")
            return render_template("menu_edit.html", item=item, ingredients=ingredients)
        price = parse_float(request.form.get("sale_price"))
        if price is None or price < 0:
            flash("Prix invalide.", "danger")
            return render_template("menu_edit.html", item=item, ingredients=ingredients)

        item.name = name
        item.category = request.form.get("category", "").strip()
        item.sale_price = price

        new_photo = _save_menu_photo(request.files.get("photo"))
        if new_photo is False:
            flash("Format de photo non supporté (PNG, JPG ou WEBP) : photo inchangée.", "warning")
        elif new_photo:
            _delete_menu_photo_file(item.photo_filename)
            item.photo_filename = new_photo
        elif request.form.get("remove_photo") == "1":
            _delete_menu_photo_file(item.photo_filename)
            item.photo_filename = None

        RecipeItem.query.filter_by(menu_item_id=item.id).delete()
        _save_recipe(item)
        db.session.commit()
        flash(f"Menu « {item.name} » modifié.", "success")
        return redirect(url_for("main.menu_list"))

    return render_template("menu_edit.html", item=item, ingredients=ingredients)


@main_bp.route("/menu/<int:menu_id>/photo/delete", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def menu_photo_delete(menu_id):
    """Supprimer uniquement la photo d'un menu (le fichier est effacé du serveur)."""
    item = MenuItem.query.get_or_404(menu_id)
    if item.photo_filename:
        _delete_menu_photo_file(item.photo_filename)
        item.photo_filename = None
        db.session.commit()
        flash(f"Photo de « {item.name} » supprimée.", "success")
    return redirect(request.form.get("next") or url_for("main.menu_list"))


@main_bp.route("/menu/<int:menu_id>/delete", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def menu_delete(menu_id):
    """Supprimer un menu.
    - Jamais vendu (ex : menu de test) → effacé complètement, photo comprise.
    - Déjà vendu → retiré de partout (carte, caisse, rapports...) mais gardé
      dans la base pour que les anciens tickets et rapports restent justes.
      Il reste restaurable depuis « Menus supprimés »."""
    item = MenuItem.query.get_or_404(menu_id)
    name = item.name
    _delete_menu_photo_file(item.photo_filename)
    item.photo_filename = None
    if SaleItem.query.filter_by(menu_item_id=item.id).first():
        item.is_archived = True
        item.available = False
        db.session.commit()
        flash(f"« {name} » supprimé de la carte. Il a déjà été vendu : il reste dans l'historique "
              "des ventes (restaurable en bas de la page Menu).", "success")
    else:
        db.session.delete(item)
        db.session.commit()
        flash(f"« {name} » supprimé définitivement.", "success")
    return redirect(url_for("main.menu_list"))


@main_bp.route("/menu/<int:menu_id>/restore", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def menu_restore(menu_id):
    item = MenuItem.query.get_or_404(menu_id)
    item.is_archived = False
    db.session.commit()
    flash(f"« {item.name} » remis dans la carte (marqué indisponible : activez-le quand il est prêt).", "success")
    return redirect(url_for("main.menu_list"))


def _menu_cost(menu):
    return sum(ri.quantity_per_portion * ri.ingredient.unit_price for ri in menu.recipe_items)


@main_bp.route("/menu/<int:menu_id>")
@login_required
def menu_detail(menu_id):
    """Fiche d'un menu (photo, prix, recette) — imprimable.
    Le coût et la marge ne sont visibles que par Admin / Super-Admin."""
    item = MenuItem.query.get_or_404(menu_id)
    show_cost = current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN)
    cost = _menu_cost(item) if show_cost else None
    return render_template("menu_detail.html", item=item, cost=cost, show_cost=show_cost, printed_at=now_local())


@main_bp.route("/menu/print")
@login_required
def menu_print():
    """Carte du restaurant imprimable : tous les menus avec photo et prix."""
    only_available = request.args.get("dispo") == "1"
    items = MenuItem.active().order_by(MenuItem.category, MenuItem.name).all()
    if only_available:
        items = [i for i in items if i.is_really_available()]
    groups = {}
    for it in items:
        groups.setdefault(it.category or "Autres", []).append(it)
    return render_template("menu_print.html", groups=groups, only_available=only_available, printed_at=now_local())


# ---------------------------------------------------------------------------
# STOCK / INGREDIENTS (section 2.5)
# ---------------------------------------------------------------------------
@main_bp.route("/stock")
@login_required
@roles_required(ROLE_ADMIN, ROLE_STOCK_MANAGER)
def stock_list():
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()
    return render_template("stock.html", ingredients=ingredients)


@main_bp.route("/search")
@login_required
def search():
    """Recherche globale (menus, ingrédients, ventes, achats, dépenses, utilisateurs),
    filtrée selon ce que le rôle de l'utilisateur peut normalement consulter."""
    q = request.args.get("q", "").strip()
    results = {}

    if q:
        like = f"%{q}%"

        # Menus : visibles par tous les rôles connectés
        results["menus"] = MenuItem.active().filter(MenuItem.name.ilike(like)).limit(10).all()

        if current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STOCK_MANAGER):
            results["ingredients"] = Ingredient.query.filter(
                db.or_(Ingredient.name.ilike(like), Ingredient.code.ilike(like))
            ).limit(10).all()

        if current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_CASHIER):
            results["sales"] = (
                Sale.query.filter(
                    db.or_(Sale.table_number.ilike(like), Sale.client_name.ilike(like))
                )
                .order_by(Sale.created_at.desc())
                .limit(10)
                .all()
            )

        if current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_ACCOUNTANT):
            results["purchases"] = (
                Purchase.query.join(Ingredient)
                .filter(db.or_(Ingredient.name.ilike(like), Purchase.supplier.ilike(like)))
                .order_by(Purchase.date.desc())
                .limit(10)
                .all()
            )
            results["expenses"] = (
                Expense.query.filter(
                    db.or_(Expense.category.ilike(like), Expense.description.ilike(like))
                )
                .order_by(Expense.date.desc())
                .limit(10)
                .all()
            )

        if current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN):
            results["users"] = User.query.filter(User.username.ilike(like)).limit(10).all()

    total_count = sum(len(v) for v in results.values())
    return render_template("search_results.html", q=q, results=results, total_count=total_count)


@main_bp.route("/stock/journal")
@login_required
@roles_required(ROLE_ADMIN)
def stock_journal():
    """Journal d'audit des modifications manuelles de stock — qui, quand,
    avant/après, pourquoi. Permet au propriétaire de vérifier à distance
    qu'aucune quantité n'a été changée sans trace (prévention du vol interne)."""
    adjustments = StockAdjustment.query.order_by(StockAdjustment.changed_at.desc()).limit(200).all()
    return render_template("stock_journal.html", adjustments=adjustments)


@main_bp.route("/stock/add", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN, ROLE_STOCK_MANAGER)
def stock_add():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Le nom de l'ingrédient est requis.", "danger")
            return render_template("stock_add.html")

        stock_quantity = parse_float(request.form.get("stock_quantity"), default=0)
        alert_threshold = parse_float(request.form.get("alert_threshold"), default=0)
        unit_price = parse_float(request.form.get("unit_price"), default=0)

        taken = {c.upper() for (c,) in db.session.query(Ingredient.code).filter(Ingredient.code.isnot(None))}
        wanted = normalize_code(request.form.get("code", ""))
        if wanted and wanted in taken:
            flash(f"Le code « {wanted} » est déjà utilisé par un autre ingrédient. Choisissez-en un autre.", "danger")
            return render_template("stock_add.html", form=request.form)
        code = wanted or unique_code(suggest_code(name), taken)

        ingredient = Ingredient(
            name=name,
            code=code,
            category=request.form.get("category", "").strip(),
            unit=request.form.get("unit", "pièce").strip() or "pièce",
            stock_quantity=stock_quantity,
            alert_threshold=alert_threshold,
            unit_price=unit_price,
        )
        db.session.add(ingredient)
        db.session.commit()
        flash(f"Ingrédient « {name} » créé avec succès ! Code : {code}", "success")
        if request.form.get("then") == "print":
            return redirect(url_for("main.stock_print", highlight=ingredient.id))
        return redirect(url_for("main.stock_list"))

    return render_template("stock_add.html", form={})


@main_bp.route("/stock/suggest-code")
@login_required
def stock_suggest_code():
    """Proposition de code en direct pendant la saisie du nom (formulaire)."""
    name = request.args.get("name", "")
    exclude_id = request.args.get("exclude", type=int)
    q = db.session.query(Ingredient.code).filter(Ingredient.code.isnot(None))
    if exclude_id:
        q = q.filter(Ingredient.id != exclude_id)
    taken = {c.upper() for (c,) in q}
    return {"code": unique_code(suggest_code(name), taken) if name.strip() else ""}


@main_bp.route("/stock/quick-add", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN, ROLE_STOCK_MANAGER)
def ingredient_quick_add():
    """Création rapide d'un ingrédient depuis la recette d'un menu (« + Créer »).
    Si un ingrédient du même nom existe déjà, on le renvoie au lieu d'en créer
    un doublon. Prix et stock à 0 : ils se complètent ensuite (Stock / Achats)."""
    name = " ".join(request.form.get("name", "").split())[:150]
    unit = request.form.get("unit", "").strip()[:20] or "pièce"
    if not name:
        return {"error": "Nom manquant"}, 400
    ing = Ingredient.query.filter(db.func.lower(Ingredient.name) == name.lower()).first()
    if not ing:
        taken = {c.upper() for (c,) in db.session.query(Ingredient.code).filter(Ingredient.code.isnot(None))}
        ing = Ingredient(name=name, code=unique_code(suggest_code(name), taken), unit=unit,
                         stock_quantity=0, alert_threshold=0, unit_price=0)
        db.session.add(ing)
        db.session.commit()
    return {"id": ing.id, "name": ing.name, "code": ing.code, "unit": ing.unit}


@main_bp.route("/stock/<int:ingredient_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN, ROLE_STOCK_MANAGER)
def ingredient_edit(ingredient_id):
    """Modifier un ingrédient : nom, code, catégorie, unité, seuil, prix.
    La QUANTITÉ ne se modifie pas ici (elle passe par « Modifier » dans la
    liste du stock, qui l'enregistre dans le journal)."""
    ing = Ingredient.query.get_or_404(ingredient_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Le nom de l'ingrédient est requis.", "danger")
            return render_template("ingredient_edit.html", ing=ing)
        code = normalize_code(request.form.get("code", ""))
        if not code:
            taken = {c.upper() for (c,) in db.session.query(Ingredient.code)
                     .filter(Ingredient.code.isnot(None), Ingredient.id != ing.id)}
            code = unique_code(suggest_code(name), taken)
        clash = Ingredient.query.filter(db.func.upper(Ingredient.code) == code, Ingredient.id != ing.id).first()
        if clash:
            flash(f"Le code « {code} » est déjà utilisé par « {clash.name} ».", "danger")
            return render_template("ingredient_edit.html", ing=ing)
        ing.name = name
        ing.code = code
        ing.category = request.form.get("category", "").strip()
        ing.unit = request.form.get("unit", ing.unit).strip() or ing.unit
        ing.alert_threshold = parse_float(request.form.get("alert_threshold"), default=ing.alert_threshold)
        ing.unit_price = parse_float(request.form.get("unit_price"), default=ing.unit_price)
        db.session.commit()
        flash(f"Ingrédient « {ing.name} » ({ing.code}) mis à jour.", "success")
        return redirect(url_for("main.stock_list"))
    return render_template("ingredient_edit.html", ing=ing)


@main_bp.route("/stock/<int:ingredient_id>/delete", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def ingredient_delete(ingredient_id):
    """Supprimer un ingrédient créé par erreur / pour un test.
    Refusé s'il a un historique (achat, recette, journal de stock), pour ne
    jamais fausser les comptes : dans ce cas il faut d'abord retirer la recette."""
    ing = Ingredient.query.get_or_404(ingredient_id)
    reasons = []
    menus = {ri.menu_item.name for ri in RecipeItem.query.filter_by(ingredient_id=ing.id).all()}
    if menus:
        reasons.append("utilisé dans la recette de : " + ", ".join(sorted(menus)))
    if Purchase.query.filter_by(ingredient_id=ing.id).first():
        reasons.append("il a déjà des achats enregistrés")
    if StockAdjustment.query.filter_by(ingredient_id=ing.id).first():
        reasons.append("il a un historique dans le journal du stock")
    if reasons:
        flash(f"Impossible de supprimer « {ing.name} » : " + " ; ".join(reasons) + ".", "danger")
        return redirect(url_for("main.ingredient_edit", ingredient_id=ing.id))
    name = ing.name
    db.session.delete(ing)
    db.session.commit()
    flash(f"Ingrédient « {name} » supprimé.", "success")
    return redirect(url_for("main.stock_list"))


@main_bp.route("/stock/print")
@login_required
@roles_required(ROLE_ADMIN, ROLE_STOCK_MANAGER)
def stock_print():
    """Liste des ingrédients imprimable (avec codes) — sert aussi de fiche
    d'inventaire physique (colonne « Compté » vide à remplir au stylo)."""
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()
    highlight = request.args.get("highlight", type=int)
    return render_template("stock_print.html", ingredients=ingredients, highlight=highlight, printed_at=now_local())


@main_bp.route("/stock/<int:ingredient_id>/adjust", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN, ROLE_STOCK_MANAGER)
def stock_adjust(ingredient_id):
    """Inventaire manuel : ajuster une quantité de stock (section 2.5).
    Chaque changement est enregistré (qui, quand, avant/après, pourquoi) pour
    la traçabilité — voir StockAdjustment."""
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    new_qty = parse_float(request.form.get("new_quantity"))
    reason = request.form.get("reason", "").strip()

    if new_qty is None:
        flash(
            f"Veuillez compléter une quantité valide (nombre) pour « {ingredient.name} ».",
            "danger",
        )
        return redirect(url_for("main.stock_list"))

    if new_qty < 0:
        flash("La quantité ne peut pas être négative.", "danger")
        return redirect(url_for("main.stock_list"))

    old_qty = ingredient.stock_quantity

    if old_qty != new_qty:
        db.session.add(StockAdjustment(
            ingredient_id=ingredient.id,
            old_quantity=old_qty,
            new_quantity=new_qty,
            reason=reason or None,
            changed_by_id=current_user.id,
        ))

    ingredient.stock_quantity = new_qty
    db.session.commit()
    flash(f"Stock « {ingredient.name} » mis à jour ({old_qty} → {new_qty}).", "success")
    return redirect(url_for("main.stock_list"))


# ---------------------------------------------------------------------------
# UTILISATEURS (section 3) — Admin/Super-Admin seulement
# ---------------------------------------------------------------------------
@main_bp.route("/users")
@login_required
@roles_required(ROLE_ADMIN)
def users_list():
    users = User.query.order_by(User.username).all()
    return render_template("users.html", users=users, roles=role_choices())


@main_bp.route("/users/add", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN)
def users_add():
    if request.method == "POST":
        username = " ".join(request.form.get("username", "").split())
        role = request.form.get("role", "")
        temp_password = request.form.get("temp_password", "")

        if not username or not temp_password:
            flash("Le nom d'utilisateur et le mot de passe temporaire sont requis.", "danger")
            return render_template("user_add.html", roles=role_choices())

        if User.query.filter(db.func.lower(User.username) == username).first():
            flash("Ce nom d'utilisateur existe déjà.", "danger")
            return render_template("user_add.html", roles=role_choices())

        user = User(
            username=username,
            role=role,
            must_change_password=True,
            created_by_id=current_user.id,
        )
        user.set_password(temp_password)
        db.session.add(user)
        db.session.commit()
        flash(
            f"Utilisateur « {username} » créé avec succès ! Mot de passe temporaire : "
            f"{temp_password} (il devra le changer à sa première connexion).",
            "success",
        )
        return redirect(url_for("main.users_list"))

    return render_template("user_add.html", roles=role_choices())


@main_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def users_delete(user_id):
    """« Supprimer » un utilisateur — Admin/Super-Admin seulement, et jamais
    un compte Admin/Super-Admin. Techniquement le compte est DÉSACTIVÉ (pas
    supprimé de la base) pour ne jamais casser l'historique (ventes, achats,
    dépenses, journal de stock) déjà lié à cet utilisateur — mais il ne peut
    plus du tout se connecter, ce qui revient au même pour vous."""
    user = User.query.get_or_404(user_id)

    if user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN):
        flash("Impossible de supprimer un compte Admin ou Super-Admin.", "danger")
        return redirect(url_for("main.users_list"))

    if user.id == current_user.id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "danger")
        return redirect(url_for("main.users_list"))

    user.is_active = False
    db.session.commit()
    flash(f"Utilisateur « {user.username} » supprimé (accès bloqué).", "success")
    return redirect(url_for("main.users_list"))


@main_bp.route("/users/<int:user_id>/reactivate", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def users_reactivate(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = True
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()
    flash(f"Utilisateur « {user.username} » réactivé.", "success")
    return redirect(url_for("main.users_list"))


@main_bp.route("/users/<int:user_id>/edit-role", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def users_edit_role(user_id):
    """Correction rapide du rôle d'un utilisateur (ex: erreur de sélection à la création)."""
    user = User.query.get_or_404(user_id)
    new_role = request.form.get("role", "")

    if user.role == ROLE_SUPER_ADMIN and current_user.role != ROLE_SUPER_ADMIN:
        flash("Seul un Super-Admin peut modifier un compte Super-Admin.", "danger")
        return redirect(url_for("main.users_list"))

    valid_roles = [r for r, _ in ROLES]
    if new_role not in valid_roles:
        flash("Rôle invalide.", "danger")
        return redirect(url_for("main.users_list"))

    if new_role == ROLE_SUPER_ADMIN and current_user.role != ROLE_SUPER_ADMIN:
        flash("Seul un Super-Admin peut attribuer le rôle Super-Admin.", "danger")
        return redirect(url_for("main.users_list"))

    user.role = new_role
    db.session.commit()
    flash(f"Rôle de « {user.username} » changé en « {user.role_label()} ».", "success")
    return redirect(url_for("main.users_list"))


@main_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN)
def users_edit(user_id):
    """Modifier le NOM D'UTILISATEUR (ex : « serveur1 » → « Patron ») et le rôle.
    - Un Admin ne peut pas modifier un compte Super-Admin.
    - Le nom reste unique (sans tenir compte des majuscules).
    - L'historique (ventes, achats...) suit automatiquement le nouveau nom."""
    user = User.query.get_or_404(user_id)
    if user.role == ROLE_SUPER_ADMIN and current_user.role != ROLE_SUPER_ADMIN:
        flash("Seul un Super-Admin peut modifier un compte Super-Admin.", "danger")
        return redirect(url_for("main.users_list"))

    if request.method == "POST":
        new_username = " ".join(request.form.get("username", "").split())
        new_role = request.form.get("role", user.role)
        email = request.form.get("email", "").strip()

        if not new_username or len(new_username) < 2:
            flash("Le nom d'utilisateur doit contenir au moins 2 caractères.", "danger")
            return render_template("user_edit.html", u=user, roles=role_choices())
        if len(new_username) > 80:
            flash("Le nom d'utilisateur est trop long (80 caractères maximum).", "danger")
            return render_template("user_edit.html", u=user, roles=role_choices())
        clash = User.query.filter(
            db.func.lower(User.username) == new_username.lower(), User.id != user.id
        ).first()
        if clash:
            flash(f"Le nom « {new_username} » est déjà pris par un autre compte.", "danger")
            return render_template("user_edit.html", u=user, roles=role_choices())

        valid_roles = [r for r, _ in ROLES]
        if new_role not in valid_roles:
            new_role = user.role
        if new_role == ROLE_SUPER_ADMIN and current_user.role != ROLE_SUPER_ADMIN:
            flash("Seul un Super-Admin peut attribuer le rôle Super-Admin.", "danger")
            return render_template("user_edit.html", u=user, roles=role_choices())
        if user.id == current_user.id and new_role != user.role:
            flash("Vous ne pouvez pas changer votre propre rôle.", "danger")
            return render_template("user_edit.html", u=user, roles=role_choices())

        old = user.username
        user.username = new_username
        user.role = new_role
        user.email = email or None
        db.session.commit()
        msg = f"Compte mis à jour : « {old} » → « {new_username} »." if old != new_username else "Compte mis à jour."
        if old != new_username:
            msg += " La personne devra désormais se connecter avec ce nouveau nom."
        flash(msg, "success")
        return redirect(url_for("main.users_list"))

    return render_template("user_edit.html", u=user, roles=role_choices())


@main_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
@roles_required(ROLE_SUPER_ADMIN)
def users_reset_password(user_id):
    """Section 4.4 : seul le Super-Admin peut réinitialiser manuellement
    le mot de passe de n'importe quel utilisateur."""
    user = User.query.get_or_404(user_id)
    new_temp_password = request.form.get("new_temp_password", "ChangeMoi123")
    user.set_password(new_temp_password)
    user.must_change_password = True
    user.locked_until = None
    user.failed_login_attempts = 0
    db.session.commit()
    flash(
        f"Mot de passe de « {user.username} » réinitialisé. "
        f"Nouveau mot de passe : {new_temp_password}",
        "success",
    )
    return redirect(url_for("main.users_list"))
