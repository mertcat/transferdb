"""
TransferDB – Comprehensive Edge-Case Tests
==========================================
Every test opens its own connection, runs inside a transaction,
and rolls back at the end so the DB is never permanently modified.

Existing data used:
  Players  : person_id 1-18
  Referees : 1001-1007
  Managers : 2001-2010
  Clubs    : 1-16  (17th is Free Agent placeholder 999)
  Stadiums : 1-12   (stadium 1 = Etihad, capacity 53 400)
  Competitions : 1-10
  Contracts confirmed active today (2026-04-15):
    player 2  – Permanent at club 1, Loan at club 2
    player 5  – Permanent at club 1
    player 6  – Permanent at club 1
  Match 1  : clubs 1 vs 2, referee 1001, stadium 1, completed
"""

import mysql.connector
import pytest

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "transferdb_user",
    "password": "0000",
    "database": "transferdb",
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _match(cur, match_id, dt, home, away, stadium=4, comp=1, ref=1002):
    cur.execute("""
        INSERT INTO `Match`
            (match_id, match_datetime, home_club_id, away_club_id,
             stadium_id, competition_id, referee_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (match_id, dt, home, away, stadium, comp, ref))

def _lineup(cur, match_id, player_id, starter=0,
            minutes=0, pos='TBD', goals=0, assists=0,
            yc=0, rc=0, rating=5.0):
    cur.execute("""
        INSERT INTO Lineup
            (match_id, player_id, is_starter, minutes_played,
             position_in_match, goals, assists,
             yellow_cards, red_cards, rating)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (match_id, player_id, starter, minutes, pos,
          goals, assists, yc, rc, rating))

# ══════════════════════════════════════════════════════════════════════════════
# 1. MATCH SCHEDULING — trg_match_no_overlap
# ══════════════════════════════════════════════════════════════════════════════

def test_stadium_conflict_under_120min():
    """Same stadium, 90 min apart → stadium conflict error."""
    db = get_db(); cur = db.cursor()
    try:
        _match(cur, 9001, '2027-03-01 14:00:00', 1, 2, stadium=1, ref=1001)
        with pytest.raises(mysql.connector.Error, match="[Ss]tadium"):
            _match(cur, 9002, '2027-03-01 15:30:00', 3, 4, stadium=1, ref=1002)
    finally:
        db.rollback(); cur.close(); db.close()


def test_stadium_ok_after_120min():
    """Same stadium, exactly 121 min apart → no conflict."""
    db = get_db(); cur = db.cursor()
    try:
        _match(cur, 9001, '2027-03-02 14:00:00', 1, 2, stadium=1, ref=1001)
        _match(cur, 9002, '2027-03-02 16:01:00', 3, 4, stadium=1, ref=1002)
    finally:
        db.rollback(); cur.close(); db.close()


def test_referee_conflict_under_120min():
    """Same referee, 60 min apart → referee conflict error."""
    db = get_db(); cur = db.cursor()
    try:
        _match(cur, 9003, '2027-03-03 15:00:00', 1, 2, stadium=1, ref=1001)
        with pytest.raises(mysql.connector.Error, match="[Rr]eferee"):
            _match(cur, 9004, '2027-03-03 16:00:00', 3, 4, stadium=2, ref=1001)
    finally:
        db.rollback(); cur.close(); db.close()


def test_home_club_conflict_under_120min():
    """Same home club, 90 min apart → home club conflict error."""
    db = get_db(); cur = db.cursor()
    try:
        _match(cur, 9005, '2027-03-04 14:00:00', 5, 6, stadium=4, ref=1002)
        with pytest.raises(mysql.connector.Error, match="[Cc]lub"):
            _match(cur, 9006, '2027-03-04 15:30:00', 5, 7, stadium=5, ref=1003)
    finally:
        db.rollback(); cur.close(); db.close()


def test_away_club_conflict_under_120min():
    """Same away club, 90 min apart → away club conflict error."""
    db = get_db(); cur = db.cursor()
    try:
        _match(cur, 9007, '2027-03-05 14:00:00', 5, 6, stadium=4, ref=1002)
        with pytest.raises(mysql.connector.Error, match="[Cc]lub"):
            _match(cur, 9008, '2027-03-05 15:30:00', 7, 6, stadium=5, ref=1003)
    finally:
        db.rollback(); cur.close(); db.close()


