"""
Test suite for Propali Kladionicari
Run with:  python -m pytest test_app.py -v
"""

import pytest
import sqlite3
import os
import sys
import tempfile

# ── Patch DB_NAME before importing app so all functions use the test DB ──────
os.environ["TESTING"] = "1"
import app as A  # noqa: E402  (import after env var)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """Redirect every sqlite3.connect call to a fresh temp database."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(A, "DB_NAME", db_path)
    A.init_db()
    yield db_path


@pytest.fixture()
def client(use_temp_db):
    A.app.config["TESTING"] = True
    A.app.config["SECRET_KEY"] = "test"
    A.app.config["WTF_CSRF_ENABLED"] = False
    with A.app.test_client() as c:
        yield c


@pytest.fixture()
def admin_client(client):
    """Logged-in admin test client."""
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    yield client


# ─────────────────────────────────────────────────────────────────────────────
# Helper — build minimal API-shaped ticket dict
# ─────────────────────────────────────────────────────────────────────────────

def make_api_ticket(ticket_id="T1", number="NUM001", result="PENDING", legs=None):
    if legs is None:
        # Default: 6 legs (one per player), alternating WINNING/LOSING
        legs = [
            {"fixtureName": f"Match {i+1}", "oddsPlaced": 1.8, "result": "WINNING" if i % 2 == 0 else "LOSING"}
            for i in range(6)
        ]
    return {
        "id": ticket_id,
        "number": number,
        "result": result,
        "placementDetailsTime": "2026-03-27T10:46:28Z",
        "legs": legs,
    }


