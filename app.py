"""
TransferDB – Flask Backend
CMPE 321 Spring 2026

Requirements:
    pip install flask mysql-connector-python bcrypt
"""

import re
import bcrypt
import mysql.connector
from functools import wraps
from flask import (Flask, request, session, redirect, url_for,
                   render_template, flash, g)

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_TO_A_RANDOM_SECRET_IN_PRODUCTION"

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE CONFIG  – edit to match your local MySQL setup
# ─────────────────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "127.0.0.1",
    "port":     3306,
    "user":     "transferdb_user",
    "password": "0000",
    "database": "transferdb",
    "charset":  "utf8mb4",
}


def get_db():
    """Return a per-request MySQL connection (stored in Flask's g)."""
    if "db" not in g:
        g.db = mysql.connector.connect(**DB_CONFIG)
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

PASSWORD_RE = re.compile(
    r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@#$%&!^*()_\-+=<>?]).{8,}$'
)


def friendly_error(err) -> str:
    """Convert a mysql.connector.Error to a readable message."""
    code = err.errno
    msg  = err.msg or ""
    if code == 1062:
        m = re.search(r"Duplicate entry '(.+?)' for key '(.+?)'", msg)
        if m:
            return f"Duplicate value '{m.group(1)}' — this entry already exists."
        return "A duplicate entry was found — this record already exists."
    if code == 1452:
        return "One of the selected values no longer exists in the database. Refresh the page and try again."
    if code == 1451:
        return "Cannot complete: other records still reference this entry."
    if code in (4025, 3819):
        m = re.search(r"constraint '(.+?)'", msg)
        if m:
            return f"A field value is outside its allowed range (constraint: {m.group(1)})."
        return "A field value violates a database constraint (value out of allowed range)."
    # errno 1644 = SIGNAL from stored procedure — already human-readable
    return msg


def validate_password(password: str) -> list[str]:
    """Return a list of violation messages; empty list means OK."""
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one digit.")
    if not re.search(r'[@#$%&!^*()_\-+=<>?]', password):
        errors.append("Password must contain at least one special character.")
    return errors