def test_past_date_match():
    """Match in the past → error."""
    db = get_db(); cur = db.cursor()
    try:
        with pytest.raises(mysql.connector.Error, match="[Ff]uture"):
            _match(cur, 9009, '2020-01-01 12:00:00', 1, 2)
    finally:
        db.rollback(); cur.close(); db.close()


def test_same_club_home_away():
    """A club cannot play itself → CHECK constraint error."""
    db = get_db(); cur = db.cursor()
    try:
        with pytest.raises(mysql.connector.Error):
            _match(cur, 9010, '2027-03-06 20:00:00', 1, 1)
    finally:
        db.rollback(); cur.close(); db.close()


# ══════════════════════════════════════════════════════════════════════════════
# 2. LINEUP — trg_lineup_starter_limit, trg_no_loan_parent_play
# ══════════════════════════════════════════════════════════════════════════════

def test_starter_limit_exceeded():
    """11 starters already → adding a 12th starter raises error."""
    db = get_db(); cur = db.cursor()
    try:
        _match(cur, 9011, '2027-04-01 20:00:00', 3, 4, stadium=3, ref=1002)
        for pid in range(1, 12):           # players 1-11 as starters
            _lineup(cur, 9011, pid, starter=1, minutes=90, rating=6.0)
        with pytest.raises(mysql.connector.Error, match="[Ss]tarter"):
            _lineup(cur, 9011, 12, starter=1, minutes=90, rating=6.0)
    finally:
        db.rollback(); cur.close(); db.close()


def test_starter_limit_exactly_11_ok():
    """Exactly 11 starters → accepted."""
    db = get_db(); cur = db.cursor()
    try:
        _match(cur, 9012, '2027-04-02 20:00:00', 3, 4, stadium=3, ref=1002)
        for pid in range(1, 12):
            _lineup(cur, 9012, pid, starter=1, minutes=90, rating=6.0)
    finally:
        db.rollback(); cur.close(); db.close()


def test_squad_size_exceeded():
    """Squad > 23 → error."""
    db = get_db(); cur = db.cursor()
    try:
        _match(cur, 9013, '2027-04-03 20:00:00', 5, 6, stadium=4, ref=1003)
        # Create 6 temporary players so we have 24 total (18 existing + 6)
        for pid in range(9901, 9907):
            cur.execute("""
                INSERT INTO Person (person_id, name, surname, nationality, date_of_birth)
                VALUES (%s,'Tmp','Player','Test','2000-01-01')
            """, (pid,))
            cur.execute("""
                INSERT INTO Player (person_id, market_value, main_position, strong_foot, height)
                VALUES (%s, 1000, 'Forward', 'Right', 180)
            """, (pid,))
        # Add 23 players (IDs 1-18, 9901-9905)
        for pid in list(range(1, 19)) + list(range(9901, 9906)):
            _lineup(cur, 9013, pid, minutes=0, rating=5.0)
        # 24th must fail
        with pytest.raises(mysql.connector.Error, match="[Ss]quad"):
            _lineup(cur, 9013, 9906, minutes=0, rating=5.0)
    finally:
        db.rollback(); cur.close(); db.close()


def test_loan_player_blocked_from_parent_club_match():
    """Player 2 on loan from club 1; match involving club 1 → error."""
    db = get_db(); cur = db.cursor()
    try:
        # Match 1 (existing) has clubs 1 and 2. Player 2 is on loan from club 1.
        with pytest.raises(mysql.connector.Error, match="[Ll]oan"):
            _lineup(cur, 1, 2, starter=1, minutes=90, rating=7.0)
    finally:
        db.rollback(); cur.close(); db.close()


# ══════════════════════════════════════════════════════════════════════════════
# 3. ATTENDANCE — trg_match_attendance_capacity
# ══════════════════════════════════════════════════════════════════════════════

