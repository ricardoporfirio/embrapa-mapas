from src.controllers.auth import bp_auth
from flask import request, session, redirect, url_for, flash
import pyrebase
import os

# Configuração do Firebase
firebaseConfig = {
    "apiKey": "AIzaSyAsdlwLzDlfBZ_l50gYPDgYHNkhjJFBBkA",
    "authDomain": "sistema-embrapa.firebaseapp.com",
    "projectId": "sistema-embrapa",
    "storageBucket": "sistema-embrapa.appspot.com",  # corrigido
    "messagingSenderId": "1009585432219",
    "appId": "1:1009585432219:web:d4919f634ede3b6983883e",
    "measurementId": "G-Y1CM8NND46",
    "databaseURL": "https://sistema-embrapa.firebaseio.com/",
}

# Permite configurar outro projeto sem alterar o c?digo.
for key, env_name in {"apiKey": "FIREBASE_API_KEY", "authDomain": "FIREBASE_AUTH_DOMAIN", "databaseURL": "FIREBASE_DATABASE_URL", "projectId": "FIREBASE_PROJECT_ID"}.items():
    firebaseConfig[key] = os.getenv(env_name, firebaseConfig[key])


def get_auth():
    return pyrebase.initialize_app(firebaseConfig).auth()


def get_user_name_by_email(email: str):
    """
    Retorna apenas o nome do usuário
    """
    user_map = {
        "ricardo.porfirio@gmail.com": "Ricardo Tristão Porfirio",
        "ricardo.andrade@embrapa.br": "Ricardo Guimarães Andrade",
        "marcos.hott@embrapa.br": "Marcos Cicarini Hott",
        "vanessa.magalhaes@embrapa.br": "Vanessa Maia Aguiar de Magalhães",
        "glauco.carvalho@embrapa.br": "Glauco Rodrigues Carvalho",
        "walter.magalhaes@embrapa.br": "Walter Coelho Pereira de Magalhães Junior",
        "maria.carneiro@embrapa.br": "Maria Izabel Carneiro Ferreira",
    }
    return user_map.get(email)


@bp_auth.route("/", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    try:
        # Autentica no Firebase
        user = get_auth().sign_in_with_email_and_password(email, password)

        # Busca nome amigável do usuário
        name = get_user_name_by_email(email) or email

        # Armazena na sessão
        session.clear()
        session["user"] = {
            "id": user["localId"],
            "email": email,
            "name": name,
        }
        session.permanent = True

        flash("Login realizado com sucesso!", "success")
        return redirect(url_for("setup.index"))

    except Exception:
        flash("Usuário ou senha inválidos.", "error")
        return redirect(url_for("home.login"))


@bp_auth.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Você saiu da sessão.", "info")
    return redirect(url_for("home.index"))