def hash_password(plain: str) -> str:
    """bcrypt-hash a plain-text password; returns a UTF-8 string for DB storage."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode("utf-8")


def check_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode("utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# ROLE-BASED ACCESS DECORATORS
# ─────────────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Usage: @role_required('DatabaseManager', 'Referee')"""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            if session.get("role") not in roles:
                flash("Access denied: insufficient permissions.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # Parameterized query – SQL injection safe
        db  = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute(
            "SELECT username, password, role, person_id FROM AppUser WHERE username = %s",
            (username,)
        )
        user = cur.fetchone()
        cur.close()

        if user and check_password(password, user["password"]):
            session["username"]  = user["username"]
            session["role"]      = user["role"]
            session["person_id"] = user["person_id"]
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """
    Any role can self-register here.
    Database Manager accounts are also created via this page.
    """
    if request.method == "POST":
        username  = request.form.get("username", "").strip()
        password  = request.form.get("password", "")
        role      = request.form.get("role", "")

        # Password policy – handled in application layer (per spec §4)
        errors = validate_password(password)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("signup.html")

        db  = get_db()
        cur = db.cursor()

        # Check username uniqueness (parameterized)
        cur.execute("SELECT 1 FROM AppUser WHERE username = %s", (username,))
        if cur.fetchone():
            flash("Username already taken.", "danger")
            cur.close()
            return render_template("signup.html")

        hashed = hash_password(password)

        try:
            if role == "DatabaseManager":
                cur.execute(
                    "INSERT INTO AppUser (username, password, role) VALUES (%s, %s, %s)",
                    (username, hashed, "DatabaseManager")
                )

            elif role == "Player":
                # Collect player-specific fields
                name        = request.form.get("name", "").strip()
                surname     = request.form.get("surname", "").strip()
                nationality = request.form.get("nationality", "").strip()
                dob         = request.form.get("date_of_birth", "")
                market_val  = request.form.get("market_value")
                main_pos    = request.form.get("main_position")
                strong_foot = request.form.get("strong_foot")
                height      = request.form.get("height")

                cur.execute(
                    """INSERT INTO Person (name, surname, nationality, date_of_birth)
                       VALUES (%s, %s, %s, %s)""",
                    (name, surname, nationality, dob)
                )
                pid = cur.lastrowid
                cur.execute(
                    """INSERT INTO Player (person_id, market_value, main_position, strong_foot, height)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (pid, market_val, main_pos, strong_foot, height)
                )
                cur.execute(
                    "INSERT INTO AppUser (username, password, role, person_id) VALUES (%s, %s, 'Player', %s)",
                    (username, hashed, pid)
                )

            elif role == "Manager":
                name        = request.form.get("name", "").strip()
                surname     = request.form.get("surname", "").strip()
                nationality = request.form.get("nationality", "").strip()
                dob         = request.form.get("date_of_birth", "")
                formation   = request.form.get("preferred_formation", "").strip()
                exp_level   = request.form.get("experience_level", "").strip()

                cur.execute(
                    "INSERT INTO Person (name, surname, nationality, date_of_birth) VALUES (%s,%s,%s,%s)",
                    (name, surname, nationality, dob)
                )
                pid = cur.lastrowid
                cur.execute(
                    "INSERT INTO Manager (person_id, preferred_formation, experience_level) VALUES (%s,%s,%s)",
                    (pid, formation, exp_level)
                )
                cur.execute(
                    "INSERT INTO AppUser (username, password, role, person_id) VALUES (%s,%s,'Manager',%s)",
                    (username, hashed, pid)
                )

            elif role == "Referee":
                name        = request.form.get("name", "").strip()
                surname     = request.form.get("surname", "").strip()
                nationality = request.form.get("nationality", "").strip()
                dob         = request.form.get("date_of_birth", "")
                lic_level   = request.form.get("license_level", "").strip()
                years_exp   = request.form.get("years_of_experience")

                cur.execute(
                    "INSERT INTO Person (name, surname, nationality, date_of_birth) VALUES (%s,%s,%s,%s)",
                    (name, surname, nationality, dob)
                )
                pid = cur.lastrowid
                cur.execute(
                    "INSERT INTO Referee (person_id, license_level, years_of_experience) VALUES (%s,%s,%s)",
                    (pid, lic_level, years_exp)
                )
                cur.execute(
                    "INSERT INTO AppUser (username, password, role, person_id) VALUES (%s,%s,'Referee',%s)",
                    (username, hashed, pid)
                )
            else:
                flash("Invalid role.", "danger")
                cur.close()
                return render_template("signup.html")

            db.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))

        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Sign-up error: {friendly_error(err)}", "danger")
        finally:
            cur.close()

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD  –  role-based redirect hub
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    role = session["role"]
    if role == "DatabaseManager":
        return redirect(url_for("dbm_home"))
    if role == "Player":
        return redirect(url_for("player_home"))
    if role == "Manager":
        return redirect(url_for("manager_home"))
    if role == "Referee":
        return redirect(url_for("referee_home"))
    return redirect(url_for("login"))


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE MANAGER ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/dbm")
@role_required("DatabaseManager")
def dbm_home():
    return render_template("dbm/home.html")


@app.route("/dbm/stadiums")
@role_required("DatabaseManager")
def dbm_stadiums():
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT s.stadium_id, s.stadium_name, s.city, s.capacity,
               GROUP_CONCAT(c.club_name ORDER BY c.club_name SEPARATOR ', ') AS clubs
        FROM Stadium s
        LEFT JOIN Club c ON c.stadium_id = s.stadium_id
        GROUP BY s.stadium_id
        ORDER BY s.stadium_name
    """)
    stadiums = cur.fetchall()
    cur.close()
    return render_template("dbm/stadiums.html", stadiums=stadiums)


@app.route("/dbm/stadiums/rename", methods=["POST"])
@role_required("DatabaseManager")
def dbm_rename_stadium():
    sid      = request.form.get("stadium_id")
    new_name = request.form.get("new_name", "").strip()
    if not new_name:
        flash("Stadium name cannot be empty.", "danger")
        return redirect(url_for("dbm_stadiums"))
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE Stadium SET stadium_name = %s WHERE stadium_id = %s",
        (new_name, sid)
    )
    db.commit()
    cur.close()
    flash("Stadium renamed successfully.", "success")
    return redirect(url_for("dbm_stadiums"))