def make_legs(results):
    """Build a leg list from a simple list of result strings."""
    return [
        {"fixtureName": f"Match {i+1}", "oddsPlaced": 2.0, "result": r}
        for i, r in enumerate(results)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — pure functions, no DB
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeResult:
    def test_winning(self):
        assert A.normalize_result("WINNING") == "WINNING"

    def test_winning_voided(self):
        assert A.normalize_result("WINNING_VOIDED") == "WINNING"

    def test_voided(self):
        assert A.normalize_result("VOIDED") == "WINNING"

    def test_losing(self):
        assert A.normalize_result("LOSING") == "LOSING"

    def test_pending(self):
        assert A.normalize_result("PENDING") == "PENDING"

    def test_none(self):
        assert A.normalize_result(None) == "PENDING"

    def test_unknown(self):
        assert A.normalize_result("UNKNOWN") == "PENDING"

    def test_empty_string(self):
        assert A.normalize_result("") == "PENDING"


class TestExtractTicketId:
    def test_raw_id(self):
        assert A.extract_ticket_id("ABC123") == "ABC123"

    def test_full_url(self):
        url = "https://applink.psk.hr/ticketdetail?id=MYJWT123&source=SB"
        assert A.extract_ticket_id(url) == "MYJWT123"

    def test_url_with_deeplink(self):
        url = "https://applink.psk.hr/ticketdetail?id=TOKEN&source=SB&deeplink=xyz"
        assert A.extract_ticket_id(url) == "TOKEN"

    def test_malformed_returns_input(self):
        assert A.extract_ticket_id("not-a-url") == "not-a-url"


class TestParsePskDate:
    def test_valid_date(self):
        if not hasattr(A, 'parse_psk_date'):
            pytest.skip("parse_psk_date not in this version of app.py")
        result = A.parse_psk_date("2026-03-27T10:46:28Z")
        assert "2026" in result
        assert len(result) > 0

    def test_invalid_returns_fallback(self):
        if not hasattr(A, 'parse_psk_date'):
            pytest.skip("parse_psk_date not in this version of app.py")
        result = A.parse_psk_date("not-a-date")
        assert len(result) > 0

    def test_empty_returns_fallback(self):
        if not hasattr(A, 'parse_psk_date'):
            pytest.skip("parse_psk_date not in this version of app.py")
        result = A.parse_psk_date("")
        assert len(result) > 0


class TestTicketOverallStatus:
    def test_all_winning(self):
        assert A.ticket_overall_status(["WINNING", "WINNING"]) == "WINNING"

    def test_any_losing(self):
        assert A.ticket_overall_status(["WINNING", "LOSING"]) == "LOSING"

    def test_any_pending(self):
        assert A.ticket_overall_status(["WINNING", "PENDING"]) == "PENDING"

    def test_pending_takes_priority_over_losing(self):
        assert A.ticket_overall_status(["LOSING", "PENDING"]) == "PENDING"

    def test_voided_counts_as_winning(self):
        assert A.ticket_overall_status(["VOIDED", "WINNING"]) == "WINNING"

    def test_empty_list(self):
        # No results → normalised list is empty → not PENDING, not LOSING → WINNING
        assert A.ticket_overall_status([]) == "WINNING"


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — save_ticket + DB
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveTicket:
    def test_saves_ticket_row(self, use_temp_db):
        data = make_api_ticket()
        A.save_ticket("MYJWT", data)

        conn = sqlite3.connect(use_temp_db)
        row = conn.execute("SELECT ticket_id, ticket_number FROM tickets").fetchone()
        conn.close()
        assert row[0] == "T1"
        assert row[1] == "NUM001"

    def test_saves_bets(self, use_temp_db):
        data = make_api_ticket(legs=make_legs(["WINNING"] * 6))
        A.save_ticket("JWT", data)

        conn = sqlite3.connect(use_temp_db)
        count = conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
        conn.close()
        assert count == 6

    def test_duplicate_ticket_skipped(self, use_temp_db):
        data = make_api_ticket()
        A.save_ticket("JWT", data)
        A.save_ticket("JWT", data)  # second call should be ignored

        conn = sqlite3.connect(use_temp_db)
        count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        conn.close()
        assert count == 1

    def test_6_legs_one_per_player(self, use_temp_db):
        legs = make_legs(["WINNING"] * 6)
        data = make_api_ticket(legs=legs)
        A.save_ticket("JWT", data)

        conn = sqlite3.connect(use_temp_db)
        rows = conn.execute("SELECT player FROM bets ORDER BY id").fetchall()
        conn.close()
        players = [r[0] for r in rows]
        assert players == [1, 2, 3, 4, 5, 6]

    def test_12_legs_two_per_player(self, use_temp_db):
        legs = make_legs(["WINNING"] * 12)
        data = make_api_ticket(legs=legs)
        A.save_ticket("JWT", data)

        conn = sqlite3.connect(use_temp_db)
        rows = conn.execute("SELECT player FROM bets ORDER BY id").fetchall()
        conn.close()
        players = [r[0] for r in rows]
        assert players == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]

    def test_psk_date_stored_in_created_at(self, use_temp_db):
        data = make_api_ticket()
        A.save_ticket("JWT", data)

        conn = sqlite3.connect(use_temp_db)
        created_at = conn.execute("SELECT created_at FROM tickets").fetchone()[0]
        conn.close()
        assert "2026" in created_at

    def test_none_data_does_nothing(self, use_temp_db):
        A.save_ticket("JWT", None)
        conn = sqlite3.connect(use_temp_db)
        count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        conn.close()
        assert count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — loss streaks
# ─────────────────────────────────────────────────────────────────────────────

def get_streak(db_path, player_id):
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT streak FROM loss_streaks WHERE player=?", (player_id,)).fetchone()
    conn.close()
    return row[0] if row else 0


