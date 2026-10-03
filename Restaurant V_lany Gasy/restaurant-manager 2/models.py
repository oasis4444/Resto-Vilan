from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db

# ---------------------------------------------------------------------------
# Rôles disponibles (cahier des charges section 3)
# ---------------------------------------------------------------------------
ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_STOCK_MANAGER = "stock_manager"
ROLE_SERVER = "server"
ROLE_CASHIER = "cashier"
ROLE_ACCOUNTANT = "accountant"

ROLES = [
    (ROLE_SUPER_ADMIN, "Super-Admin"),
    (ROLE_ADMIN, "Admin (Propriétaire)"),
    (ROLE_STOCK_MANAGER, "Gérant"),
    (ROLE_SERVER, "Serveur"),
    (ROLE_CASHIER, "Caissier"),
    (ROLE_ACCOUNTANT, "Comptable"),
]

def role_labels():
    """{code_role: libellé} en tenant compte des noms personnalisés
    enregistrés dans Paramètres (ex : admin → « Patron »)."""
    labels = dict(ROLES)
    try:
        custom = Settings.get().custom_role_labels()
        for key, value in custom.items():
            if key in labels and value:
                labels[key] = value
    except Exception:
        pass
    return labels


def role_choices():
    """Liste [(code, libellé)] pour les listes déroulantes."""
    labels = role_labels()
    return [(code, labels[code]) for code, _ in ROLES]


# Rôles autorisés à ajouter des utilisateurs (règle du cahier des charges 3)
ROLES_CAN_MANAGE_USERS = {ROLE_SUPER_ADMIN, ROLE_ADMIN}


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default=ROLE_SERVER)

    email = db.Column(db.String(255), nullable=True)
    secret_question = db.Column(db.String(255), nullable=True)
    secret_answer_hash = db.Column(db.String(255), nullable=True)

    # Section 4.2 : l'utilisateur DOIT changer son mot de passe à la 1ère connexion
    must_change_password = db.Column(db.Boolean, default=True, nullable=False)
    # Section 4.5 : sécurité anti brute-force
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def set_secret_answer(self, raw_answer):
        self.secret_answer_hash = generate_password_hash(raw_answer.strip().lower())

    def check_secret_answer(self, raw_answer):
        if not self.secret_answer_hash:
            return False
        return check_password_hash(self.secret_answer_hash, raw_answer.strip().lower())

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > datetime.utcnow())

    def register_failed_login(self, max_attempts, lockout_minutes):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = datetime.utcnow() + timedelta(minutes=lockout_minutes)
            self.failed_login_attempts = 0

    def register_successful_login(self):
        self.failed_login_attempts = 0
        self.locked_until = None

    def role_label(self):
        """Libellé du rôle — personnalisable dans Paramètres (ex : « Patron »)."""
        return role_labels().get(self.role, self.role)

    def can_manage_users(self):
        return self.role in ROLES_CAN_MANAGE_USERS

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Ingredient(db.Model):
    """Stock d'ingrédients (matière première) — section 2.5"""

    __tablename__ = "ingredients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    # Code court (mot-clé) : Poulet → PLT, Yaourt → YRT... utilisable dans la
    # recherche, les recettes, et les fichiers Excel à la place du nom complet.
    code = db.Column(db.String(10), nullable=True, index=True)
    category = db.Column(db.String(100), nullable=True)
    unit = db.Column(db.String(20), nullable=False, default="pièce")  # kg, l, pièce...
    stock_quantity = db.Column(db.Float, nullable=False, default=0)
    alert_threshold = db.Column(db.Float, nullable=False, default=0)
    unit_price = db.Column(db.Float, nullable=False, default=0)

    def is_low_stock(self):
        return self.stock_quantity <= self.alert_threshold

    @property
    def label(self):
        """« [PLT] Poulet » — affichage court + nom."""
        return f"[{self.code}] {self.name}" if self.code else self.name


class StockAdjustment(db.Model):
    """Journal de TOUTE modification manuelle du stock — qui, quand, avant/après,
    et pourquoi. C'est ce qui permet au propriétaire de vérifier à distance
    (depuis chez lui) qu'aucune quantité n'a été changée sans trace, et donc de
    repérer un vol ou une erreur non signalée."""

    __tablename__ = "stock_adjustments"

    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    old_quantity = db.Column(db.Float, nullable=False)
    new_quantity = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

    ingredient = db.relationship("Ingredient")
    changed_by = db.relationship("User")

    @property
    def difference(self):
        return self.new_quantity - self.old_quantity


