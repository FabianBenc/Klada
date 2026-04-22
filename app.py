from flask import Flask, render_template, request, redirect, session, jsonify
import requests
import sqlite3
from datetime import datetime, timezone
import threading
import time
import os
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change in production

API_URL = "https://api.psk.hr/betslip-history/v2/detail"
DB_NAME = "database.db"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123"

# ---------------------------------------------------------------------------
# Helpers: load player dicts dynamically from DB
# ---------------------------------------------------------------------------

def get_player_names(conn=None):
    """Returns {player_id: name} for ALL players (active + inactive)."""
    close = conn is None
    if close:
        conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name FROM players ORDER BY id ASC")
    result = {row[0]: row[1] for row in c.fetchall()}
    if close:
        conn.close()
    return result


def get_active_player_names(conn=None):
    """Returns {player_id: name} for currently ACTIVE players only."""
    close = conn is None
    if close:
        conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name FROM players WHERE active=1 ORDER BY id ASC")
    result = {row[0]: row[1] for row in c.fetchall()}
    if close:
        conn.close()
    return result


def get_eligible_players_for_ticket(ticket_date_str, conn=None):
    """
    Returns {player_id: name} for players whose joined_at <= ticket date.
    ticket_date_str is the PSK-parsed created_at string, e.g. '2026-03-27 10:46'.
    This ensures newly added players are excluded from tickets that predate them,
    which matters when the DB is dropped and re-populated via komanda.sh.
    Only active players are considered.
    """
    close = conn is None
    if close:
        conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Compare as text — both are 'YYYY-MM-DD HH:MM' so lexicographic order is correct
    c.execute(
        "SELECT id, name FROM players WHERE active=1 AND joined_at <= ? ORDER BY id ASC",
        (ticket_date_str,)
    )
    result = {row[0]: row[1] for row in c.fetchall()}
    if close:
        conn.close()
    return result


def get_all_players_with_status(conn=None):
    """Returns list of dicts: {id, name, active, joined_at} for all players."""
    close = conn is None
    if close:
        conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, active, joined_at FROM players ORDER BY id ASC")
    result = [{"id": r[0], "name": r[1], "active": r[2], "joined_at": r[3]} for r in c.fetchall()]
    if close:
        conn.close()
    return result