@app.route("/dbm/schedule_match", methods=["GET", "POST"])
@role_required("DatabaseManager")
def dbm_schedule_match():
    db = get_db()
    if request.method == "POST":
        dt           = request.form.get("match_datetime", "").replace("T", " ")  # YYYY-MM-DD HH:MM
        stadium_id   = request.form.get("stadium_id")
        home_club_id = request.form.get("home_club_id")
        away_club_id = request.form.get("away_club_id")
        referee_id   = request.form.get("referee_id")
        comp_id      = request.form.get("competition_id")

        cur = db.cursor()
        try:
            # Call the stored procedure (all constraint logic inside it + triggers)
            cur.callproc("schedule_match", [dt, stadium_id, home_club_id,
                                             away_club_id, referee_id, comp_id, 0])
            db.commit()
            flash("Match scheduled successfully.", "success")
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Could not schedule match: {friendly_error(err)}", "danger")
        finally:
            cur.close()
        return redirect(url_for("dbm_schedule_match"))

    # GET – load dropdowns
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT club_id, club_name FROM Club ORDER BY club_name")
    clubs = cur.fetchall()
    cur.execute("SELECT stadium_id, stadium_name, city FROM Stadium ORDER BY stadium_name")
    stadiums = cur.fetchall()
    cur.execute("""
        SELECT r.person_id AS referee_id,
               CONCAT(p.name,' ',p.surname) AS full_name
        FROM Referee r JOIN Person p ON r.person_id = p.person_id
        ORDER BY p.surname
    """)
    referees = cur.fetchall()
    cur.execute("SELECT competition_id, name, season FROM Competition ORDER BY name, season")
    competitions = cur.fetchall()
    cur.close()
    return render_template("dbm/schedule_match.html",
                           clubs=clubs, stadiums=stadiums,
                           referees=referees, competitions=competitions)


