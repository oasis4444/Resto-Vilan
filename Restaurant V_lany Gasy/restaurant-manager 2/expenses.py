from datetime import datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from extensions import db
from models import (
    Expense, Purchase, FundingSource, FixedExpense,
    EXPENSE_CATEGORIES, FIXED_EXPENSE_CATEGORIES, VARIABLE_EXPENSE_CATEGORIES,
    EXPENSE_TYPE_FIXED, EXPENSE_TYPE_VARIABLE,
    ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_SUPER_ADMIN,
)
from decorators import roles_required
from utils import parse_float, now_local, local_today_start_utc, local_to_utc, LOCAL_OFFSET

expenses_bp = Blueprint("expenses", __name__)

FRENCH_MONTHS = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                 "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


# ---------------------------------------------------------------------------
# Outils de période
# ---------------------------------------------------------------------------
def _period_bounds(period):
    """Filtres rapides de la « Vue globale » (comme avant)."""
    if period == "today":
        return local_today_start_utc(), "Aujourd'hui"
    if period == "week":
        return local_today_start_utc(6), "Cette semaine (7 derniers jours)"
    if period == "month":
        return local_today_start_utc(29), "Ce mois (30 derniers jours)"
    return None, "Toutes les dépenses"


def _parse_month(raw):
    """'2026-09' → (2026, 9). Par défaut : le mois en cours (heure locale)."""
    try:
        y, m = raw.split("-")
        y, m = int(y), int(m)
        if 1 <= m <= 12 and 2000 <= y <= 2100:
            return y, m
    except (AttributeError, ValueError):
        pass
    n = now_local()
    return n.year, n.month


def _month_bounds_utc(y, m):
    start_local = datetime(y, m, 1)
    end_local = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)
    return local_to_utc(start_local), local_to_utc(end_local)


def _shift_month(y, m, delta):
    m += delta
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return y, m


def _parse_form_date(raw):
    """Date du formulaire (AAAA-MM-JJ, heure locale) → datetime UTC à midi,
    pour que la date affichée reste la bonne quel que soit le fuseau."""
    try:
        d = datetime.strptime((raw or "").strip(), "%Y-%m-%d")
        return local_to_utc(d.replace(hour=12))
    except ValueError:
        return datetime.utcnow()


def _can_edit_fixed():
    return current_user.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN)


# ---------------------------------------------------------------------------
# PAGE DÉPENSES
#   - Onglet « Fixes & Variables » (par défaut) : deux colonnes côte à côte
#   - Onglet « Vue globale » : l'ancienne page, inchangée (achats + dépenses)
# ---------------------------------------------------------------------------
@expenses_bp.route("/expenses")
@login_required
@roles_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def expenses_list():
    view = request.args.get("view", "split")
    if view == "global":
        return _global_view()
    return _split_view()