def test_attendance_exceeds_capacity():
    """Attendance > stadium capacity → error (stadium 1 cap = 53 400)."""
    db = get_db(); cur = db.cursor()
    try:
        with pytest.raises(mysql.connector.Error, match="[Cc]apacity"):
            cur.execute(
                "UPDATE `Match` SET attendance = 60000 WHERE match_id = 1"
            )
            db.commit()
    finally:
        db.rollback(); cur.close(); db.close()


def test_attendance_at_capacity_ok():
    """Attendance exactly at capacity → accepted."""
    db = get_db(); cur = db.cursor()
    try:
        cur.execute(
            "UPDATE `Match` SET attendance = 53400 WHERE match_id = 1"
        )
    finally:
        db.rollback(); cur.close(); db.close()


# ══════════════════════════════════════════════════════════════════════════════
# 4. CONTRACTS — trg_contract_rules
# ══════════════════════════════════════════════════════════════════════════════

def test_duplicate_permanent_contract():
    """Player with active permanent → adding a second permanent → error."""
    db = get_db(); cur = db.cursor()
    try:
        # Player 5 has an active permanent at club 1 (confirmed from data)
        with pytest.raises(mysql.connector.Error, match="[Pp]ermanent"):
            cur.execute("""
                INSERT INTO Contract (player_id, club_id, contract_type,
                                      weekly_wage, start_date, end_date)
                VALUES (5, 2, 'Permanent', 5000, '2026-01-01', '2028-01-01')
            """)
    finally:
        db.rollback(); cur.close(); db.close()


def test_loan_requires_permanent_elsewhere():
    """Loan contract without any active permanent → error."""
    db = get_db(); cur = db.cursor()
    try:
        # Create a brand-new player with no contracts
        cur.execute("""
            INSERT INTO Person (person_id, name, surname, nationality, date_of_birth)
            VALUES (9920, 'Test', 'NoContract', 'Test', '2000-01-01')
        """)
        cur.execute("""
            INSERT INTO Player (person_id, market_value, main_position, strong_foot, height)
            VALUES (9920, 1000, 'Forward', 'Right', 180)
        """)
        with pytest.raises(mysql.connector.Error, match="[Ll]oan"):
            cur.execute("""
                INSERT INTO Contract (player_id, club_id, contract_type,
                                      weekly_wage, start_date, end_date)
                VALUES (9920, 2, 'Loan', 3000, '2026-05-01', '2027-05-01')
            """)
    finally:
        db.rollback(); cur.close(); db.close()


def test_loan_requires_permanent_at_different_club():
    """Loan to the same club as the permanent → error."""
    db = get_db(); cur = db.cursor()
    try:
        # Create player with permanent at club 2
        cur.execute("""
            INSERT INTO Person (person_id, name, surname, nationality, date_of_birth)
            VALUES (9921, 'Test', 'SameClub', 'Test', '2000-01-01')
        """)
        cur.execute("""
            INSERT INTO Player (person_id, market_value, main_position, strong_foot, height)
            VALUES (9921, 1000, 'Forward', 'Right', 180)
        """)
        cur.execute("""
            INSERT INTO Contract (player_id, club_id, contract_type,
                                  weekly_wage, start_date, end_date)
            VALUES (9921, 2, 'Permanent', 5000, '2025-01-01', '2028-01-01')
        """)
        # Loan to the SAME club as permanent → no eligible parent club at different club
        with pytest.raises(mysql.connector.Error, match="[Ll]oan"):
            cur.execute("""
                INSERT INTO Contract (player_id, club_id, contract_type,
                                      weekly_wage, start_date, end_date)
                VALUES (9921, 2, 'Loan', 3000, '2026-05-01', '2027-05-01')
            """)
    finally:
        db.rollback(); cur.close(); db.close()


