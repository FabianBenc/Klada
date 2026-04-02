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
    6: "Joza.",
}

TICKET_NAMES = {
    #Ako neko vec nabo igrav samo tu ga zbrisem
    1: "Jegulja",
    2: "Alexandar",
    3: "Mama",
    4: "Kiki",
    5: "Livro",
    6: "Joza.",
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


    c.execute("PRAGMA table_info(tickets)")
    columns = [row[1] for row in c.fetchall()]

    if "ticket_jwt" not in columns:
        c.execute("ALTER TABLE tickets ADD COLUMN ticket_jwt TEXT")

    if "ticket_result" not in columns:
        c.execute("ALTER TABLE tickets ADD COLUMN ticket_result TEXT")

    c.execute("""
        CREATE TABLE IF NOT EXISTS loss_streaks (
            player INTEGER PRIMARY KEY,
            streak INTEGER DEFAULT 0
        )
    """)

    # Ensure every player has a row
    for player_id in PLAYER_NAMES:
        c.execute("INSERT OR IGNORE INTO loss_streaks (player, streak) VALUES (?, 0)", (player_id,))

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


def fetch_data(ticket_id):
    

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

def normalize_result(api_result):
    """
    Maps raw PSK API result strings to one of three display states:
    WINNING / WINNING_VOIDED / VOIDED  → 'WINNING'
    LOSING                              → 'LOSING'
    anything else (None, PENDING, etc.) → 'PENDING'
    """
    if api_result in ("WINNING", "WINNING_VOIDED", "VOIDED"):
        return "WINNING"
    if api_result == "LOSING":
        return "LOSING"
    return "PENDING"


def ticket_overall_status(bets_results):
    """
    Derives ticket-level status from a list of normalised bet results.
    - Any PENDING  → ticket is PENDING
    - All WINNING  → ticket is WINNING
    - Any LOSING   → ticket is LOSING
    """
    normalised = [normalize_result(r) for r in bets_results]
    if any(r == "PENDING" for r in normalised):
        return "PENDING"
    if any(r == "LOSING" for r in normalised):
        return "LOSING"
    return "WINNING"


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
        INSERT INTO tickets (ticket_id, ticket_number, created_at, last_updated, ticket_jwt, ticket_result)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (ticket_id, number, now, now, ticket_number, data.get("result")))

    legs = data.get("legs", [])
    total_legs = len(legs)

    if total_legs == len(TICKET_NAMES):
        legs_per_player = 1
    elif total_legs == (len(TICKET_NAMES) * 2):
        legs_per_player = 2
    else:
        legs_per_player = max(1, total_legs // len(TICKET_NAMES))

    for index, leg in enumerate(legs):
        player = (index // legs_per_player) + 1
        if player > len(TICKET_NAMES):
            player = len(TICKET_NAMES)

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
    update_loss_streaks(ticket_id, conn)
    conn.close()

def update_loss_streaks(ticket_id, conn=None):
    """
    After a ticket's bets are saved/updated, recalculate loss streaks.
    A player's streak increases by 1 if ALL their legs on this ticket are LOSING.
    If their streak was already 3 (max), it resets to 0 before the new bet counts
    (the 4th bet resets the streak). A win/voided result resets the streak to 0.
    """
    close_conn = conn is None
    if close_conn:
        conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Get all players who have bets on this ticket
    c.execute("SELECT DISTINCT player FROM bets WHERE ticket_id=?", (ticket_id,))
    players = [row[0] for row in c.fetchall()]

    for player in players:
        c.execute("SELECT result FROM bets WHERE ticket_id=? AND player=?", (ticket_id, player))
        results = [row[0] for row in c.fetchall()]

        # Only update streak if all results are resolved (not NULL/PENDING/UNKNOWN)
        if not results or any(r in (None, "PENDING", "UNKNOWN") for r in results):
            continue

        all_losing = all(r == "LOSING" for r in results)

        c.execute("SELECT streak FROM loss_streaks WHERE player=?", (player,))
        row = c.fetchone()
        current_streak = row[0] if row else 0

        if all_losing:
            # If streak was at max (3), this 4th bet resets it to 1 (fresh streak starting)
            if current_streak >= 3:
                new_streak = 1
            else:
                new_streak = current_streak + 1
        else:
            # Win or voided — reset streak
            new_streak = 0

        c.execute("INSERT OR REPLACE INTO loss_streaks (player, streak) VALUES (?, ?)", (player, new_streak))

    if close_conn:
        conn.commit()
        conn.close()
    else:
        conn.commit()


def get_loss_streaks():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT player, streak FROM loss_streaks")
    streaks = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return streaks


def update_ticket_results():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        SELECT DISTINCT t.ticket_id, t.ticket_jwt
        FROM tickets t
        JOIN bets b ON t.ticket_id = b.ticket_id
        WHERE b.result IS NULL OR b.result = 'PENDING' OR b.result = 'UNKNOWN'
        ORDER BY t.id DESC
        LIMIT 2
    """)
    tickets = c.fetchall()
    for (ticket_id, ticket_jwt,) in tickets:
        data = fetch_data(ticket_jwt)
        if not data:
            continue

        for leg in data.get("legs", []):
            c.execute("""
                UPDATE bets
                SET result=?
                WHERE ticket_id=? AND fixture_name=?
            """, (leg.get("result"), ticket_id, leg.get("fixtureName")))

        c.execute("""
            UPDATE tickets SET last_updated=?, ticket_result=?
            WHERE ticket_id=?
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), data.get("result"), ticket_id))

        conn.commit()

    conn.commit()
    conn.close()
    recalculate_all_streaks()


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
        ticket_id = extract_ticket_id(ticket_number)
        print (ticket_id)

        data = fetch_data(ticket_id)
        save_ticket(ticket_id, data)

        return redirect("/")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        SELECT ticket_id, ticket_number, created_at, last_updated, ticket_result, ticket_jwt
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
        admin_logged_in=session.get("admin_logged_in"),
        loss_streaks=get_loss_streaks(),
        normalize_result=normalize_result
    )