# ---------------------------------------------------------------------------
# DB init
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # ── players table ────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL UNIQUE,
            active    INTEGER NOT NULL DEFAULT 1,
            joined_at TEXT NOT NULL DEFAULT '2000-01-01 00:00'
        )
    """)

    # Add joined_at to existing DBs that predate this column
    c.execute("PRAGMA table_info(players)")
    player_cols = [r[1] for r in c.fetchall()]
    if "joined_at" not in player_cols:
        c.execute("ALTER TABLE players ADD COLUMN joined_at TEXT NOT NULL DEFAULT '2000-01-01 00:00'")

    # Migrate old hardcoded players if table is empty
    c.execute("SELECT COUNT(*) FROM players")
    if c.fetchone()[0] == 0:
        # Founding players: joined_at = epoch so they appear on ALL tickets
        legacy = ["Jegulja", "Alexandar", "Mama", "Kiki", "Livro", "Joza."]
        for name in legacy:
            c.execute(
                "INSERT OR IGNORE INTO players (name, active, joined_at) VALUES (?, 1, '2000-01-01 00:00')",
                (name,)
            )

    # ── tickets table ────────────────────────────────────────────────────────
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
            result TEXT,
            start_time TEXT,
            score TEXT
        )
    """)

    # Migrate existing bets tables that predate start_time / score columns
    c.execute("PRAGMA table_info(bets)")
    bet_cols = [r[1] for r in c.fetchall()]
    if "start_time" not in bet_cols:
        c.execute("ALTER TABLE bets ADD COLUMN start_time TEXT")
    if "score" not in bet_cols:
        c.execute("ALTER TABLE bets ADD COLUMN score TEXT")

    c.execute("PRAGMA table_info(tickets)")
    columns = [row[1] for row in c.fetchall()]
    if "ticket_jwt" not in columns:
        c.execute("ALTER TABLE tickets ADD COLUMN ticket_jwt TEXT")
    if "ticket_result" not in columns:
        c.execute("ALTER TABLE tickets ADD COLUMN ticket_result TEXT")
    if "period_id" not in columns:
        c.execute("ALTER TABLE tickets ADD COLUMN period_id INTEGER REFERENCES periods(id)")
    if "payout" not in columns:
        c.execute("ALTER TABLE tickets ADD COLUMN payout REAL")

    # ── periods table ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS periods (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            start_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # ── ticket_players snapshot table ────────────────────────────────────────
    # Records which players were active when each ticket was created.
    # This preserves historical payment calculations even as the roster changes.
    c.execute("""
        CREATE TABLE IF NOT EXISTS ticket_players (
            ticket_id  TEXT NOT NULL,
            player_id  INTEGER NOT NULL,
            PRIMARY KEY (ticket_id, player_id)
        )
    """)

    # Backfill ticket_players for existing tickets that have no snapshot yet
    c.execute("SELECT ticket_id FROM tickets")
    all_ticket_ids = [r[0] for r in c.fetchall()]
    for tid in all_ticket_ids:
        c.execute("SELECT COUNT(*) FROM ticket_players WHERE ticket_id=?", (tid,))
        if c.fetchone()[0] == 0:
            c.execute("SELECT DISTINCT player FROM bets WHERE ticket_id=?", (tid,))
            for (pid,) in c.fetchall():
                c.execute("INSERT OR IGNORE INTO ticket_players (ticket_id, player_id) VALUES (?, ?)", (tid, pid))

    # ── streak tables ────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS loss_streaks (
            player INTEGER PRIMARY KEY,
            streak INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS win_streaks (
            player INTEGER PRIMARY KEY,
            streak INTEGER DEFAULT 0,
            max_streak INTEGER DEFAULT 0
        )
    """)

    c.execute("SELECT id FROM players")
    for (pid,) in c.fetchall():
        c.execute("INSERT OR IGNORE INTO loss_streaks (player, streak) VALUES (?, 0)", (pid,))
        c.execute("INSERT OR IGNORE INTO win_streaks (player, streak, max_streak) VALUES (?, 0, 0)", (pid,))

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Ticket helpers
# ---------------------------------------------------------------------------

def extract_ticket_id(input_value):
    try:
        parsed = urlparse(input_value)
        query = parse_qs(parsed.query)
        if "id" in query:
            return query["id"][0]
        return input_value
    except:
        return input_value


def fetch_data(ticket_id):
    params = {"id": ticket_id, "source": "SB"}
    try:
        res = requests.get(API_URL, params=params)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print("API error:", e)
        return None


def parse_psk_date(iso_string):
    try:
        dt = datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%SZ")
        dt = dt.replace(tzinfo=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M")


def normalize_result(api_result):
    if api_result == "WINNING":
        return "WINNING"
    if api_result in ("VOIDED", "WINNING_VOIDED"):
        return "VOIDED"
    if api_result == "LOSING":
        return "LOSING"
    return "PENDING"


def ticket_overall_status(bets_results):
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
    psk_created = parse_psk_date(data.get("placementDetailsTime", ""))

    # Extract payout from winning ticket
    payout = None
    if data.get("result") == "WINNING":
        payout = data.get("payoutDetailsWinning")
        if payout is not None:
            try:
                payout = float(payout)
            except (TypeError, ValueError):
                payout = None

    c.execute("""
        INSERT INTO tickets (ticket_id, ticket_number, created_at, last_updated, ticket_jwt, ticket_result, payout)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (ticket_id, number, psk_created, now, ticket_number, data.get("result"), payout))

    # Determine which players were eligible for this ticket based on join date.
    # This is the critical fix: when re-importing old tickets after a DB reset,
    # players who joined AFTER a ticket's date are automatically excluded.
    active_players = get_eligible_players_for_ticket(psk_created, conn)
    for pid in active_players:
        c.execute("INSERT OR IGNORE INTO ticket_players (ticket_id, player_id) VALUES (?, ?)", (ticket_id, pid))

    legs = data.get("legs", [])
    total_legs = len(legs)
    num_players = max(len(active_players), 1)
    player_ids = sorted(active_players.keys())

    if total_legs == num_players:
        legs_per_player = 1
    elif total_legs == num_players * 2:
        legs_per_player = 2
    else:
        legs_per_player = max(1, total_legs // num_players)

    for index, leg in enumerate(legs):
        player_index = min(index // legs_per_player, len(player_ids) - 1)
        player = player_ids[player_index]
        # Start time is a top-level field on the leg
        raw_start = leg.get("startTime") or ""
        start_time = parse_psk_date(raw_start) if raw_start else None
        # Outcome result: markets[0].outcomeResult  → e.g. "3 : 2"
        # Selection name: markets[0].selections[0].name  → e.g. "1", "X", "Over 2.5"
        market = (leg.get("markets") or [None])[0] or {}
        outcome_result = market.get("outcomeResult") or None          # "3 : 2"
        selection_name = None
        selections = market.get("selections") or []
        if selections:
            selection_name = selections[0].get("name") or None        # "1"
        # Store as "1 (3:2)" — outcome picked + final score
        if outcome_result and selection_name:
            score = f"{selection_name} ({outcome_result})"
        elif selection_name:
            score = selection_name
        elif outcome_result:
            score = outcome_result
        else:
            score = None
        c.execute("""
            INSERT INTO bets (ticket_id, player, fixture_name, odds, result, start_time, score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (ticket_id, player, leg.get("fixtureName"), leg.get("oddsPlaced"),
              leg.get("result"), start_time, score))

    conn.commit()
    update_loss_streaks(ticket_id, conn)
    conn.close()


# ---------------------------------------------------------------------------
# Streak logic
# ---------------------------------------------------------------------------

def update_loss_streaks(ticket_id, conn=None):
    close_conn = conn is None
    if close_conn:
        conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT DISTINCT player FROM bets WHERE ticket_id=?", (ticket_id,))
    players = [row[0] for row in c.fetchall()]

    for player in players:
        c.execute("SELECT result FROM bets WHERE ticket_id=? AND player=?", (ticket_id, player))
        results = [row[0] for row in c.fetchall()]

        if not results or any(r in (None, "PENDING", "UNKNOWN") for r in results):
            continue

        all_losing = all(r == "LOSING" for r in results)
        c.execute("SELECT streak FROM loss_streaks WHERE player=?", (player,))
        row = c.fetchone()
        current_streak = row[0] if row else 0

        if all_losing:
            new_streak = 1 if current_streak >= 3 else current_streak + 1
        else:
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


def get_win_streaks():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT player, streak FROM win_streaks")
    streaks = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return streaks


def recalculate_all_streaks():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    PLAYER_NAMES = get_player_names(conn)

    for player_id in PLAYER_NAMES:
        c.execute("INSERT OR REPLACE INTO loss_streaks (player, streak) VALUES (?, 0)", (player_id,))
        c.execute("INSERT OR REPLACE INTO win_streaks (player, streak, max_streak) VALUES (?, 0, 0)", (player_id,))

    c.execute("SELECT ticket_id FROM tickets ORDER BY id ASC")
    ticket_ids = [row[0] for row in c.fetchall()]

    loss_streaks = {pid: 0 for pid in PLAYER_NAMES}
    win_streaks  = {pid: 0 for pid in PLAYER_NAMES}
    max_streaks  = {pid: 0 for pid in PLAYER_NAMES}

    for ticket_id in ticket_ids:
        for player in PLAYER_NAMES:
            c.execute("SELECT result FROM bets WHERE ticket_id=? AND player=?", (ticket_id, player))
            results = [row[0] for row in c.fetchall()]

            if not results or any(r in (None, "PENDING", "UNKNOWN") for r in results):
                continue

            all_losing  = all(r == "LOSING" for r in results)
            all_winning = all(r in ("WINNING", "VOIDED", "WINNING_VOIDED") for r in results)

            if all_losing:
                loss_streaks[player] = 1 if loss_streaks[player] >= 3 else loss_streaks[player] + 1
            else:
                loss_streaks[player] = 0

            if all_winning:
                win_streaks[player] += 1
                max_streaks[player] = max(max_streaks[player], win_streaks[player])
            else:
                win_streaks[player] = 0

    for player_id in PLAYER_NAMES:
        c.execute("INSERT OR REPLACE INTO loss_streaks (player, streak) VALUES (?, ?)",
                  (player_id, loss_streaks[player_id]))
        c.execute("INSERT OR REPLACE INTO win_streaks (player, streak, max_streak) VALUES (?, ?, ?)",
                  (player_id, win_streaks[player_id], max_streaks[player_id]))

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Ticket update
# ---------------------------------------------------------------------------

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
    for (ticket_id, ticket_jwt) in tickets:
        data = fetch_data(ticket_jwt)
        if not data:
            continue
        for leg in data.get("legs", []):
            raw_start = leg.get("startTime") or ""
            start_time = parse_psk_date(raw_start) if raw_start else None
            market = (leg.get("markets") or [None])[0] or {}
            outcome_result = market.get("outcomeResult") or None
            selection_name = None
            selections = market.get("selections") or []
            if selections:
                selection_name = selections[0].get("name") or None
            if outcome_result and selection_name:
                score = f"{selection_name} ({outcome_result})"
            elif selection_name:
                score = selection_name
            elif outcome_result:
                score = outcome_result
            else:
                score = None
            c.execute("""
                UPDATE bets SET result=?, start_time=COALESCE(?, start_time), score=COALESCE(?, score)
                WHERE ticket_id=? AND fixture_name=?
            """, (leg.get("result"), start_time, score, ticket_id, leg.get("fixtureName")))
        c.execute("""
            UPDATE tickets SET last_updated=?, ticket_result=?,
            payout = CASE WHEN ? = 'WINNING' THEN COALESCE(?, payout) ELSE payout END
            WHERE ticket_id=?
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), data.get("result"),
              data.get("result"),
              float(data["payoutDetailsWinning"]) if data.get("payoutDetailsWinning") else None,
              ticket_id))
        conn.commit()

    conn.commit()
    conn.close()
    recalculate_all_streaks()