@app.route("/dbm/transfer", methods=["GET", "POST"])
@role_required("DatabaseManager")
def dbm_register_transfer():
    db = get_db()
    if request.method == "POST":
        player_id    = request.form.get("player_id")
        to_club_id   = request.form.get("to_club_id")
        t_type       = request.form.get("transfer_type")
        t_fee        = request.form.get("transfer_fee", "0")
        wage         = request.form.get("weekly_wage")
        contract_end = request.form.get("contract_end")

        # Derive from_club from the player's active permanent contract (NULL if free agent)
        cur = db.cursor(dictionary=True)
        cur.execute("""
            SELECT club_id FROM Contract
            WHERE player_id = %s AND contract_type = 'Permanent'
              AND CURDATE() BETWEEN start_date AND end_date
            LIMIT 1
        """, (player_id,))
        row = cur.fetchone()
        from_club_id = row["club_id"] if row else None
        cur.close()

        cur = db.cursor()
        try:
            cur.callproc("register_transfer",
                         [player_id, from_club_id, to_club_id,
                          t_type, t_fee, wage, contract_end, 0, 0])
            db.commit()
            flash("Transfer registered successfully.", "success")
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Transfer failed: {friendly_error(err)}", "danger")
        finally:
            cur.close()
        return redirect(url_for("dbm_register_transfer"))

    # GET
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT p.person_id, CONCAT(pe.name,' ',pe.surname) AS full_name
        FROM Player p JOIN Person pe ON p.person_id = pe.person_id
        ORDER BY pe.surname
    """)
    players = cur.fetchall()
    cur.execute("SELECT club_id, club_name FROM Club ORDER BY club_name")
    clubs = cur.fetchall()
    # Build player → current permanent club mapping for auto-fill
    cur.execute("""
        SELECT ct.player_id, ct.club_id, c.club_name
        FROM Contract ct
        JOIN Club c ON c.club_id = ct.club_id
        WHERE ct.contract_type = 'Permanent'
          AND CURDATE() BETWEEN ct.start_date AND ct.end_date
    """)
    player_clubs = {str(r['player_id']): {'club_id': r['club_id'], 'club_name': r['club_name']}
                    for r in cur.fetchall()}
    cur.close()
    return render_template("dbm/register_transfer.html",
                           players=players, clubs=clubs, player_clubs=player_clubs)


@app.route("/dbm/competition/create", methods=["GET", "POST"])
@role_required("DatabaseManager")
def dbm_create_competition():
    db = get_db()
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        season   = request.form.get("season", "").strip()
        country  = request.form.get("country", "").strip()
        c_type   = request.form.get("competition_type")
        cur = db.cursor()
        try:
            cur.execute(
                "INSERT INTO Competition (name, season, country, competition_type) VALUES (%s,%s,%s,%s)",
                (name, season, country, c_type)
            )
            db.commit()
            flash("Competition created.", "success")
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Could not create competition: {friendly_error(err)}", "danger")
        finally:
            cur.close()
        return redirect(url_for("dbm_create_competition"))
    return render_template("dbm/create_competition.html")


@app.route("/dbm/assign_manager", methods=["GET", "POST"])
@role_required("DatabaseManager")
def dbm_assign_manager():
    db = get_db()
    if request.method == "POST":
        club_id    = request.form.get("club_id")
        manager_id = request.form.get("manager_id")
        cur = db.cursor()
        try:
            # Trigger trg_club_manager_unique fires here
            cur.execute(
                "UPDATE Club SET manager_id = %s WHERE club_id = %s",
                (manager_id, club_id)
            )
            db.commit()
            flash("Manager assigned.", "success")
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Could not assign manager: {friendly_error(err)}", "danger")
        finally:
            cur.close()
        return redirect(url_for("dbm_assign_manager"))

    cur = db.cursor(dictionary=True)
    cur.execute("SELECT club_id, club_name FROM Club ORDER BY club_name")
    clubs = cur.fetchall()
    cur.execute("""
        SELECT m.person_id, CONCAT(p.name,' ',p.surname) AS full_name
        FROM Manager m JOIN Person p ON m.person_id = p.person_id
        ORDER BY p.surname
    """)
    managers = cur.fetchall()
    cur.close()
    return render_template("dbm/assign_manager.html",
                           clubs=clubs, managers=managers)


# ─────────────────────────────────────────────────────────────────────────────
# PLAYER ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/player")
@role_required("Player")
def player_home():
    pid = session["person_id"]
    db  = get_db()
    cur = db.cursor(dictionary=True)

    # Profile
    cur.execute("""
        SELECT pe.name, pe.surname, pe.nationality,
               TIMESTAMPDIFF(YEAR, pe.date_of_birth, CURDATE()) AS age,
               pl.market_value, pl.main_position, pl.strong_foot, pl.height,
               c.club_name AS current_club
        FROM Person pe
        JOIN Player pl ON pl.person_id = pe.person_id
        LEFT JOIN Contract ct ON ct.player_id = pe.person_id
            AND ct.contract_type = 'Permanent'
            AND CURDATE() BETWEEN ct.start_date AND ct.end_date
        LEFT JOIN Club c ON c.club_id = ct.club_id
        WHERE pe.person_id = %s
    """, (pid,))
    profile = cur.fetchone()
    cur.close()
    return render_template("player/home.html", profile=profile)


@app.route("/player/stats")
@role_required("Player")
def player_stats():
    pid    = session["person_id"]
    season = request.args.get("season")
    comp   = request.args.get("competition_id")
    db     = get_db()
    cur    = db.cursor(dictionary=True)

    # Build filter dynamically (still parameterized)
    filters  = ["l.player_id = %s"]
    params   = [pid]
    if season:
        filters.append("comp.season = %s")
        params.append(season)
    if comp:
        filters.append("m.competition_id = %s")
        params.append(comp)

    where = " AND ".join(filters)
    cur.execute(f"""
        SELECT COUNT(*) AS games_played,
               SUM(l.goals)        AS total_goals,
               SUM(l.assists)      AS total_assists,
               SUM(l.yellow_cards) AS yellow_cards,
               SUM(l.red_cards)    AS red_cards,
               ROUND(AVG(l.rating), 2) AS avg_rating
        FROM Lineup l
        JOIN `Match` m    ON m.match_id = l.match_id
        JOIN Competition comp ON comp.competition_id = m.competition_id
        WHERE {where}
    """, params)
    stats = cur.fetchone()

    # Seasons & competitions for filter dropdowns
    cur.execute("""
        SELECT DISTINCT comp.season
        FROM Lineup l
        JOIN `Match` m ON m.match_id = l.match_id
        JOIN Competition comp ON comp.competition_id = m.competition_id
        WHERE l.player_id = %s
        ORDER BY comp.season DESC
    """, (pid,))
    seasons = [r["season"] for r in cur.fetchall()]

    cur.execute("""
        SELECT DISTINCT comp.competition_id, comp.name, comp.season
        FROM Lineup l
        JOIN `Match` m ON m.match_id = l.match_id
        JOIN Competition comp ON comp.competition_id = m.competition_id
        WHERE l.player_id = %s
        ORDER BY comp.name
    """, (pid,))
    competitions = cur.fetchall()
    cur.close()

    return render_template("player/stats.html",
                           stats=stats, seasons=seasons,
                           competitions=competitions,
                           selected_season=season,
                           selected_comp=comp)


@app.route("/player/match_history")
@role_required("Player")
def player_match_history():
    pid = session["person_id"]
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT m.match_datetime, comp.name AS competition,
               s.stadium_name,
               CASE WHEN m.home_club_id = c_home.club_id
                    THEN c_away.club_name ELSE c_home.club_name END AS opponent,
               m.home_goals, m.away_goals,
               l.minutes_played, l.position_in_match,
               l.goals, l.assists, l.yellow_cards, l.red_cards, l.rating,
               m.is_completed
        FROM Lineup l
        JOIN `Match` m     ON m.match_id = l.match_id
        JOIN Competition comp ON comp.competition_id = m.competition_id
        JOIN Stadium s     ON s.stadium_id = m.stadium_id
        JOIN Club c_home   ON c_home.club_id = m.home_club_id
        JOIN Club c_away   ON c_away.club_id = m.away_club_id
        WHERE l.player_id = %s
        ORDER BY m.match_datetime DESC
    """, (pid,))
    matches = cur.fetchall()
    cur.close()
    return render_template("player/match_history.html", matches=matches)


