from flask import Flask, render_template, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "super-secret-key"
DB = "database.db"

# ================= DATABASE =================
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with get_db() as db:
        c = db.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            elo INTEGER DEFAULT 1000,
            avatar TEXT DEFAULT 'https://via.placeholder.com/80'
        )
        """)
        db.commit()

init_db()

# ================= AUTH =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        if not u or not p:
            return render_template("login.html", message="Введіть логін і пароль")
        with get_db() as db:
            c = db.cursor()
            c.execute("SELECT password FROM users WHERE username=?", (u,))
            user = c.fetchone()
            if not user:
                c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                          (u, generate_password_hash(p)))
                db.commit()
                session["user"] = u
                return redirect("/")
            elif check_password_hash(user["password"], p):
                session["user"] = u
                return redirect("/")
            else:
                return render_template("login.html", message="Неправильний пароль")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ================= HOME =================
@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]
    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT elo, avatar FROM users WHERE username=?", (user,))
        row = c.fetchone()
        elo = row["elo"] if row else 1000
        avatar = row["avatar"] if row else 'https://via.placeholder.com/80'
    return render_template("index.html", username=user, elo=elo, avatar=avatar)

# ================= PROFILE =================
@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect("/login")
    user = session["user"]
    with get_db() as db:
        c = db.cursor()
        c.execute("SELECT elo, avatar FROM users WHERE username=?", (user,))
        row = c.fetchone()
        elo = row["elo"] if row else 1000
        avatar = row["avatar"] if row else 'https://via.placeholder.com/80'
    return render_template("profile.html", username=user, elo=elo, avatar=avatar)

# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
