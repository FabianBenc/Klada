from flask import Flask, render_template, request, redirect, session
import requests
import sqlite3
from datetime import datetime
import threading
import time
import os
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change in production

API_URL = "https://api.psk.hr/betslip-history/v2/detail"
DB_NAME = "database.db"

PLAYER_NAMES = {
    1: "Jegulja",
    2: "Alexandar",
    3: "Mama",
    4: "Kiki",
    5: "Livro",
    6: "Broncani"
}

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE,
            ticket_number TEXT,
            created_at TEXT,
            last_updated TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT,
            player INTEGER,
            fixture_name TEXT,
            odds REAL,
            result TEXT
        )
    """)

    conn.commit()
    conn.close()

def extract_ticket_id(input_value):
    """
    Accepts either:
    - full PSK URL
    - raw ticket ID
    """
    try:
        parsed = urlparse(input_value)
        query = parse_qs(parsed.query)

        if "id" in query:
            return query["id"][0]

        return input_value
    except:
        return input_value


def fetch_data(ticket_input):
    ticket_id = extract_ticket_id(ticket_input)

    params = {
        "id": ticket_id,
        "source": "SB"
    }

    try:
        res = requests.get(API_URL, params=params)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print("API error:", e)
        return None

def save_ticket(ticket_number, data):
    if not data:
        return

    ticket_id = data.get("id")
    number = data.get("number")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT id FROM tickets WHERE ticket_id=?", (ticket_id,))
    if c.fetchone():
        conn.close()
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute("""
        INSERT INTO tickets (ticket_id, ticket_number, created_at, last_updated)
        VALUES (?, ?, ?, ?)
    """, (ticket_id, number, now, now))

    legs = data.get("legs", [])
    total_legs = len(legs)

    if total_legs == 6:
        legs_per_player = 1
    elif total_legs == 12:
        legs_per_player = 2
    else:
        legs_per_player = max(1, total_legs // len(PLAYER_NAMES))

    for index, leg in enumerate(legs):
        player = (index // legs_per_player) + 1
        if player > len(PLAYER_NAMES):
            player = len(PLAYER_NAMES)

        c.execute("""
            INSERT INTO bets (ticket_id, player, fixture_name, odds, result)
            VALUES (?, ?, ?, ?, ?)
        """, (
            ticket_id,
            player,
            leg.get("fixtureName"),
            leg.get("oddsPlaced"),
            leg.get("result")
        ))

    conn.commit()
    conn.close()

def update_ticket_results():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        SELECT DISTINCT t.ticket_id
        FROM tickets t
        JOIN bets b ON t.ticket_id = b.ticket_id
        WHERE b.result IS NULL OR b.result = 'PENDING' OR b.result = 'UNKNOWN'
        ORDER BY t.id DESC
        LIMIT 2
    """)
    tickets = c.fetchall()

    for (ticket_id,) in tickets:
        data = fetch_data(ticket_id)
        if not data:
            continue

        for leg in data.get("legs", []):
            c.execute("""
                UPDATE bets
                SET result=?
                WHERE ticket_id=? AND fixture_name=?
            """, (leg.get("result"), ticket_id, leg.get("fixtureName")))

        c.execute("""
            UPDATE tickets SET last_updated=?
            WHERE ticket_id=?
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ticket_id))

    conn.commit()
    conn.close()


def auto_update():
    while True:
        update_ticket_results()
        time.sleep(86400)  # once per day

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect("/")
        else:
            return render_template("login.html", error="Invalid credentials")

    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect("/")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if not session.get("admin_logged_in"):
            return "Unauthorized", 403

        ticket_number = request.form.get("ticket_number").strip()

        data = fetch_data(ticket_number)
        save_ticket(ticket_number, data)

        return redirect("/")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        SELECT ticket_id, ticket_number, created_at, last_updated
        FROM tickets
        ORDER BY id DESC
    """)
    tickets = c.fetchall()

    c.execute("""
        SELECT ticket_id, player, fixture_name, odds, result
        FROM bets
        ORDER BY ticket_id, player
    """)
    bets = c.fetchall()

    conn.close()

    return render_template(
        "index.html",
        tickets=tickets,
        bets=bets,
        player_names=PLAYER_NAMES,
        admin_logged_in=session.get("admin_logged_in")
    )

@app.route("/leaderboard")
def leaderboard():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    leaderboard_data = []

    for player_id, name in PLAYER_NAMES.items():
        c.execute("SELECT COUNT(*) FROM bets WHERE player=?", (player_id,))
        total = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM bets WHERE player=? AND (result='WINNING' OR result='VOIDED')", (player_id,))
        guessed = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM bets WHERE player=? AND result='LOSING'", (player_id,))
        missed = c.fetchone()[0]

        c.execute("SELECT AVG(odds) FROM bets WHERE player=?", (player_id,))
        avg_odds = c.fetchone()[0]

        c.execute("SELECT MAX(odds) FROM bets WHERE player=? AND (result='WINNING' OR result='VOIDED')", (player_id,))
        max_win = c.fetchone()[0]

        win_rate = (guessed / total * 100) if total > 0 else 0

        leaderboard_data.append({
            "name": name,
            "win_rate": round(win_rate, 2),
            "avg_odds": round(avg_odds, 2) if avg_odds else 0,
            "max_win": max_win if max_win else 0,
            "guessed": guessed,
            "missed": missed
        })

    conn.close()

    leaderboard_data.sort(
        key=lambda x: (x["win_rate"], x["avg_odds"]),
        reverse=True
    )

    return render_template("leaderboard.html", data=leaderboard_data)

@app.route('/update')
def update():
    if not session.get('admin_logged_in'):
        return redirect('/')
    return render_template('update.html')


@app.route("/delete_ticket/<ticket_id>", methods=["POST"])
def delete_ticket(ticket_id):
    if not session.get("admin_logged_in"):
        return "Unauthorized", 403

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("DELETE FROM bets WHERE ticket_id=?", (ticket_id,))
    c.execute("DELETE FROM tickets WHERE ticket_id=?", (ticket_id,))

    conn.commit()
    conn.close()

    return redirect("/")

if __name__ == "__main__":
    init_db()

    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=auto_update, daemon=True).start()

    app.run(debug=True)