class MenuItem(db.Model):
    """Plat / menu proposé aux clients — section 2.3"""

    __tablename__ = "menu_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=True)  # entrée, plat, dessert, boisson
    sale_price = db.Column(db.Float, nullable=False, default=0)
    available = db.Column(db.Boolean, default=True, nullable=False)
    photo_filename = db.Column(db.String(255), nullable=True)
    # « Supprimé » alors qu'il a déjà été vendu : on le cache partout, mais on
    # le garde dans la base pour ne pas casser l'historique des ventes.
    is_archived = db.Column(db.Boolean, default=False, nullable=False)

    @classmethod
    def active(cls):
        """Menus visibles (non supprimés)."""
        return cls.query.filter(cls.is_archived.is_(False))

    recipe_items = db.relationship(
        "RecipeItem", backref="menu_item", cascade="all, delete-orphan"
    )

    def is_really_available(self):
        """Disponible = marqué dispo ET tous les ingrédients de la recette en stock."""
        if not self.available:
            return False
        for item in self.recipe_items:
            if item.ingredient.stock_quantity < item.quantity_per_portion:
                return False
        return True


class RecipeItem(db.Model):
    """Ligne de recette : quel ingrédient, quelle quantité, pour quel menu — section 2.3"""

    __tablename__ = "recipe_items"

    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    quantity_per_portion = db.Column(db.Float, nullable=False, default=0)

    ingredient = db.relationship("Ingredient")


# ---------------------------------------------------------------------------
# VENTE / CAISSE — section 2.4 et 7
# ---------------------------------------------------------------------------
PAYMENT_METHODS = ["Espèces", "Mvola", "Orange Money", "Airtel Money", "Carte bancaire"]


class Sale(db.Model):
    """Une vente / commande — section 2.4"""

    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    table_number = db.Column(db.String(20), nullable=True)
    client_name = db.Column(db.String(150), nullable=True)
    payment_method = db.Column(db.String(30), nullable=False, default="Espèces")
    total = db.Column(db.Float, nullable=False, default=0)
    server_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    server = db.relationship("User")
    items = db.relationship("SaleItem", backref="sale", cascade="all, delete-orphan")

    def receipt_number(self):
        return f"V-{self.id:06d}"

    def invoice_number(self):
        return f"F-{self.id:06d}"


class SaleItem(db.Model):
    """Une ligne de vente (un menu vendu, avec sa quantité) — section 2.4"""

    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False, default=0)

    menu_item = db.relationship("MenuItem")

    @property
    def line_total(self):
        return self.quantity * self.unit_price


# ---------------------------------------------------------------------------
# SOURCE DE FINANCEMENT / CAISSE — section 2.2
# ---------------------------------------------------------------------------
class FundingSource(db.Model):
    """Une caisse / source de financement (Patron, Vente, Autre) — section 2.2"""

    __tablename__ = "funding_sources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    initial_balance = db.Column(db.Float, nullable=False, default=0)

    def balance(self):
        """Solde = apport initial − total des achats − total des dépenses générales
        attribués à cette source (les achats/dépenses annulés ne comptent pas)."""
        purchases_total = sum(p.total for p in self.purchases if not p.is_cancelled)
        expenses_total = sum(e.amount for e in self.expenses if not e.is_cancelled)
        return self.initial_balance - purchases_total - expenses_total


