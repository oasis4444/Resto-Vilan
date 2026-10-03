from flask import Flask

from config import Config
from extensions import db, login_manager
from models import User


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_settings():
        from models import Settings
        try:
            return {"settings": Settings.get()}
        except Exception:
            return {"settings": None}

    @app.context_processor
    def inject_helpers():
        from models import role_choices

        def restaurant_logo_url():
            """Logo du restaurant : celui importé dans Paramètres, sinon le logo
            V'lany Gasy fourni avec le logiciel."""
            import os
            from flask import url_for
            from models import Settings
            try:
                s = Settings.get()
                if s.logo_filename and os.path.isfile(
                    os.path.join(app.root_path, "static", "uploads", s.logo_filename)
                ):
                    return url_for("static", filename="uploads/" + s.logo_filename)
            except Exception:
                pass
            return url_for("static", filename="images/restaurant-logo.png")

        return {"restaurant_logo_url": restaurant_logo_url, "role_choices": role_choices}

    # Affichage des dates en heure de Madagascar (la base stocke en UTC)
    @app.template_filter("local")
    def local_dt(value, fmt="%d/%m/%Y %H:%M"):
        from utils import to_local
        if not value:
            return ""
        return to_local(value).strftime(fmt)

    # Montants : 12500 → « 12 500 »
    @app.template_filter("ar")
    def format_ar(value):
        try:
            return f"{float(value):,.0f}".replace(",", " ")
        except (TypeError, ValueError):
            return "0"

    @app.context_processor
    def inject_alerts():
        """Nombre d'ingrédients en alerte de stock — utilisé pour le badge de
        notification dans le header. Calculé une seule fois par requête."""
        from flask_login import current_user
        from models import Ingredient, ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STOCK_MANAGER

        try:
            if current_user.is_authenticated and current_user.role in (
                ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STOCK_MANAGER
            ):
                count = sum(1 for i in Ingredient.query.all() if i.is_low_stock())
            else:
                count = 0
        except Exception:
            count = 0
        return {"low_stock_alert_count": count}

    # Enregistrement des blueprints (routes)
    from auth import auth_bp
    from routes import main_bp
    from sales import sales_bp
    from purchases import purchases_bp
    from reports import reports_bp
    from excel_io import excel_bp
    from backup import backup_bp
    from settings_bp import settings_bp
    from expenses import expenses_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(excel_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(expenses_bp)

    # Création des tables + mise à jour des colonnes + Super-Admin par défaut
    with app.app_context():
        db.create_all()
        from migrations import ensure_schema, backfill_ingredient_codes

        ensure_schema()
        backfill_ingredient_codes()

        from seed import ensure_super_admin

        ensure_super_admin(app)

    return app


# Pour PythonAnywhere : la variable "app" doit être importable directement.
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
