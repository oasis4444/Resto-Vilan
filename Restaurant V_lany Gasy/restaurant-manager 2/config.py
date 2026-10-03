import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # ---------------------------------------------------------------------
    # Clé secrète Flask (sessions). En production, mettez une vraie valeur
    # secrète dans une variable d'environnement SECRET_KEY (voir README).
    # ---------------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-en-production")

    # ---------------------------------------------------------------------
    # Base de données : SQLite par défaut (simple pour démarrer).
    # Pour passer à MySQL plus tard (PythonAnywhere le propose), remplacez
    # SQLALCHEMY_DATABASE_URI par une variable d'environnement DATABASE_URL.
    # ---------------------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'restaurant.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ---------------------------------------------------------------------
    # Compte Super-Admin par défaut, créé automatiquement au premier
    # lancement (voir seed.py). À changer dès la première connexion !
    # ---------------------------------------------------------------------
    SUPER_ADMIN_USERNAME = os.environ.get("SUPER_ADMIN_USERNAME", "super-adm")
    SUPER_ADMIN_PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD", "Ampandrana")

    # Nombre de tentatives de connexion avant blocage temporaire (5.4/4.5)
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_LOCKOUT_MINUTES = 15