def test_valid_loan_accepted():
    """Player with permanent at club 1, loan at club 2 → accepted."""
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO Person (person_id, name, surname, nationality, date_of_birth)
            VALUES (9922, 'Test', 'ValidLoan', 'Test', '2000-01-01')
        """)
        cur.execute("""
            INSERT INTO Player (person_id, market_value, main_position, strong_foot, height)
            VALUES (9922, 1000, 'Forward', 'Right', 180)
        """)
        cur.execute("""
            INSERT INTO Contract (player_id, club_id, contract_type,
                                  weekly_wage, start_date, end_date)
            VALUES (9922, 1, 'Permanent', 5000, '2025-01-01', '2028-01-01')
        """)
        # Loan to a different club → must succeed
        cur.execute("""
            INSERT INTO Contract (player_id, club_id, contract_type,
                                  weekly_wage, start_date, end_date)
            VALUES (9922, 2, 'Loan', 3000, '2026-05-01', '2027-05-01')
        """)
    finally:
        db.rollback(); cur.close(); db.close()


def test_second_loan_rejected():
    """Player already on loan → second loan → error."""
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO Person (person_id, name, surname, nationality, date_of_birth)
            VALUES (9923, 'Test', 'SecondLoan', 'Test', '2000-01-01')
        """)
        cur.execute("""
            INSERT INTO Player (person_id, market_value, main_position, strong_foot, height)
            VALUES (9923, 1000, 'Forward', 'Right', 180)
        """)
        cur.execute("""
            INSERT INTO Contract (player_id, club_id, contract_type,
                                  weekly_wage, start_date, end_date)
            VALUES (9923, 1, 'Permanent', 5000, '2025-01-01', '2028-01-01')
        """)
        cur.execute("""
            INSERT INTO Contract (player_id, club_id, contract_type,
                                  weekly_wage, start_date, end_date)
            VALUES (9923, 2, 'Loan', 3000, '2026-01-01', '2027-05-01')
        """)
        with pytest.raises(mysql.connector.Error, match="[Ll]oan"):
            cur.execute("""
                INSERT INTO Contract (player_id, club_id, contract_type,
                                      weekly_wage, start_date, end_date)
                VALUES (9923, 3, 'Loan', 3000, '2026-01-01', '2027-05-01')
            """)
    finally:
        db.rollback(); cur.close(); db.close()


def test_contract_end_before_start():
    """Contract end_date <= start_date → CHECK constraint error."""
    db = get_db(); cur = db.cursor()
    try:
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO Contract (player_id, club_id, contract_type,
                                      weekly_wage, start_date, end_date)
                VALUES (6, 3, 'Permanent', 5000, '2027-01-01', '2026-01-01')
            """)
    finally:
        db.rollback(); cur.close(); db.close()


# ══════════════════════════════════════════════════════════════════════════════
# 5. CLUB — trg_club_manager_unique
# ══════════════════════════════════════════════════════════════════════════════

def test_manager_assigned_to_two_clubs():
    """Manager already at club 1 cannot be assigned to club 2 → error."""
    db = get_db(); cur = db.cursor()
    try:
        # Find manager currently at club 1
        cur2 = db.cursor(dictionary=True)
        cur2.execute("SELECT manager_id FROM Club WHERE club_id = 1")
        mgr = cur2.fetchone()["manager_id"]
        cur2.close()
        with pytest.raises(mysql.connector.Error, match="[Mm]anager"):
            cur.execute("UPDATE Club SET manager_id = %s WHERE club_id = 2", (mgr,))
    finally:
        db.rollback(); cur.close(); db.close()


# ══════════════════════════════════════════════════════════════════════════════
# 6. TRANSFERS — TransferRecord CHECK constraints
# ══════════════════════════════════════════════════════════════════════════════

def test_negative_transfer_fee():
    """transfer_fee < 0 → CHECK constraint error."""
    db = get_db(); cur = db.cursor()
    try:
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO TransferRecord
                    (player_id, from_club_id, to_club_id, transfer_date,
                     transfer_fee, transfer_type)
                VALUES (6, 1, 3, '2027-01-01', -500, 'Purchase')
            """)
    finally:
        db.rollback(); cur.close(); db.close()


def test_free_transfer_nonzero_fee_via_procedure():
    """register_transfer: Free type with fee > 0 → procedure error."""
    db = get_db(); cur = db.cursor()
    try:
        with pytest.raises(mysql.connector.Error, match="[Ff]ree"):
            cur.callproc("register_transfer",
                         [6, 1, 3, 'Free', 1000.00, 5000.00, '2027-12-31', 0, 0])
    finally:
        db.rollback(); cur.close(); db.close()


