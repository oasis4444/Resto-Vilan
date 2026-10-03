from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_login import login_required

from models import (
    Sale,
    SaleItem,
    Purchase,
    Expense,
    Ingredient,
    MenuItem,
    FundingSource,
    ROLE_ADMIN,
    ROLE_ACCOUNTANT,
)
from decorators import roles_required
from utils import now_local, local_today_start_utc, local_to_utc

FRENCH_MONTHS = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/reports")
@login_required
@roles_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def reports_dashboard():
    now = datetime.utcnow()
    last_30_days = now - timedelta(days=30)

    all_sales = Sale.query.all()
    recent_sales = [s for s in all_sales if s.created_at and s.created_at >= last_30_days]

    total_revenue = sum(s.total for s in all_sales)
    revenue_30d = sum(s.total for s in recent_sales)

    all_purchases = Purchase.query.filter_by(is_cancelled=False).all()
    all_expenses = Expense.query.filter_by(is_cancelled=False).all()
    total_spent = sum(p.total for p in all_purchases) + sum(e.amount for e in all_expenses)

    # Menu le plus vendu (30 derniers jours)
    sales_count_by_menu = {}
    for s in recent_sales:
        for item in s.items:
            sales_count_by_menu[item.menu_item_id] = (
                sales_count_by_menu.get(item.menu_item_id, 0) + item.quantity
            )
    top_menus = sorted(sales_count_by_menu.items(), key=lambda x: x[1], reverse=True)[:5]
    top_menus_data = []
    for menu_id, qty in top_menus:
        menu = MenuItem.query.get(menu_id)
        if menu:
            top_menus_data.append({"name": menu.name, "quantity": qty})

    # Marge par menu : prix de vente − coût des ingrédients (recette)
    margins = []
    for menu in MenuItem.active().all():
        cost = sum(ri.quantity_per_portion * ri.ingredient.unit_price for ri in menu.recipe_items)
        margin = menu.sale_price - cost
        margins.append({"name": menu.name, "sale_price": menu.sale_price, "cost": cost, "margin": margin})

    low_stock = [i for i in Ingredient.query.all() if i.is_low_stock()]
    funding_sources = FundingSource.query.all()

    # -----------------------------------------------------------------
    # BILAN RAPIDE : "suis-je en train de perdre de l'argent, ou pas ?"
    # Réponse en un coup d'œil, sans avoir à faire un inventaire complet.
    # -----------------------------------------------------------------
    today_start = local_today_start_utc()
    # Début de la semaine en cours (lundi, heure de Madagascar)
    current_week_start = today_start - timedelta(days=now_local().weekday())

    weekly_summary = []
    for i in range(7, -1, -1):  # 8 dernières semaines, de la plus ancienne à la plus récente
        week_start = current_week_start - timedelta(weeks=i)
        week_end = week_start + timedelta(days=7)

        week_ventes = sum(
            s.total for s in all_sales
            if s.created_at and week_start <= s.created_at < week_end
        )
        week_achats = sum(
            p.total for p in all_purchases
            if p.date and week_start <= p.date < week_end
        )
        week_depenses = sum(
            e.amount for e in all_expenses
            if e.date and week_start <= e.date < week_end
        )
        week_total_depenses = week_achats + week_depenses
        week_resultat = week_ventes - week_total_depenses

        ws_local = week_start + (now_local() - now)
        weekly_summary.append({
            "label": f"{ws_local.strftime('%d/%m')} au {(ws_local + timedelta(days=6)).strftime('%d/%m')}",
            "is_current": i == 0,
            "ventes": week_ventes,
            "depenses": week_total_depenses,
            "resultat": week_resultat,
            "en_perte": week_resultat < 0,
            "a_des_donnees": week_ventes > 0 or week_total_depenses > 0,
        })

    bilan_semaine = weekly_summary[-1]  # semaine en cours

    # -----------------------------------------------------------------
    # RÉSUMÉ PAR MOIS (calendaire) — 6 derniers mois
    # -----------------------------------------------------------------
    monthly_summary = []
    nl = now_local()
    month_cursor_year, month_cursor_month = nl.year, nl.month
    months_list = []
    for i in range(6):
        months_list.append((month_cursor_year, month_cursor_month))
        month_cursor_month -= 1
        if month_cursor_month == 0:
            month_cursor_month = 12
            month_cursor_year -= 1
    months_list.reverse()  # du plus ancien au plus récent

    for year, month in months_list:
        month_start = local_to_utc(datetime(year, month, 1))
        if month == 12:
            month_end = local_to_utc(datetime(year + 1, 1, 1))
        else:
            month_end = local_to_utc(datetime(year, month + 1, 1))

        month_ventes = sum(
            s.total for s in all_sales
            if s.created_at and month_start <= s.created_at < month_end
        )
        month_achats = sum(
            p.total for p in all_purchases
            if p.date and month_start <= p.date < month_end
        )
        month_exp_list = [e for e in all_expenses if e.date and month_start <= e.date < month_end]
        month_depenses = sum(e.amount for e in month_exp_list)
        month_fixes = sum(e.amount for e in month_exp_list if e.expense_type == "fixe")
        month_total_depenses = month_achats + month_depenses
        month_resultat = month_ventes - month_total_depenses

        monthly_summary.append({
            "label": f"{FRENCH_MONTHS[month]} {year}",
            "is_current": (year == nl.year and month == nl.month),
            "achats": month_achats,
            "fixes": month_fixes,
            "variables": month_depenses - month_fixes,
            "ventes": month_ventes,
            "depenses": month_total_depenses,
            "resultat": month_resultat,
            "en_perte": month_resultat < 0,
            "a_des_donnees": month_ventes > 0 or month_total_depenses > 0,
        })

    bilan_mois = monthly_summary[-1]  # mois en cours

    return render_template(
        "reports.html",
        total_revenue=total_revenue,
        revenue_30d=revenue_30d,
        total_spent=total_spent,
        total_sales_count=len(all_sales),
        top_menus=top_menus_data,
        margins=margins,
        low_stock=low_stock,
        funding_sources=funding_sources,
        bilan_semaine=bilan_semaine,
        weekly_summary=weekly_summary,
        bilan_mois=bilan_mois,
        monthly_summary=monthly_summary,
    )