@app.route("/player/career_history")
@role_required("Player")
def player_career_history():
    pid = session["person_id"]
    db  = get_db()
    cur = db.cursor(dictionary=True)

    # Contracts
    cur.execute("""
        SELECT c.club_name, ct.contract_type, ct.weekly_wage,
               ct.start_date, ct.end_date
        FROM Contract ct
        JOIN Club c ON c.club_id = ct.club_id
        WHERE ct.player_id = %s
        ORDER BY ct.start_date DESC
    """, (pid,))
    contracts = cur.fetchall()

    # Transfers
    cur.execute("""
        SELECT tr.transfer_date, tr.transfer_fee, tr.transfer_type,
               COALESCE(cf.club_name, 'Free Agent') AS from_club,
               ct2.club_name AS to_club
        FROM TransferRecord tr
        LEFT JOIN Club cf  ON cf.club_id  = tr.from_club_id
        JOIN  Club ct2 ON ct2.club_id = tr.to_club_id
        WHERE tr.player_id = %s
        ORDER BY tr.transfer_date DESC
    """, (pid,))
    transfers = cur.fetchall()
    cur.close()
    return render_template("player/career_history.html",
                           contracts=contracts, transfers=transfers)


# ─────────────────────────────────────────────────────────────────────────────
# MANAGER ROUTES
# ─────────────────────────────────────────────────────────────────────────────

def _get_manager_club_id(person_id):
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT club_id FROM Club WHERE manager_id = %s", (person_id,))
    row = cur.fetchone()
    cur.close()
    return row["club_id"] if row else None