def _split_view():
    y, m = _parse_month(request.args.get("m"))
    period_key = f"{y:04d}-{m:02d}"
    start, end = _month_bounds_utc(y, m)
    prev_y, prev_m = _shift_month(y, m, -1)
    next_y, next_m = _shift_month(y, m, 1)
    now = now_local()
    is_current_month = (y, m) == (now.year, now.month)

    # --- Dépenses FIXES : lignes prévues + paiements du mois
    fixed_items = FixedExpense.query.filter_by(is_active=True).order_by(FixedExpense.name).all()
    fixed_rows = []
    for fx in fixed_items:
        payments = sorted(fx.payments_for(period_key), key=lambda e: e.date)
        paid = sum(p.amount for p in payments)
        fixed_rows.append({
            "fx": fx, "payments": payments, "paid": paid,
            "remaining": max(fx.amount - paid, 0),
            "status": "paid" if paid >= fx.amount and fx.amount > 0 else ("partial" if paid > 0 else "todo"),
        })
    fixed_planned = sum(fx.amount for fx in fixed_items)

    # Paiements « fixes » du mois : ceux liés à une ligne + ceux saisis à la main
    month_fixed_expenses = Expense.query.filter(
        Expense.expense_type == EXPENSE_TYPE_FIXED,
        db.or_(
            Expense.period == period_key,
            db.and_(Expense.period.is_(None), Expense.date >= start, Expense.date < end),
        ),
    ).order_by(Expense.date.desc()).all()
    active_fixed_ids = {fx.id for fx in fixed_items}
    other_fixed = [e for e in month_fixed_expenses if e.fixed_expense_id not in active_fixed_ids]
    fixed_paid_total = sum(e.amount for e in month_fixed_expenses if not e.is_cancelled)

    # --- Dépenses VARIABLES du mois
    variable_expenses = Expense.query.filter(
        Expense.expense_type != EXPENSE_TYPE_FIXED,
        Expense.date >= start, Expense.date < end,
    ).order_by(Expense.date.desc()).all()
    variable_total = sum(e.amount for e in variable_expenses if not e.is_cancelled)
    var_by_cat = {}
    for e in variable_expenses:
        if not e.is_cancelled:
            var_by_cat[e.category] = var_by_cat.get(e.category, 0) + e.amount
    var_by_cat = sorted(var_by_cat.items(), key=lambda x: x[1], reverse=True)

    # --- Achats d'ingrédients du mois (pour le total global)
    purchases_total = sum(
        p.total for p in Purchase.query.filter(
            Purchase.is_cancelled.is_(False), Purchase.date >= start, Purchase.date < end
        ).all()
    )

    return render_template(
        "expenses.html",
        view="split",
        month_label=f"{FRENCH_MONTHS[m]} {y}",
        period_key=period_key,
        prev_key=f"{prev_y:04d}-{prev_m:02d}",
        next_key=f"{next_y:04d}-{next_m:02d}",
        is_current_month=is_current_month,
        fixed_rows=fixed_rows,
        other_fixed=other_fixed,
        fixed_planned=fixed_planned,
        fixed_paid_total=fixed_paid_total,
        variable_expenses=variable_expenses,
        variable_total=variable_total,
        var_by_cat=var_by_cat,
        purchases_total=purchases_total,
        grand_total=fixed_paid_total + variable_total + purchases_total,
        funding_sources=FundingSource.query.order_by(FundingSource.name).all(),
        today_str=now.strftime("%Y-%m-%d"),
        can_edit_fixed=_can_edit_fixed(),
    )


def _global_view():
    period = request.args.get("period", "today")
    start, period_label = _period_bounds(period)

    purchases_q = Purchase.query
    expenses_q = Expense.query
    if start:
        purchases_q = purchases_q.filter(Purchase.date >= start)
        expenses_q = expenses_q.filter(Expense.date >= start)

    purchases = purchases_q.order_by(Purchase.date.desc()).all()
    general_expenses = expenses_q.order_by(Expense.date.desc()).all()

    # Fusionne les deux listes en une seule vue triée par date.
    # Les entrées annulées restent visibles (barrées) pour la traçabilité, mais
    # ne comptent pas dans les totaux ni la répartition par catégorie.
    rows = []
    for p in purchases:
        rows.append({
            "date": p.date, "type": "Achat ingrédient", "category": p.ingredient.category or "Ingrédient",
            "label": p.ingredient.name, "detail": p.supplier or "",
            "amount": p.total, "source": p.funding_source.name if p.funding_source else "—",
            "is_cancelled": p.is_cancelled, "kind": "purchase", "id": p.id,
            "cancel_reason": p.cancel_reason, "cancelled_by": p.cancelled_by.username if p.cancelled_by else None,
        })
    for e in general_expenses:
        rows.append({
            "date": e.date, "type": "Dépense fixe" if e.is_fixed else "Dépense variable",
            "category": e.category,
            "label": e.fixed_expense.name if e.fixed_expense else e.category, "detail": e.description or "",
            "amount": e.amount, "source": e.funding_source.name if e.funding_source else "—",
            "is_cancelled": e.is_cancelled, "kind": "expense", "id": e.id,
            "cancel_reason": e.cancel_reason, "cancelled_by": e.cancelled_by.username if e.cancelled_by else None,
        })
    rows.sort(key=lambda r: r["date"], reverse=True)

    active_purchases = [p for p in purchases if not p.is_cancelled]
    active_expenses = [e for e in general_expenses if not e.is_cancelled]

    total_purchases = sum(p.total for p in active_purchases)
    total_fixed = sum(e.amount for e in active_expenses if e.is_fixed)
    total_variable = sum(e.amount for e in active_expenses if not e.is_fixed)
    total_expenses = total_fixed + total_variable
    grand_total = total_purchases + total_expenses

    by_category = {}
    for r in rows:
        if r["is_cancelled"]:
            continue
        by_category[r["category"]] = by_category.get(r["category"], 0) + r["amount"]
    by_category = sorted(by_category.items(), key=lambda x: x[1], reverse=True)

    return render_template(
        "expenses.html",
        view="global",
        rows=rows, period=period, period_label=period_label,
        total_purchases=total_purchases, total_expenses=total_expenses,
        total_fixed=total_fixed, total_variable=total_variable,
        grand_total=grand_total, by_category=by_category,
    )