def test_transfer_from_club_equals_to_club():
    """from_club_id = to_club_id → CHECK constraint error."""
    db = get_db(); cur = db.cursor()
    try:
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO TransferRecord
                    (player_id, from_club_id, to_club_id, transfer_date,
                     transfer_fee, transfer_type)
                VALUES (6, 2, 2, '2027-01-01', 0, 'Free')
            """)
    finally:
        db.rollback(); cur.close(); db.close()


# ══════════════════════════════════════════════════════════════════════════════
# 7. SCHEMA CHECK CONSTRAINTS — Lineup
# ══════════════════════════════════════════════════════════════════════════════

def _fresh_lineup_match(cur):
    """Insert a throwaway future match and return its id (9099)."""
    _match(cur, 9099, '2027-09-01 20:00:00', 5, 6, stadium=4, ref=1003)
    return 9099


def test_lineup_rating_too_low():
    db = get_db(); cur = db.cursor()
    try:
        mid = _fresh_lineup_match(cur)
        with pytest.raises(mysql.connector.Error):
            _lineup(cur, mid, 3, rating=0.5)
    finally:
        db.rollback(); cur.close(); db.close()


def test_lineup_rating_too_high():
    db = get_db(); cur = db.cursor()
    try:
        mid = _fresh_lineup_match(cur)
        with pytest.raises(mysql.connector.Error):
            _lineup(cur, mid, 3, rating=10.5)
    finally:
        db.rollback(); cur.close(); db.close()


def test_lineup_minutes_over_120():
    db = get_db(); cur = db.cursor()
    try:
        mid = _fresh_lineup_match(cur)
        with pytest.raises(mysql.connector.Error):
            _lineup(cur, mid, 3, minutes=121, rating=6.0)
    finally:
        db.rollback(); cur.close(); db.close()


def test_lineup_yellow_cards_over_2():
    db = get_db(); cur = db.cursor()
    try:
        mid = _fresh_lineup_match(cur)
        with pytest.raises(mysql.connector.Error):
            _lineup(cur, mid, 3, yc=3, rating=6.0)
    finally:
        db.rollback(); cur.close(); db.close()


def test_lineup_red_cards_over_1():
    db = get_db(); cur = db.cursor()
    try:
        mid = _fresh_lineup_match(cur)
        with pytest.raises(mysql.connector.Error):
            _lineup(cur, mid, 3, rc=2, rating=6.0)
    finally:
        db.rollback(); cur.close(); db.close()


def test_lineup_negative_goals():
    db = get_db(); cur = db.cursor()
    try:
        mid = _fresh_lineup_match(cur)
        with pytest.raises(mysql.connector.Error):
            _lineup(cur, mid, 3, goals=-1, rating=6.0)
    finally:
        db.rollback(); cur.close(); db.close()


# ══════════════════════════════════════════════════════════════════════════════
# 8. SCHEMA CHECK CONSTRAINTS — Player / Contract / Referee
# ══════════════════════════════════════════════════════════════════════════════

def test_player_market_value_zero():
    """market_value must be > 0."""
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO Person (person_id, name, surname, nationality, date_of_birth)
            VALUES (9930, 'Bad', 'Value', 'Test', '2000-01-01')
        """)
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO Player (person_id, market_value, main_position, strong_foot, height)
                VALUES (9930, 0, 'Forward', 'Right', 180)
            """)
    finally:
        db.rollback(); cur.close(); db.close()


def test_player_height_zero():
    """height must be > 0."""
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO Person (person_id, name, surname, nationality, date_of_birth)
            VALUES (9931, 'Bad', 'Height', 'Test', '2000-01-01')
        """)
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO Player (person_id, market_value, main_position, strong_foot, height)
                VALUES (9931, 1000, 'Forward', 'Right', 0)
            """)
    finally:
        db.rollback(); cur.close(); db.close()


def test_contract_weekly_wage_zero():
    """weekly_wage must be > 0."""
    db = get_db(); cur = db.cursor()
    try:
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO Contract (player_id, club_id, contract_type,
                                      weekly_wage, start_date, end_date)
                VALUES (6, 3, 'Permanent', 0, '2027-01-01', '2028-01-01')
            """)
    finally:
        db.rollback(); cur.close(); db.close()