# ---------------------------------------------------------------------------
# ACHAT — section 2.1
# ---------------------------------------------------------------------------
class Purchase(db.Model):
    """Un achat d'ingrédient — section 2.1"""

    __tablename__ = "purchases"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=0)
    unit_price = db.Column(db.Float, nullable=False, default=0)
    supplier = db.Column(db.String(150), nullable=True)
    funding_source_id = db.Column(db.Integer, db.ForeignKey("funding_sources.id"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Annulation (pas de suppression réelle, pour garder la traçabilité)
    is_cancelled = db.Column(db.Boolean, default=False, nullable=False)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    cancel_reason = db.Column(db.String(255), nullable=True)

    ingredient = db.relationship("Ingredient", foreign_keys=[ingredient_id])
    funding_source = db.relationship("FundingSource", backref="purchases")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    cancelled_by = db.relationship("User", foreign_keys=[cancelled_by_id])

    @property
    def total(self):
        return self.quantity * self.unit_price


# ---------------------------------------------------------------------------
# DÉPENSES GÉNÉRALES — électricité, eau, loyer, salaires, etc.
# (distinctes des Achats, qui sont toujours liés à un ingrédient)
# ---------------------------------------------------------------------------
EXPENSE_CATEGORIES = [
    "Électricité (JIRAMA)",
    "Eau (JIRAMA)",
    "Loyer",
    "Salaires",
    "Internet / Téléphone",
    "Entretien / Réparation",
    "Transport",
    "Autre",
]

# Dépenses FIXES : reviennent chaque mois, montant stable (loyer, salaires...)
FIXED_EXPENSE_CATEGORIES = [
    "Loyer",
    "Salaires",
    "Électricité (JIRAMA)",
    "Eau (JIRAMA)",
    "Internet / Téléphone",
    "Abonnement",
    "Assurance",
    "Impôts / Taxes",
    "Autre",
]

# Dépenses VARIABLES : changent tout le temps (menaka, cure-dents, imprévus...)
VARIABLE_EXPENSE_CATEGORIES = [
    "Huile (menaka)",
    "Gaz / Charbon",
    "Cure-dents / Serviettes",
    "Produits d'entretien",
    "Emballages",
    "Légumes / Marché",
    "Transport",
    "Entretien / Réparation",
    "Imprévu",
    "Autre",
]

EXPENSE_TYPE_FIXED = "fixe"
EXPENSE_TYPE_VARIABLE = "variable"


class FixedExpense(db.Model):
    """Modèle de dépense FIXE (ex : Loyer 500 000 Ar / mois, Salaire Rabe...).
    Ce n'est pas une dépense en soi : c'est la « ligne prévue » chaque mois.
    Quand on la paie, une vraie Expense (type « fixe ») est créée et liée ici.
    Seuls Admin et Super-Admin peuvent créer/modifier ces lignes."""

    __tablename__ = "fixed_expenses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=False, default="Autre")
    amount = db.Column(db.Float, nullable=False, default=0)  # montant mensuel prévu
    due_day = db.Column(db.Integer, nullable=True)  # jour d'échéance (1-31), optionnel
    funding_source_id = db.Column(db.Integer, db.ForeignKey("funding_sources.id"), nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    funding_source = db.relationship("FundingSource")
    updated_by = db.relationship("User")

    def payments_for(self, period):
        """Paiements (non annulés) pour un mois donné, période = 'AAAA-MM'."""
        return [
            e for e in self.payments
            if e.period == period and not e.is_cancelled
        ]

    def paid_amount(self, period):
        return sum(e.amount for e in self.payments_for(period))


class Expense(db.Model):
    """Dépense générale (hors achat d'ingrédient) — section 2.2."""

    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(100), nullable=False, default="Autre")
    description = db.Column(db.String(255), nullable=True)
    amount = db.Column(db.Float, nullable=False, default=0)
    funding_source_id = db.Column(db.Integer, db.ForeignKey("funding_sources.id"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Fixe (loyer, salaires...) ou variable (huile, cure-dents, imprévus...)
    expense_type = db.Column(db.String(20), nullable=False, default=EXPENSE_TYPE_VARIABLE)
    # Pour une dépense fixe : quelle ligne fixe est payée, et pour quel mois (AAAA-MM)
    fixed_expense_id = db.Column(db.Integer, db.ForeignKey("fixed_expenses.id"), nullable=True)
    period = db.Column(db.String(7), nullable=True)

    # Annulation (pas de suppression réelle, pour garder la traçabilité)
    is_cancelled = db.Column(db.Boolean, default=False, nullable=False)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    cancel_reason = db.Column(db.String(255), nullable=True)

    fixed_expense = db.relationship("FixedExpense", backref="payments")

    @property
    def is_fixed(self):
        return self.expense_type == EXPENSE_TYPE_FIXED

    funding_source = db.relationship("FundingSource", backref="expenses")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    cancelled_by = db.relationship("User", foreign_keys=[cancelled_by_id])


# ---------------------------------------------------------------------------
# PARAMÈTRES DU RESTAURANT — identité (nom, logo, coordonnées) pour le design
# "premium" et la facture officielle
# ---------------------------------------------------------------------------
class Settings(db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_name = db.Column(db.String(150), nullable=False, default="Restaurant Manager")
    address = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    nif = db.Column(db.String(50), nullable=True)
    stat = db.Column(db.String(50), nullable=True)
    logo_filename = db.Column(db.String(255), nullable=True)
    primary_color = db.Column(db.String(20), nullable=False, default="#1863d6")

    # Ticket de caisse : UN seul message de remerciement (modifiable)
    receipt_message = db.Column(db.String(255), nullable=True)
    # Largeur du papier de l'imprimante thermique : "58" ou "80" (mm)
    receipt_width = db.Column(db.String(5), nullable=True, default="80")
    # Noms des rôles personnalisés, en JSON : {"admin": "Patron", "server": "Serveur"}
    role_labels_json = db.Column(db.Text, nullable=True)
    # Ouvrir automatiquement l'impression du ticket juste après une vente
    auto_print_receipt = db.Column(db.Boolean, nullable=True, default=False)

    DEFAULT_RECEIPT_MESSAGE = "Misaotra betsaka ! Mandrosoa indray."

    def receipt_message_or_default(self):
        return (self.receipt_message or "").strip() or self.DEFAULT_RECEIPT_MESSAGE

    def receipt_width_mm(self):
        return 58 if str(self.receipt_width or "80") == "58" else 80

    def custom_role_labels(self):
        import json
        try:
            data = json.loads(self.role_labels_json or "{}")
            return {k: str(v).strip() for k, v in data.items() if str(v).strip()}
        except (ValueError, TypeError):
            return {}

    @classmethod
    def get(cls):
        """Retourne l'unique ligne de paramètres, la crée si elle n'existe pas encore."""
        settings = cls.query.first()
        if settings is None:
            settings = cls()
            db.session.add(settings)
            db.session.commit()
        return settings