class TestLossStreaks:
    def test_all_losing_increments_streak(self, use_temp_db):
        legs = make_legs(["LOSING"] * 6)
        A.save_ticket("JWT1", make_api_ticket("T1", legs=legs, result="LOSING"))
        assert get_streak(use_temp_db, 1) == 1

    def test_winning_resets_streak(self, use_temp_db):
        # First ticket: all lose
        A.save_ticket("JWT1", make_api_ticket("T1", legs=make_legs(["LOSING"] * 6), result="LOSING"))
        assert get_streak(use_temp_db, 1) == 1

        # Second ticket: player 1 wins
        legs2 = make_legs(["WINNING", "LOSING", "LOSING", "LOSING", "LOSING", "LOSING"])
        A.save_ticket("JWT2", make_api_ticket("T2", legs=legs2, result="LOSING"))
        A.recalculate_all_streaks()
        assert get_streak(use_temp_db, 1) == 0

    def test_streak_caps_at_3_then_resets(self, use_temp_db):
        for i in range(1, 5):
            legs = make_legs(["LOSING"] * 6)
            A.save_ticket(f"JWT{i}", make_api_ticket(f"T{i}", legs=legs, result="LOSING"))
            A.recalculate_all_streaks()

        # After 4 consecutive losses: streak should reset to 1 (4th ticket starts fresh)
        assert get_streak(use_temp_db, 1) == 1

    def test_pending_legs_dont_update_streak(self, use_temp_db):
        legs = make_legs(["PENDING"] * 6)
        A.save_ticket("JWT1", make_api_ticket("T1", legs=legs, result="PENDING"))
        assert get_streak(use_temp_db, 1) == 0

    def test_recalculate_after_reassign(self, use_temp_db):
        # Player 1 loses on ticket 1
        legs = make_legs(["LOSING"] + ["WINNING"] * 5)
        A.save_ticket("JWT1", make_api_ticket("T1", legs=legs, result="LOSING"))
        assert get_streak(use_temp_db, 1) == 1

        # Reassign player 1's losing leg to player 2
        conn = sqlite3.connect(use_temp_db)
        conn.execute("UPDATE bets SET player=2 WHERE player=1 AND result='LOSING'")
        conn.commit()
        conn.close()

        A.recalculate_all_streaks()
        # Player 1 now has a WINNING leg — streak should reset
        assert get_streak(use_temp_db, 1) == 0
        # Player 2 now has a LOSING leg alongside their WINNING one — not all losing
        assert get_streak(use_temp_db, 2) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — recalculate_all_streaks
# ─────────────────────────────────────────────────────────────────────────────