def auto_update():
    while True:
        update_ticket_results()
        time.sleep(86400)


# ---------------------------------------------------------------------------
# Routes: Auth
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Routes: Player management
# ---------------------------------------------------------------------------

@app.route("/add_player", methods=["POST"])
def add_player():
    if not session.get("admin_logged_in"):
        return "Unauthorized", 403

    name = request.form.get("player_name", "").strip()
    if not name:
        return redirect("/")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Check if player already exists (may have been removed before)
    c.execute("SELECT id, active FROM players WHERE name=?", (name,))
    row = c.fetchone()

    if row:
        pid, active = row
        if active:
            conn.close()
            return redirect("/")  # already active
        # Reactivate — update joined_at to NOW so they only appear on future tickets
        c.execute("UPDATE players SET active=1, joined_at=? WHERE id=?", (now, pid))
    else:
        c.execute("INSERT INTO players (name, active, joined_at) VALUES (?, 1, ?)", (name, now))
        pid = c.lastrowid

    # Ensure streak rows exist
    c.execute("INSERT OR IGNORE INTO loss_streaks (player, streak) VALUES (?, 0)", (pid,))
    c.execute("INSERT OR IGNORE INTO win_streaks (player, streak, max_streak) VALUES (?, 0, 0)", (pid,))

    conn.commit()
    conn.close()
    return redirect("/")