# ---------------------------------------------------------------------------
# Ajouter une dépense (variable par défaut ; « fixe » ponctuelle possible)
# ---------------------------------------------------------------------------
@expenses_bp.route("/expenses/add", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def expense_add():
    funding_sources = FundingSource.query.order_by(FundingSource.name).all()
    expense_type = request.values.get("type", EXPENSE_TYPE_VARIABLE)
    if expense_type not in (EXPENSE_TYPE_FIXED, EXPENSE_TYPE_VARIABLE):
        expense_type = EXPENSE_TYPE_VARIABLE

    def render():
        return render_template(
            "expense_add.html",
            categories=FIXED_EXPENSE_CATEGORIES if expense_type == EXPENSE_TYPE_FIXED else VARIABLE_EXPENSE_CATEGORIES,
            funding_sources=funding_sources,
            today_str=now_local().strftime("%Y-%m-%d"),
            expense_type=expense_type,
        )

    if request.method == "POST":
        category = request.form.get("category", "").strip() or "Autre"
        description = request.form.get("description", "").strip()
        amount = parse_float(request.form.get("amount"))
        funding_source_id = request.form.get("funding_source_id") or None

        if amount is None or amount <= 0:
            flash("Veuillez compléter un montant valide (nombre supérieur à 0).", "danger")
            return render()

        expense_date = _parse_form_date(request.form.get("date"))
        local_date = expense_date + LOCAL_OFFSET

        expense = Expense(
            date=expense_date,
            category=category,
            description=description,
            amount=amount,
            expense_type=expense_type,
            period=local_date.strftime("%Y-%m") if expense_type == EXPENSE_TYPE_FIXED else None,
            funding_source_id=int(funding_source_id) if funding_source_id else None,
            created_by_id=current_user.id,
        )
        db.session.add(expense)
        db.session.commit()
        kind = "fixe" if expense_type == EXPENSE_TYPE_FIXED else "variable"
        flash(f"Dépense {kind} « {category} » de {amount:,.0f} Ar enregistrée.".replace(",", " "), "success")
        return redirect(url_for("expenses.expenses_list", m=local_date.strftime("%Y-%m")))

    return render()


@expenses_bp.route("/expenses/<int:expense_id>/cancel", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN)
def expense_cancel(expense_id):
    """Annule une dépense (au lieu de la supprimer) — garde la trace de qui a
    annulé, quand, et pourquoi."""
    expense = Expense.query.get_or_404(expense_id)
    back = request.form.get("next") or url_for("expenses.expenses_list", view="global", period="all")

    if expense.is_cancelled:
        flash("Cette dépense est déjà annulée.", "warning")
        return redirect(back)

    reason = request.form.get("reason", "").strip()
    expense.is_cancelled = True
    expense.cancelled_at = datetime.utcnow()
    expense.cancelled_by_id = current_user.id
    expense.cancel_reason = reason or None
    db.session.commit()

    flash(f"Dépense « {expense.category} » annulée.", "success")
    return redirect(back)


# ---------------------------------------------------------------------------
# DÉPENSES FIXES — lignes prévues chaque mois (Admin / Super-Admin seulement)
# ---------------------------------------------------------------------------
def _fixed_form_values(fx=None):
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip() or "Autre"
    amount = parse_float(request.form.get("amount"))
    due_raw = request.form.get("due_day", "").strip()
    due_day = None
    if due_raw:
        try:
            due_day = int(due_raw)
            if not 1 <= due_day <= 31:
                due_day = None
        except ValueError:
            due_day = None
    src = request.form.get("funding_source_id") or None
    return {
        "name": name, "category": category, "amount": amount, "due_day": due_day,
        "funding_source_id": int(src) if src else None,
        "notes": request.form.get("notes", "").strip() or None,
    }


@expenses_bp.route("/expenses/fixed/add", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN)
def fixed_add():
    funding_sources = FundingSource.query.order_by(FundingSource.name).all()
    if request.method == "POST":
        v = _fixed_form_values()
        if not v["name"] or v["amount"] is None or v["amount"] < 0:
            flash("Indiquez un nom et un montant mensuel valide.", "danger")
            return render_template("fixed_expense_form.html", fx=None, categories=FIXED_EXPENSE_CATEGORIES,
                                   funding_sources=funding_sources, form=request.form)
        fx = FixedExpense(**v, updated_by_id=current_user.id, updated_at=datetime.utcnow())
        db.session.add(fx)
        db.session.commit()
        flash(f"Dépense fixe « {fx.name} » ajoutée ({fx.amount:,.0f} Ar / mois).".replace(",", " "), "success")
        return redirect(url_for("expenses.expenses_list"))
    return render_template("fixed_expense_form.html", fx=None, categories=FIXED_EXPENSE_CATEGORIES,
                           funding_sources=funding_sources, form={})


@expenses_bp.route("/expenses/fixed/<int:fixed_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_ADMIN)
def fixed_edit(fixed_id):
    fx = FixedExpense.query.get_or_404(fixed_id)
    funding_sources = FundingSource.query.order_by(FundingSource.name).all()
    if request.method == "POST":
        if request.form.get("action") == "deactivate":
            fx.is_active = False
            fx.updated_by_id = current_user.id
            fx.updated_at = datetime.utcnow()
            db.session.commit()
            flash(f"« {fx.name} » retirée des dépenses fixes (l'historique des paiements est conservé).", "success")
            return redirect(url_for("expenses.expenses_list"))
        v = _fixed_form_values(fx)
        if not v["name"] or v["amount"] is None or v["amount"] < 0:
            flash("Indiquez un nom et un montant mensuel valide.", "danger")
            return render_template("fixed_expense_form.html", fx=fx, categories=FIXED_EXPENSE_CATEGORIES,
                                   funding_sources=funding_sources, form=request.form)
        for k, val in v.items():
            setattr(fx, k, val)
        fx.updated_by_id = current_user.id
        fx.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f"Dépense fixe « {fx.name} » mise à jour.", "success")
        return redirect(url_for("expenses.expenses_list"))
    return render_template("fixed_expense_form.html", fx=fx, categories=FIXED_EXPENSE_CATEGORIES,
                           funding_sources=funding_sources, form={})


@expenses_bp.route("/expenses/fixed/<int:fixed_id>/pay", methods=["POST"])
@login_required
@roles_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def fixed_pay(fixed_id):
    """Enregistre le paiement d'une dépense fixe pour un mois donné
    (paiement partiel possible, ex : avance sur salaire)."""
    fx = FixedExpense.query.get_or_404(fixed_id)
    period_key = request.form.get("period", "")
    y, m = _parse_month(period_key)
    period_key = f"{y:04d}-{m:02d}"
    amount = parse_float(request.form.get("amount"))
    if amount is None or amount <= 0:
        flash("Montant du paiement invalide.", "danger")
        return redirect(url_for("expenses.expenses_list", m=period_key))

    src = request.form.get("funding_source_id") or fx.funding_source_id
    expense = Expense(
        date=_parse_form_date(request.form.get("date")),
        category=fx.category,
        description=(request.form.get("description", "").strip() or fx.name),
        amount=amount,
        expense_type=EXPENSE_TYPE_FIXED,
        fixed_expense_id=fx.id,
        period=period_key,
        funding_source_id=int(src) if src else None,
        created_by_id=current_user.id,
    )
    db.session.add(expense)
    db.session.commit()
    flash(f"Paiement « {fx.name} » ({FRENCH_MONTHS[m]} {y}) : {amount:,.0f} Ar enregistré.".replace(",", " "), "success")
    return redirect(url_for("expenses.expenses_list", m=period_key))