@app.route("/manager")
@role_required("Manager")
def manager_home():
    pid = session["person_id"]
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT pe.name, pe.surname, pe.nationality,
               TIMESTAMPDIFF(YEAR, pe.date_of_birth, CURDATE()) AS age,
               mg.preferred_formation, mg.experience_level,
               c.club_name AS current_club
        FROM Person pe
        JOIN Manager mg ON mg.person_id = pe.person_id
        LEFT JOIN Club c ON c.manager_id = pe.person_id
        WHERE pe.person_id = %s
    """, (pid,))
    profile = cur.fetchone()
    cur.close()
    return render_template("manager/home.html", profile=profile)


@app.route("/manager/fixtures")
@role_required("Manager")
def manager_fixtures():
    pid     = session["person_id"]
    club_id = _get_manager_club_id(pid)
    season  = request.args.get("season")
    comp_id = request.args.get("competition_id")

    db  = get_db()
    cur = db.cursor(dictionary=True)

    filters = ["(m.home_club_id = %s OR m.away_club_id = %s)"]
    params  = [club_id, club_id]
    if season:
        filters.append("comp.season = %s")
        params.append(season)
    if comp_id:
        filters.append("m.competition_id = %s")
        params.append(comp_id)

    where = " AND ".join(filters)
    cur.execute(f"""
        SELECT m.match_id, m.match_datetime, m.home_goals, m.away_goals,
               m.is_completed, m.home_club_id, m.away_club_id,
               ch.club_name AS home_name, ca.club_name AS away_name,
               s.stadium_name, comp.name AS competition, comp.season
        FROM `Match` m
        JOIN Club ch   ON ch.club_id = m.home_club_id
        JOIN Club ca   ON ca.club_id = m.away_club_id
        JOIN Stadium s ON s.stadium_id = m.stadium_id
        JOIN Competition comp ON comp.competition_id = m.competition_id
        WHERE {where}
        ORDER BY m.match_datetime DESC
    """, params)
    fixtures = cur.fetchall()

    cur.execute("SELECT DISTINCT comp.season FROM Competition comp ORDER BY comp.season DESC")
    seasons = [r["season"] for r in cur.fetchall()]
    cur.execute("SELECT competition_id, name, season FROM Competition ORDER BY name")
    competitions = cur.fetchall()
    cur.close()

    return render_template("manager/fixtures.html",
                           fixtures=fixtures, club_id=club_id,
                           seasons=seasons, competitions=competitions)


@app.route("/manager/squad_submit/<int:match_id>", methods=["GET", "POST"])
@role_required("Manager")
def manager_submit_squad(match_id):
    pid     = session["person_id"]
    club_id = _get_manager_club_id(pid)
    db      = get_db()

    if request.method == "POST":
        player_ids  = request.form.getlist("player_ids")
        starter_ids = set(request.form.getlist("starter_ids"))

        if not (11 <= len(player_ids) <= 23):
            flash("Squad must be between 11 and 23 players.", "danger")
            return redirect(url_for("manager_submit_squad", match_id=match_id))
        if len(starter_ids) > 11:
            flash("Cannot have more than 11 starters.", "danger")
            return redirect(url_for("manager_submit_squad", match_id=match_id))

        cur = db.cursor()
        try:
            for pid_str in player_ids:
                is_starter = 1 if pid_str in starter_ids else 0
                # Minimal insertion – stats submitted by referee later
                cur.execute("""
                    INSERT INTO Lineup
                        (match_id, player_id, is_starter, minutes_played,
                         position_in_match, goals, assists,
                         yellow_cards, red_cards, rating)
                    VALUES (%s, %s, %s, 0, 'TBD', 0, 0, 0, 0, 5.0)
                """, (match_id, pid_str, is_starter))
            db.commit()
            flash("Squad submitted.", "success")
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Could not submit squad: {friendly_error(err)}", "danger")
        finally:
            cur.close()
        return redirect(url_for("manager_fixtures"))

    # GET – eligible players (active contract with this club, not on loan to parent)
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT p.person_id, CONCAT(pe.name,' ',pe.surname) AS full_name,
               pl.main_position
        FROM Contract ct
        JOIN Player pl  ON pl.person_id  = ct.player_id
        JOIN Person pe  ON pe.person_id  = ct.player_id
        JOIN (SELECT person_id FROM Player) p ON p.person_id = ct.player_id
        WHERE ct.club_id = %s
          AND CURDATE() BETWEEN ct.start_date AND ct.end_date
        ORDER BY pe.surname
    """, (club_id,))
    players = cur.fetchall()
    cur.execute("""
        SELECT ch.club_name AS home_club, ca.club_name AS away_club,
               m.match_datetime, comp.name AS competition, comp.season,
               s.stadium_name
        FROM `Match` m
        JOIN Club ch ON ch.club_id = m.home_club_id
        JOIN Club ca ON ca.club_id = m.away_club_id
        JOIN Competition comp ON comp.competition_id = m.competition_id
        JOIN Stadium s ON s.stadium_id = m.stadium_id
        WHERE m.match_id = %s
    """, (match_id,))
    match_info = cur.fetchone()
    cur.close()
    return render_template("manager/submit_squad.html",
                           match_id=match_id, players=players, match_info=match_info)