@app.route("/remove_player/<int:player_id>", methods=["POST"])
def remove_player(player_id):
    if not session.get("admin_logged_in"):
        return "Unauthorized", 403

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Soft-delete: keep all history, just mark inactive
    c.execute("UPDATE players SET active=0 WHERE id=?", (player_id,))
    conn.commit()
    conn.close()
    return redirect("/")


# ---------------------------------------------------------------------------
# Routes: Main index
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if not session.get("admin_logged_in"):
            return "Unauthorized", 403

        ticket_number = request.form.get("ticket_number").strip()
        ticket_id = extract_ticket_id(ticket_number)
        data = fetch_data(ticket_id)
        save_ticket(ticket_id, data)
        return redirect("/")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        SELECT ticket_id, ticket_number, created_at, last_updated, ticket_result, ticket_jwt, period_id
        FROM tickets ORDER BY id DESC
    """)
    tickets = c.fetchall()

    c.execute("""
        SELECT ticket_id, player, fixture_name, odds, result, id, start_time, score
        FROM bets ORDER BY ticket_id, player
    """)
    bets = c.fetchall()

    # Periods for the period banner on the index page
    c.execute("SELECT id, name, start_date FROM periods ORDER BY start_date DESC")
    periods = [{"id": r[0], "name": r[1], "start_date": r[2]} for r in c.fetchall()]
    period_ids = {p["id"] for p in periods}

    conn.close()

    return render_template(
        "index.html",
        tickets=tickets,
        bets=bets,
        player_names=get_player_names(),
        active_player_names=get_active_player_names(),
        all_players=get_all_players_with_status(),
        admin_logged_in=session.get("admin_logged_in"),
        loss_streaks=get_loss_streaks(),
        win_streaks=get_win_streaks(),
        normalize_result=normalize_result,
        periods=periods,
        period_ids=period_ids,
    )


# ---------------------------------------------------------------------------
# Routes: Other
# ---------------------------------------------------------------------------

@app.route("/pravila")
def pravila():
    return render_template("pravilaigre.html")


@app.route("/update")
def update():
    if not session.get("admin_logged_in"):
        return redirect("/")
    update_ticket_results()
    return redirect("/")


@app.route("/reassign_legs/<ticket_id>", methods=["POST"])
def reassign_legs(ticket_id):
    if not session.get("admin_logged_in"):
        return "Unauthorized", 403

    PLAYER_NAMES = get_player_names()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    for key, value in request.form.items():
        if key.startswith("bet_player_"):
            bet_id = key[len("bet_player_"):]
            try:
                new_player = int(value)
                bet_id = int(bet_id)
            except ValueError:
                continue
            if new_player in PLAYER_NAMES:
                c.execute("UPDATE bets SET player=? WHERE id=? AND ticket_id=?",
                          (new_player, bet_id, ticket_id))

    conn.commit()
    conn.close()
    recalculate_all_streaks()
    return redirect("/")


@app.route("/delete_ticket/<ticket_id>", methods=["POST"])
def delete_ticket(ticket_id):
    if not session.get("admin_logged_in"):
        return "Unauthorized", 403

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM bets WHERE ticket_id=?", (ticket_id,))
    c.execute("DELETE FROM tickets WHERE ticket_id=?", (ticket_id,))
    c.execute("DELETE FROM ticket_players WHERE ticket_id=?", (ticket_id,))
    conn.commit()
    conn.close()
    recalculate_all_streaks()
    return redirect("/")


# ---------------------------------------------------------------------------
# Routes: Leaderboard & Chart
# ---------------------------------------------------------------------------

@app.route("/chart-data")
def chart_data():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    PLAYER_NAMES = get_player_names(conn)
    period_id = request.args.get("period", type=int)

    if period_id:
        c.execute("""
            SELECT ticket_id, ticket_number FROM tickets
            WHERE period_id=? AND ticket_result IS NOT NULL AND ticket_result != 'PENDING'
            ORDER BY id ASC
        """, (period_id,))
    else:
        c.execute("""
            SELECT ticket_id, ticket_number FROM tickets
            WHERE ticket_result IS NOT NULL AND ticket_result != 'PENDING'
            ORDER BY id ASC
        """)
    resolved_tickets = c.fetchall()

    labels = []
    series = {pid: [] for pid in PLAYER_NAMES}
    totals  = {pid: 0 for pid in PLAYER_NAMES}
    wins    = {pid: 0 for pid in PLAYER_NAMES}

    for ticket_id, ticket_number in resolved_tickets:
        labels.append(ticket_number)
        for pid in PLAYER_NAMES:
            c.execute("""
                SELECT result FROM bets
                WHERE ticket_id=? AND player=?
                AND result NOT IN ('PENDING', 'UNKNOWN', 'VOIDED', 'WINNING_VOIDED')
                AND result IS NOT NULL
            """, (ticket_id, pid))
            results = [r[0] for r in c.fetchall()]
            for r in results:
                totals[pid] += 1
                if r == "WINNING":
                    wins[pid] += 1
            rate = round(wins[pid] / totals[pid] * 100, 1) if totals[pid] > 0 else 0
            series[pid].append(rate)

    conn.close()

    datasets = [
        {"label": PLAYER_NAMES[pid], "data": series[pid]}
        for pid in PLAYER_NAMES
    ]
    return jsonify({"labels": labels, "datasets": datasets})


def compute_leaderboard_stats(c, player_names, ticket_ids):
    """
    Given a cursor, a {player_id: name} dict, and a list of ticket_ids,
    returns (leaderboard_data, payment_data) for those tickets only.
    """
    ticket_set = set(ticket_ids)

    leaderboard_data = []
    for player_id, name in player_names.items():
        if not ticket_set:
            leaderboard_data.append({
                "name": name, "player_id": player_id,
                "win_rate": 0, "avg_odds": 0, "max_win": 0,
                "max_win_streak": 0, "guessed": 0, "missed": 0, "voided": 0,
            })
            continue

        placeholders = ",".join("?" * len(ticket_set))
        tid_list = list(ticket_set)

        c.execute(f"""
            SELECT COUNT(*) FROM bets
            WHERE player=? AND ticket_id IN ({placeholders})
            AND result NOT IN ('UNKNOWN','PENDING','VOIDED','WINNING_VOIDED')
            AND result IS NOT NULL
        """, [player_id] + tid_list)
        total = c.fetchone()[0]

        c.execute(f"SELECT COUNT(*) FROM bets WHERE player=? AND ticket_id IN ({placeholders}) AND result='WINNING'",
                  [player_id] + tid_list)
        guessed = c.fetchone()[0]

        c.execute(f"SELECT COUNT(*) FROM bets WHERE player=? AND ticket_id IN ({placeholders}) AND result='LOSING'",
                  [player_id] + tid_list)
        missed = c.fetchone()[0]

        c.execute(f"SELECT COUNT(*) FROM bets WHERE player=? AND ticket_id IN ({placeholders}) AND result IN ('VOIDED','WINNING_VOIDED')",
                  [player_id] + tid_list)
        voided = c.fetchone()[0]

        c.execute(f"SELECT AVG(odds) FROM bets WHERE player=? AND ticket_id IN ({placeholders}) AND result='WINNING'",
                  [player_id] + tid_list)
        avg_odds = c.fetchone()[0]

        c.execute(f"SELECT MAX(odds) FROM bets WHERE player=? AND ticket_id IN ({placeholders}) AND result='WINNING'",
                  [player_id] + tid_list)
        max_win = c.fetchone()[0]

        # Win streak max within this period
        c.execute(f"""
            SELECT t.ticket_id FROM tickets t
            WHERE t.ticket_id IN ({placeholders})
            ORDER BY t.id ASC
        """, tid_list)
        ordered_tids = [r[0] for r in c.fetchall()]
        max_ws = 0
        cur_ws = 0
        for tid in ordered_tids:
            c.execute("SELECT result FROM bets WHERE ticket_id=? AND player=?", (tid, player_id))
            results = [r[0] for r in c.fetchall()]
            if not results or any(r in (None, "PENDING", "UNKNOWN") for r in results):
                continue
            if all(r in ("WINNING", "VOIDED", "WINNING_VOIDED") for r in results):
                cur_ws += 1
                max_ws = max(max_ws, cur_ws)
            else:
                cur_ws = 0

        win_rate = (guessed / total * 100) if total > 0 else 0
        leaderboard_data.append({
            "name": name, "player_id": player_id,
            "win_rate": round(win_rate, 2),
            "avg_odds": round(avg_odds, 2) if avg_odds else 0,
            "max_win": max_win if max_win else 0,
            "max_win_streak": max_ws,
            "guessed": guessed,
            "missed": missed,
            "voided": voided,
        })

    leaderboard_data.sort(key=lambda x: (x["win_rate"], x["avg_odds"], -x["voided"]), reverse=True)

    # ── Payment calculation ───────────────────────────────────────────────────
    resolved_ticket_ids = [tid for tid in ticket_ids]  # already ordered

    payments = {pid: 0.0 for pid in player_names}
    for i, ticket_id in enumerate(resolved_ticket_ids):
        c.execute("SELECT player_id FROM ticket_players WHERE ticket_id=?", (ticket_id,))
        snap = c.fetchall()
        ticket_pids = [r[0] for r in snap] if snap else []
        if not ticket_pids:
            c.execute("SELECT DISTINCT player FROM bets WHERE ticket_id=?", (ticket_id,))
            ticket_pids = [r[0] for r in c.fetchall()]

        num_on_ticket = len(ticket_pids)
        if num_on_ticket == 0:
            continue

        if i == 0:
            for pid in ticket_pids:
                if pid in payments:
                    payments[pid] += 1.0
        else:
            prev_ticket_id = resolved_ticket_ids[i - 1]
            c.execute("SELECT player_id FROM ticket_players WHERE ticket_id=?", (prev_ticket_id,))
            prev_snap = c.fetchall()
            prev_pids = [r[0] for r in prev_snap] if prev_snap else []
            if not prev_pids:
                c.execute("SELECT DISTINCT player FROM bets WHERE ticket_id=?", (prev_ticket_id,))
                prev_pids = [r[0] for r in c.fetchall()]

            new_players = set(ticket_pids) - set(prev_pids)
            for pid in new_players:
                if pid in payments:
                    payments[pid] += 1.0

            losers = set()
            for pid in prev_pids:
                c.execute("SELECT COUNT(*) FROM bets WHERE ticket_id=? AND player=? AND result='LOSING'",
                          (prev_ticket_id, pid))
                if c.fetchone()[0] > 0:
                    losers.add(pid)

            if losers:
                covered_by_new = len(new_players)
                remaining_cost = num_on_ticket - covered_by_new
                if remaining_cost > 0:
                    cost_per_loser = round(remaining_cost / len(losers), 2)
                    for pid in losers:
                        if pid in payments:
                            payments[pid] += cost_per_loser

    # ── Winnings calculation ──────────────────────────────────────────────────
    # For each WINNING ticket, split payout equally among all players on that ticket.
    winnings = {pid: 0.0 for pid in player_names}
    for ticket_id in resolved_ticket_ids:
        c.execute("SELECT ticket_result, payout FROM tickets WHERE ticket_id=?", (ticket_id,))
        t_row = c.fetchone()
        if not t_row or t_row[0] != "WINNING" or t_row[1] is None:
            continue
        payout = float(t_row[1])
        c.execute("SELECT DISTINCT player FROM bets WHERE ticket_id=?", (ticket_id,))
        t_players = [r[0] for r in c.fetchall()]
        eligible = [pid for pid in t_players if pid in winnings]
        if not eligible:
            continue
        share = round(payout / len(eligible), 2)
        for pid in eligible:
            winnings[pid] += share

    payment_data = [
        {
            "name": row["name"],
            "total_paid": round(payments[row["player_id"]], 2),
            "total_won": round(winnings[row["player_id"]], 2),
        }
        for row in leaderboard_data
    ]
    return leaderboard_data, payment_data


@app.route("/create_period", methods=["POST"])
def create_period():
    if not session.get("admin_logged_in"):
        return "Unauthorized", 403

    name = request.form.get("period_name", "").strip()
    start_date = request.form.get("period_start_date", "").strip()
    if not name or not start_date:
        return redirect("/leaderboard")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("INSERT INTO periods (name, start_date, created_at) VALUES (?, ?, ?)",
              (name, start_date, now))
    period_id = c.lastrowid

    # Assign all tickets from start_date onward that don't already have a period
    c.execute("""
        UPDATE tickets SET period_id=?
        WHERE created_at >= ? AND period_id IS NULL
    """, (period_id, start_date))

    conn.commit()
    conn.close()
    return redirect("/leaderboard")


@app.route("/delete_period/<int:period_id>", methods=["POST"])
def delete_period(period_id):
    if not session.get("admin_logged_in"):
        return "Unauthorized", 403

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Unlink tickets from this period before deleting
    c.execute("UPDATE tickets SET period_id=NULL WHERE period_id=?", (period_id,))
    c.execute("DELETE FROM periods WHERE id=?", (period_id,))
    conn.commit()
    conn.close()
    return redirect("/leaderboard")


@app.route("/leaderboard")
def leaderboard():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    PLAYER_NAMES = get_player_names(conn)

    # ── Overall: all resolved tickets ────────────────────────────────────────
    c.execute("""
        SELECT ticket_id FROM tickets
        WHERE ticket_result IS NOT NULL AND ticket_result != 'PENDING'
        ORDER BY id ASC
    """)
    all_resolved = [r[0] for r in c.fetchall()]
    overall_data, overall_payments = compute_leaderboard_stats(c, PLAYER_NAMES, all_resolved)

    # ── Periods ───────────────────────────────────────────────────────────────
    c.execute("SELECT id, name, start_date FROM periods ORDER BY start_date ASC")
    periods_raw = c.fetchall()

    period_tabs = []
    for (pid, pname, pstart) in periods_raw:
        c.execute("""
            SELECT ticket_id FROM tickets
            WHERE period_id=? AND ticket_result IS NOT NULL AND ticket_result != 'PENDING'
            ORDER BY id ASC
        """, (pid,))
        period_tids = [r[0] for r in c.fetchall()]
        pd_data, pd_payments = compute_leaderboard_stats(c, PLAYER_NAMES, period_tids)
        period_tabs.append({
            "id": pid,
            "name": pname,
            "start_date": pstart,
            "data": pd_data,
            "payment_data": pd_payments,
            "ticket_count": len(period_tids),
        })

    conn.close()

    return render_template(
        "leaderboard.html",
        data=overall_data,
        payment_data=overall_payments,
        period_tabs=period_tabs,
        admin_logged_in=session.get("admin_logged_in"),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=auto_update, daemon=True).start()
    app.run(debug=True)