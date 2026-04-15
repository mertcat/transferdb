# TransferDB – Setup & Run Guide
## CMPE 321 Spring 2026

---

## Prerequisites
- Python 3.10+
- MySQL 8.0+

---

## 1. Database Setup

```sql
-- Run as MySQL root:
CREATE DATABASE transferdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'transferdb_user'@'localhost' IDENTIFIED BY 'your_db_password';
GRANT ALL PRIVILEGES ON transferdb.* TO 'transferdb_user'@'localhost';
FLUSH PRIVILEGES;
```

Then load the SQL files **in order**:

```bash
mysql -u transferdb_user -p transferdb < sql/01_schema.sql
mysql -u transferdb_user -p transferdb < sql/02_triggers.sql
mysql -u transferdb_user -p transferdb < sql/03_procedures.sql
```

---

## 2. Python Environment

```bash
pip install -r requirements.txt
```

Edit `app.py` → `DB_CONFIG` to match your MySQL credentials.

---

## 3. Run the Application

```bash
python app.py
```

Open http://127.0.0.1:5000

---

## 4. First Login

Register a **DatabaseManager** account via `/signup`.
Then use that account to add stadiums, clubs, players, etc.

---

## File Structure

```
transferdb/
├── app.py                    ← Flask backend (all routes, security)
├── requirements.txt
├── sql/
│   ├── 01_schema.sql         ← CREATE TABLE statements
│   ├── 02_triggers.sql       ← All DB-level constraint triggers
│   └── 03_procedures.sql     ← Stored procedures
└── templates/
    ├── base.html             ← Shared layout + nav
    ├── login.html
    ├── signup.html
    ├── dbm/                  ← Database Manager views
    ├── player/               ← Player views
    ├── manager/              ← Club Manager views
    └── referee/              ← Referee views
```

---

## Security Checklist

| Requirement | Implementation |
|---|---|
| Password policy (8+, A-Z, a-z, 0-9, special) | `validate_password()` in app.py |
| Bcrypt hashing | `hash_password()` / `check_password()` in app.py |
| SQL Injection prevention | All queries use `%s` parameterized placeholders |
| No ORM | Raw SQL strings passed to `mysql-connector` cursor |
| DB-level constraints | Triggers in `02_triggers.sql` |

---

## DB-Level Constraints Enforced by Triggers

| Rule | Trigger |
|---|---|
| 120-min overlap (stadium/referee/clubs) | `trg_match_no_overlap` |
| Match must be in the future | `trg_match_no_overlap` |
| Max 11 starters per match | `trg_lineup_starter_limit` |
| Max 23 players per squad | `trg_lineup_starter_limit` |
| Attendance ≤ capacity | `trg_match_attendance_capacity` |
| Max 1 Permanent + 1 Loan contract | `trg_contract_rules` |
| Loan requires active Permanent elsewhere | `trg_contract_rules` |
| One manager per club | `trg_club_manager_unique` |
| Loaned player can't play for parent club | `trg_no_loan_parent_play` |

Stored Procedures (`03_procedures.sql`) additionally enforce:
- `schedule_match` – wraps match insert in a transaction
- `register_transfer` – auto-terminates old Permanent on new Permanent transfer; updates market value on Purchase
- `submit_match_result` – verifies caller is assigned referee & match time has passed