@app.route("/pravila")
def pravila():
    return render_template("pravilaigre.html")


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
    else:
        update_ticket_results()
        return redirect("/")


def recalculate_all_streaks():
    """
    Fully recalculates loss streaks for all players from scratch,
    replaying tickets in chronological order. Used after a ticket is deleted.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Reset all streaks
    for player_id in PLAYER_NAMES:
        c.execute("INSERT OR REPLACE INTO loss_streaks (player, streak) VALUES (?, 0)", (player_id,))

    # Replay tickets oldest-first
    c.execute("SELECT ticket_id FROM tickets ORDER BY id ASC")
    ticket_ids = [row[0] for row in c.fetchall()]

    streaks = {player_id: 0 for player_id in PLAYER_NAMES}

    for ticket_id in ticket_ids:
        c.execute("SELECT DISTINCT player FROM bets WHERE ticket_id=?", (ticket_id,))
        players = [row[0] for row in c.fetchall()]

        for player in players:
            c.execute("SELECT result FROM bets WHERE ticket_id=? AND player=?", (ticket_id, player))
            results = [row[0] for row in c.fetchall()]

            if not results or any(r in (None, "PENDING", "UNKNOWN") for r in results):
                continue

            all_losing = all(r == "LOSING" for r in results)

            if all_losing:
                if streaks[player] >= 3:
                    streaks[player] = 1
                else:
                    streaks[player] += 1
            else:
                streaks[player] = 0

    for player_id, streak in streaks.items():
        c.execute("INSERT OR REPLACE INTO loss_streaks (player, streak) VALUES (?, ?)", (player_id, streak))

    conn.commit()
    conn.close()


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

    recalculate_all_streaks()

    return redirect("/")

if __name__ == "__main__":
    init_db()

    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=auto_update, daemon=True).start()

    app.run(debug=True)