from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(db.func.lower(User.username) == username.lower()).first()

        if user is None:
            flash("Nom d'utilisateur ou mot de passe incorrect.", "danger")
            return render_template("login.html")

        if not user.is_active:
            flash("Ce compte a été désactivé. Veuillez contacter votre administrateur.", "danger")
            return render_template("login.html")

        if user.is_locked():
            flash(
                "Compte temporairement bloqué suite à plusieurs tentatives infructueuses. "
                "Veuillez patienter puis réessayer.",
                "danger",
            )
            return render_template("login.html")

        if not user.check_password(password):
            user.register_failed_login(
                current_app.config["MAX_LOGIN_ATTEMPTS"],
                current_app.config["LOGIN_LOCKOUT_MINUTES"],
            )
            db.session.commit()
            flash("Nom d'utilisateur ou mot de passe incorrect.", "danger")
            return render_template("login.html")

        user.register_successful_login()
        db.session.commit()
        login_user(user)

        if user.must_change_password:
            flash(
                "Première connexion : vous devez changer votre mot de passe avant de continuer.",
                "warning",
            )
            return redirect(url_for("auth.change_password"))

        return redirect(url_for("main.home"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Déconnecté avec succès.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Section 4.2 : changement obligatoire du mot de passe à la 1ère connexion,
    et endroit où l'utilisateur renseigne email + question secrète."""

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        email = request.form.get("email", "").strip()
        secret_question = request.form.get("secret_question", "").strip()
        secret_answer = request.form.get("secret_answer", "").strip()

        if not current_user.check_password(current_password):
            flash("Mot de passe actuel incorrect.", "danger")
            return render_template("change_password.html")

        if len(new_password) < 8:
            flash("Le nouveau mot de passe doit contenir au moins 8 caractères.", "danger")
            return render_template("change_password.html")

        if new_password != confirm_password:
            flash("Les deux mots de passe ne correspondent pas.", "danger")
            return render_template("change_password.html")

        current_user.set_password(new_password)
        current_user.must_change_password = False

        if email:
            current_user.email = email
        if secret_question and secret_answer:
            current_user.secret_question = secret_question
            current_user.set_secret_answer(secret_answer)

        db.session.commit()
        flash("Mot de passe modifié avec succès !", "success")
        return redirect(url_for("main.home"))

    return render_template("change_password.html")


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Section 4.3 : réinitialisation via question secrète (démo sans envoi d'email réel)."""

    step = request.form.get("step", "find_user")
    user = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        user = User.query.filter(db.func.lower(User.username) == username.lower()).first()

        if step == "find_user":
            if user is None or not user.secret_question:
                flash(
                    "Compte introuvable, ou question secrète non définie. "
                    "Veuillez contacter le Super-Admin.",
                    "danger",
                )
                return render_template("forgot_password.html")
            return render_template("forgot_password.html", user=user, step="answer")

        if step == "answer":
            answer = request.form.get("secret_answer", "")
            new_password = request.form.get("new_password", "")
            if user and user.check_secret_answer(answer):
                if len(new_password) < 8:
                    flash("Le nouveau mot de passe doit contenir au moins 8 caractères.", "danger")
                    return render_template("forgot_password.html", user=user, step="answer")
                user.set_password(new_password)
                user.must_change_password = False
                db.session.commit()
                flash("Mot de passe modifié ! Vous pouvez maintenant vous connecter.", "success")
                return redirect(url_for("auth.login"))
            flash("Réponse incorrecte. Veuillez contacter le Super-Admin.", "danger")

    return render_template("forgot_password.html")