def test_referee_negative_experience():
    """years_of_experience must be >= 0."""
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO Person (person_id, name, surname, nationality, date_of_birth)
            VALUES (9932, 'Bad', 'Ref', 'Test', '1990-01-01')
        """)
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO Referee (person_id, license_level, years_of_experience)
                VALUES (9932, 'FIFA', -1)
            """)
    finally:
        db.rollback(); cur.close(); db.close()


def test_stadium_capacity_zero():
    """Stadium capacity must be > 0."""
    db = get_db(); cur = db.cursor()
    try:
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO Stadium (stadium_name, city, capacity)
                VALUES ('Bad Stadium', 'Nowhere', 0)
            """)
    finally:
        db.rollback(); cur.close(); db.close()


# ══════════════════════════════════════════════════════════════════════════════
# 9. UNIQUE CONSTRAINTS
# ══════════════════════════════════════════════════════════════════════════════

def test_duplicate_competition_name_season():
    """Same competition name + season → unique constraint error."""
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("""
            SELECT name, season FROM Competition LIMIT 1
        """)
        row = cur.fetchone()
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO Competition (name, season, country, competition_type)
                VALUES (%s, %s, 'Test', 'League')
            """, row)
    finally:
        db.rollback(); cur.close(); db.close()


def test_duplicate_club_name():
    """Same club name → unique constraint error."""
    db = get_db(); cur = db.cursor()
    try:
        cur2 = db.cursor(dictionary=True)
        cur2.execute("SELECT club_name FROM Club LIMIT 1")
        name = cur2.fetchone()["club_name"]
        cur2.close()
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO Club (club_name, city, foundation_year)
                VALUES (%s, 'City', 2000)
            """, (name,))
    finally:
        db.rollback(); cur.close(); db.close()


def test_duplicate_username():
    """Same AppUser username → unique (PK) constraint error."""
    db = get_db(); cur = db.cursor()
    try:
        cur2 = db.cursor(dictionary=True)
        cur2.execute("SELECT username FROM AppUser LIMIT 1")
        uname = cur2.fetchone()["username"]
        cur2.close()
        with pytest.raises(mysql.connector.Error):
            cur.execute("""
                INSERT INTO AppUser (username, password, role)
                VALUES (%s, 'hash', 'DatabaseManager')
            """, (uname,))
    finally:
        db.rollback(); cur.close(); db.close()


# ══════════════════════════════════════════════════════════════════════════════
# 10. STORED PROCEDURES
# ══════════════════════════════════════════════════════════════════════════════

def test_submit_result_wrong_referee():
    """Referee 1002 tries to submit result for match assigned to 1001 → error."""
    db = get_db(); cur = db.cursor()
    try:
        # Match 1 has referee_id = 1001; submit with 1002
        with pytest.raises(mysql.connector.Error, match="[Rr]eferee"):
            cur.callproc("submit_match_result", [1, 1002, 2, 1, 40000])
    finally:
        db.rollback(); cur.close(); db.close()


def test_submit_result_future_match():
    """Cannot submit result for a match that hasn't been played yet."""
    db = get_db(); cur = db.cursor()
    try:
        # Match 5 is in the future (2026-05-01), referee 1002
        with pytest.raises(mysql.connector.Error, match="[Bb]efore|[Ff]uture|[Tt]ime"):
            cur.callproc("submit_match_result", [5, 1002, 1, 0, 15000])
    finally:
        db.rollback(); cur.close(); db.close()


def test_free_transfer_nonzero_fee_procedure():
    """register_transfer: Free type + fee > 0 → error inside procedure."""
    db = get_db(); cur = db.cursor()
    try:
        with pytest.raises(mysql.connector.Error, match="[Ff]ree"):
            # player 6 has permanent at club 1 → from_club_id = 1
            cur.callproc("register_transfer",
                         [6, 1, 3, 'Free', 999.00, 5000.00, '2028-01-01', 0, 0])
    finally:
        db.rollback(); cur.close(); db.close()