@app.route("/manager/standings")
@role_required("Manager")
def manager_standings():
    comp_id = request.args.get("competition_id")
    pid     = session["person_id"]
    db      = get_db()
    cur     = db.cursor(dictionary=True)

    cur.execute("""
        SELECT DISTINCT comp.competition_id, comp.name, comp.season
        FROM Competition comp
        JOIN `Match` m ON m.competition_id = comp.competition_id
        WHERE comp.competition_type = 'League'
          AND (m.home_club_id IN (SELECT club_id FROM Club WHERE manager_id = %s)
            OR m.away_club_id IN (SELECT club_id FROM Club WHERE manager_id = %s))
        ORDER BY comp.name
    """, (pid, pid))
    competitions = cur.fetchall()

    standings = []
    if comp_id:
        cur.execute("""
            SELECT
                c.club_name,
                COUNT(*) AS played,
                SUM(CASE
                    WHEN (m.home_club_id = c.club_id AND m.home_goals > m.away_goals)
                      OR (m.away_club_id = c.club_id AND m.away_goals > m.home_goals)
                    THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN m.home_goals = m.away_goals THEN 1 ELSE 0 END) AS draws,
                SUM(CASE
                    WHEN (m.home_club_id = c.club_id AND m.home_goals < m.away_goals)
                      OR (m.away_club_id = c.club_id AND m.away_goals < m.home_goals)
                    THEN 1 ELSE 0 END) AS losses,
                SUM(CASE WHEN m.home_club_id = c.club_id THEN m.home_goals ELSE m.away_goals END) AS gf,
                SUM(CASE WHEN m.home_club_id = c.club_id THEN m.away_goals ELSE m.home_goals END) AS ga,
                SUM(CASE WHEN m.home_club_id = c.club_id THEN m.home_goals - m.away_goals
                         ELSE m.away_goals - m.home_goals END) AS gd,
                SUM(CASE
                    WHEN (m.home_club_id = c.club_id AND m.home_goals > m.away_goals)
                      OR (m.away_club_id = c.club_id AND m.away_goals > m.home_goals)
                    THEN 3
                    WHEN m.home_goals = m.away_goals THEN 1
                    ELSE 0 END) AS points
            FROM Club c
            JOIN `Match` m ON (m.home_club_id = c.club_id OR m.away_club_id = c.club_id)
            WHERE m.competition_id = %s AND m.is_completed = 1
            GROUP BY c.club_id, c.club_name
            ORDER BY points DESC, gd DESC
        """, (comp_id,))
        standings = cur.fetchall()

    cur.close()
    return render_template("manager/standings.html",
                           competitions=competitions,
                           standings=standings,
                           selected_comp=comp_id)


@app.route("/manager/leaderboard")
@role_required("Manager")
def manager_leaderboard():
    comp_id  = request.args.get("competition_id")
    category = request.args.get("category", "goals")  # goals | assists | rating
    pid      = session["person_id"]
    db       = get_db()
    cur      = db.cursor(dictionary=True)

    cur.execute("SELECT competition_id, name, season FROM Competition ORDER BY name")
    competitions = cur.fetchall()

    leaders = []
    if comp_id:
        if category == "goals":
            metric_col = "SUM(l.goals)"
            label      = "Goals"
        elif category == "assists":
            metric_col = "SUM(l.assists)"
            label      = "Assists"
        else:
            metric_col = "AVG(l.rating)"
            label      = "Avg Rating"

        cur.execute(f"""
            SELECT CONCAT(pe.name,' ',pe.surname) AS player_name,
                   c.club_name,
                   COUNT(*) AS matches_played,
                   ROUND({metric_col}, 2) AS metric
            FROM Lineup l
            JOIN `Match` m       ON m.match_id = l.match_id
            JOIN Person pe       ON pe.person_id = l.player_id
            LEFT JOIN Contract ct ON ct.player_id = l.player_id
                AND ct.contract_type = 'Permanent'
                AND CURDATE() BETWEEN ct.start_date AND ct.end_date
            LEFT JOIN Club c     ON c.club_id = ct.club_id
            WHERE m.competition_id = %s
            GROUP BY l.player_id, pe.name, pe.surname, c.club_name
            HAVING COUNT(*) >= 3
            ORDER BY metric DESC
            LIMIT 10
        """, (comp_id,))
        leaders = cur.fetchall()

    cur.close()
    return render_template("manager/leaderboard.html",
                           competitions=competitions,
                           leaders=leaders,
                           selected_comp=comp_id,
                           category=category)


# ─────────────────────────────────────────────────────────────────────────────
# REFEREE ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/referee")
@role_required("Referee")
def referee_home():
    pid = session["person_id"]
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT pe.name, pe.surname, pe.nationality,
               TIMESTAMPDIFF(YEAR, pe.date_of_birth, CURDATE()) AS age,
               r.license_level, r.years_of_experience
        FROM Person pe
        JOIN Referee r ON r.person_id = pe.person_id
        WHERE pe.person_id = %s
    """, (pid,))
    profile = cur.fetchone()

    # Career stats
    cur.execute("""
        SELECT COUNT(*) AS total_matches,
               SUM(l.yellow_cards) AS total_yellows,
               SUM(l.red_cards)    AS total_reds
        FROM `Match` m
        LEFT JOIN Lineup l ON l.match_id = m.match_id
        WHERE m.referee_id = %s AND m.is_completed = 1
    """, (pid,))
    stats = cur.fetchone()
    cur.close()
    return render_template("referee/home.html", profile=profile, stats=stats)


@app.route("/referee/match_history")
@role_required("Referee")
def referee_match_history():
    pid = session["person_id"]
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT m.match_id, m.match_datetime, m.is_completed,
               comp.name AS competition, s.stadium_name, m.attendance,
               m.home_goals, m.away_goals,
               ch.club_name AS home_club, ca.club_name AS away_club,
               SUM(l.yellow_cards) AS yellows,
               SUM(l.red_cards)    AS reds,
               (m.match_datetime <= NOW()) AS is_past
        FROM `Match` m
        JOIN Competition comp ON comp.competition_id = m.competition_id
        JOIN Stadium s        ON s.stadium_id = m.stadium_id
        JOIN Club ch          ON ch.club_id = m.home_club_id
        JOIN Club ca          ON ca.club_id = m.away_club_id
        LEFT JOIN Lineup l    ON l.match_id = m.match_id
        WHERE m.referee_id = %s
        GROUP BY m.match_id
        ORDER BY m.match_datetime DESC
    """, (pid,))
    matches = cur.fetchall()
    cur.close()
    return render_template("referee/match_history.html", matches=matches)