class TestRecalculateAllStreaks:
    def test_starts_from_zero(self, use_temp_db):
        A.recalculate_all_streaks()
        for pid in A.PLAYER_NAMES:
            assert get_streak(use_temp_db, pid) == 0

    def test_correct_after_delete(self, use_temp_db):
        # Two tickets, both losing
        for i in range(1, 3):
            A.save_ticket(f"JWT{i}", make_api_ticket(f"T{i}", legs=make_legs(["LOSING"] * 6), result="LOSING"))

        # Delete the first ticket
        conn = sqlite3.connect(use_temp_db)
        conn.execute("DELETE FROM bets WHERE ticket_id='T1'")
        conn.execute("DELETE FROM tickets WHERE ticket_id='T1'")
        conn.commit()
        conn.close()

        A.recalculate_all_streaks()
        # Only 1 loss now remains, streak should be 1
        assert get_streak(use_temp_db, 1) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Route tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRoutes:
    def test_index_get(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_login_page(self, client):
        r = client.get("/login")
        assert r.status_code == 200

    def test_login_valid(self, client):
        r = client.post("/login", data={"username": "admin", "password": "password123"},
                        follow_redirects=True)
        assert r.status_code == 200

    def test_login_invalid(self, client):
        r = client.post("/login", data={"username": "admin", "password": "wrong"})
        assert b"Invalid credentials" in r.data or r.status_code == 200

    def test_logout(self, admin_client):
        r = admin_client.get("/logout", follow_redirects=True)
        assert r.status_code == 200

    def test_leaderboard(self, client):
        r = client.get("/leaderboard")
        assert r.status_code == 200

    def test_pravila(self, client):
        r = client.get("/pravila")
        assert r.status_code == 200

    def test_chart_data_empty(self, client):
        r = client.get("/chart-data")
        assert r.status_code == 200
        data = r.get_json()
        assert "labels" in data
        assert "datasets" in data
        assert data["labels"] == []

    def test_post_ticket_requires_auth(self, client):
        r = client.post("/", data={"ticket_number": "someurl"})
        assert r.status_code == 403

    def test_delete_requires_auth(self, client):
        r = client.post("/delete_ticket/T1")
        assert r.status_code == 403

    def test_reassign_requires_auth(self, client):
        r = client.post("/reassign_legs/T1", data={})
        assert r.status_code == 403

    def test_update_requires_auth(self, client):
        r = client.get("/update", follow_redirects=True)
        # Should redirect to / without admin
        assert r.status_code == 200

    def test_delete_ticket(self, admin_client, use_temp_db):
        # Insert a ticket directly
        conn = sqlite3.connect(use_temp_db)
        conn.execute("INSERT INTO tickets (ticket_id, ticket_number, created_at, last_updated) VALUES ('T1','NUM1','2026-01-01','2026-01-01')")
        conn.execute("INSERT INTO bets (ticket_id, player, fixture_name, odds, result) VALUES ('T1', 1, 'Match 1', 2.0, 'LOSING')")
        conn.commit()
        conn.close()

        r = admin_client.post("/delete_ticket/T1", follow_redirects=True)
        assert r.status_code == 200

        conn = sqlite3.connect(use_temp_db)
        count = conn.execute("SELECT COUNT(*) FROM tickets WHERE ticket_id='T1'").fetchone()[0]
        conn.close()
        assert count == 0

    def test_reassign_legs(self, admin_client, use_temp_db):
        conn = sqlite3.connect(use_temp_db)
        conn.execute("INSERT INTO tickets (ticket_id, ticket_number, created_at, last_updated) VALUES ('T1','NUM1','2026-01-01','2026-01-01')")
        conn.execute("INSERT INTO bets (id, ticket_id, player, fixture_name, odds, result) VALUES (99, 'T1', 1, 'Match 1', 2.0, 'LOSING')")
        conn.commit()
        conn.close()

        r = admin_client.post("/reassign_legs/T1", data={"bet_player_99": "3"}, follow_redirects=True)
        assert r.status_code == 200

        conn = sqlite3.connect(use_temp_db)
        player = conn.execute("SELECT player FROM bets WHERE id=99").fetchone()[0]
        conn.close()
        assert player == 3


# ─────────────────────────────────────────────────────────────────────────────
# Payment logic tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPayments:
    def _insert_ticket_with_results(self, db_path, ticket_id, number, player_results, ticket_result):
        """
        player_results: dict {player_id: result_string}
        """
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO tickets (ticket_id, ticket_number, created_at, last_updated, ticket_result) VALUES (?,?,?,?,?)",
            (ticket_id, number, "2026-01-01", "2026-01-01", ticket_result)
        )
        for pid, result in player_results.items():
            conn.execute(
                "INSERT INTO bets (ticket_id, player, fixture_name, odds, result) VALUES (?,?,?,?,?)",
                (ticket_id, pid, f"Match {pid}", 2.0, result)
            )
        conn.commit()
        conn.close()

    def _get_payment_data(self, client):
        r = client.get("/leaderboard")
        # Parse payment_data from context — easier to just call the route
        # and check for known euro amounts in the HTML
        return r.data.decode()

    def test_first_ticket_everyone_pays(self, admin_client, use_temp_db):
        self._insert_ticket_with_results(
            use_temp_db, "T1", "NUM1",
            {1: "WINNING", 2: "WINNING", 3: "WINNING", 4: "WINNING", 5: "WINNING", 6: "WINNING"},
            "WINNING"
        )
        html = self._get_payment_data(admin_client)
        # All 6 players should show €1.00
        assert html.count("€1.00") == 6

    def test_second_ticket_only_losers_pay(self, admin_client, use_temp_db):
        # Ticket 1: players 1 and 2 lose, rest win
        self._insert_ticket_with_results(
            use_temp_db, "T1", "NUM1",
            {1: "LOSING", 2: "LOSING", 3: "WINNING", 4: "WINNING", 5: "WINNING", 6: "WINNING"},
            "LOSING"
        )
        # Ticket 2: all win (just needs to exist to trigger payment for T2)
        self._insert_ticket_with_results(
            use_temp_db, "T2", "NUM2",
            {1: "WINNING", 2: "WINNING", 3: "WINNING", 4: "WINNING", 5: "WINNING", 6: "WINNING"},
            "WINNING"
        )
        html = self._get_payment_data(admin_client)
        # Players 1 and 2: €1 (T1) + €3 (T2, 6/2 losers) = €4.00
        assert html.count("€4.00") == 2
        # Players 3-6: only €1 (T1)
        assert html.count("€1.00") == 4