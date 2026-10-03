from extensions import db
from models import User, ROLE_SUPER_ADMIN


def ensure_super_admin(app):
    """Crée le compte Super-Admin par défaut au premier lancement
    (cahier des charges section 4.1). À changer dès la première connexion !"""

    existing = User.query.filter_by(role=ROLE_SUPER_ADMIN).first()
    if existing:
        return

    username = app.config["SUPER_ADMIN_USERNAME"]
    password = app.config["SUPER_ADMIN_PASSWORD"]

    super_admin = User(
        username=username,
        role=ROLE_SUPER_ADMIN,
        must_change_password=True,
    )
    super_admin.set_password(password)
    db.session.add(super_admin)
    db.session.commit()
    print(
        f"[seed] Compte Super-Admin créé : {username} / {password} "
        "— à changer immédiatement lors de la première connexion !"
    )