@app.route("/referee/submit_result/<int:match_id>", methods=["GET", "POST"])
@role_required("Referee")
def referee_submit_result(match_id):
    pid = session["person_id"]
    db  = get_db()

    if request.method == "POST":
        home_goals = request.form.get("home_goals")
        away_goals = request.form.get("away_goals")
        attendance = request.form.get("attendance")
        cur = db.cursor()
        try:
            cur.callproc("submit_match_result",
                         [match_id, pid, home_goals, away_goals, attendance])
            db.commit()
            flash("Match result submitted.", "success")
        except mysql.connector.Error as err:
            db.rollback()
            flash(f"Could not submit result: {friendly_error(err)}", "danger")
        finally:
            cur.close()
        return redirect(url_for("referee_match_history"))

    # GET – load lineup for stat input
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT l.player_id, CONCAT(p.name,' ',p.surname) AS full_name,
               l.is_starter, l.minutes_played, l.goals, l.assists,
               l.yellow_cards, l.red_cards, l.rating, l.position_in_match
        FROM Lineup l
        JOIN Person p ON p.person_id = l.player_id
        WHERE l.match_id = %s
        ORDER BY l.is_starter DESC, p.surname
    """, (match_id,))
    lineup = cur.fetchall()
    cur.execute("""
        SELECT ch.club_name AS home_club, ca.club_name AS away_club,
               m.match_datetime, m.home_goals, m.away_goals,
               m.is_completed, s.stadium_name, comp.name AS competition
        FROM `Match` m
        JOIN Club ch ON ch.club_id = m.home_club_id
        JOIN Club ca ON ca.club_id = m.away_club_id
        JOIN Stadium s ON s.stadium_id = m.stadium_id
        JOIN Competition comp ON comp.competition_id = m.competition_id
        WHERE m.match_id = %s
    """, (match_id,))
    match_info = cur.fetchone()
    cur.close()
    return render_template("referee/submit_result.html",
                           match_id=match_id, lineup=lineup, match_info=match_info)


# ─────────────────────────────────────────────────────────────────────────────
# REFEREE – update per-player stats after result is submitted
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/referee/update_player_stat/<int:match_id>/<int:player_id>", methods=["POST"])
@role_required("Referee")
def referee_update_player_stat(match_id, player_id):
    pid = session["person_id"]
    db  = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT referee_id FROM `Match` WHERE match_id = %s", (match_id,))
    row = cur.fetchone()
    if not row or row["referee_id"] != pid:
        flash("You are not the assigned referee for this match.", "danger")
        cur.close()
        return redirect(url_for("referee_match_history"))

    minutes  = request.form.get("minutes_played", 90)
    goals    = request.form.get("goals", 0)
    assists  = request.form.get("assists", 0)
    yc       = request.form.get("yellow_cards", 0)
    rc       = request.form.get("red_cards", 0)
    rating   = request.form.get("rating", 6.0)
    position = request.form.get("position_in_match", "TBD").strip()

    try:
        cur.execute("""
            UPDATE Lineup
            SET minutes_played   = %s,
                goals            = %s,
                assists          = %s,
                yellow_cards     = %s,
                red_cards        = %s,
                rating           = %s,
                position_in_match = %s
            WHERE match_id = %s AND player_id = %s
        """, (minutes, goals, assists, yc, rc, rating, position, match_id, player_id))
        db.commit()
        flash("Player stats updated.", "success")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Could not update player stats: {friendly_error(err)}", "danger")
    finally:
        cur.close()

    return redirect(url_for("referee_submit_result", match_id=match_id))


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
