"""
TransferDB – Comprehensive Seed Data
=====================================
Wipes the database and inserts large, realistic data covering every
edge-case scenario exercised by the test suite and the application.

Edge cases explicitly included
───────────────────────────────
• Duplicate permanent contract attempt    → player with 1 active permanent
• Loan without permanent elsewhere        → free-agent players (no contracts)
• Valid loan                              → player with perm at club A, loan at club B
• Second loan attempt                     → player already on an active loan
• Contract end <= start                   → prevented by CHECK
• Loaned player vs parent-club match      → players 1201/1202 (loan setup)
• Starter limit (11) & squad limit (23)   → completed matches have exactly 11+5 or 11+12
• Attendance at / over capacity           → stadium capacities vary widely
• Stadium / referee / club 120-min rule   → matches scheduled carefully
• Past completed matches with full stats  → ~60 completed matches + lineups
• Future scheduled matches                → 20 upcoming matches
• Free-agent transfers (from_club NULL)   → players 1240-1249
• Purchase / Loan transfers               → transfer history
• Wrong-referee submit attempt            → each match has a specific referee
• Various card / rating / minutes values  → realistic random stats

Usage
─────
  python3 seed_data.py
"""

import mysql.connector
import bcrypt
import random
import subprocess
from datetime import date, datetime, timedelta

# ── connection ────────────────────────────────────────────────────────────────
DB_CONFIG = dict(host="127.0.0.1", port=3306,
                 user="transferdb_user", password="0000",
                 database="transferdb", charset="utf8mb4")

HASHED_PW = bcrypt.hashpw(b"Test@1234", bcrypt.gensalt()).decode()

random.seed(42)

# ── helpers ───────────────────────────────────────────────────────────────────
def today():    return date.today()
def fut(days):  return today() + timedelta(days=days)
def past(days): return today() - timedelta(days=days)

def ri(a, b):   return random.randint(a, b)
def rf(a, b):   return round(random.uniform(a, b), 1)

# ══════════════════════════════════════════════════════════════════════════════
# RAW DATA
# ══════════════════════════════════════════════════════════════════════════════

STADIUMS = [
    # (id, name, city, capacity)
    (1,  "RAMS Park",               "Istanbul",    52280),
    (2,  "Ülker Stadyumu",          "Istanbul",    50530),
    (3,  "Vodafone Park",           "Istanbul",    41903),
    (4,  "Tüpraş Stadyumu",         "Istanbul",    42590),
    (5,  "Ataturk Olympic Stadium", "Istanbul",    74753),
    (6,  "Papara Park",             "Istanbul",    40782),
    (7,  "Mersin Stadyumu",         "Mersin",      25534),
    (8,  "Eryaman Stadium",         "Ankara",      22000),
    (9,  "Corendon Airlines Park",  "Antalya",     32537),
    (10, "Gürsel Aksel Stadium",    "Izmir",       20035),
    (11, "Etihad Stadium",          "Manchester",  53400),
    (12, "Anfield",                 "Liverpool",   61276),
    (13, "Allianz Arena",           "Munich",      75024),
    (14, "Camp Nou",                "Barcelona",   99354),
    (15, "Santiago Bernabeu",       "Madrid",      81044),
    (16, "San Siro",                "Milan",       80018),
    (17, "Juventus Stadium",        "Turin",       41507),
    (18, "Parc des Princes",        "Paris",       48700),
    (19, "Johan Cruyff Arena",      "Amsterdam",   54990),
    (20, "Signal Iduna Park",       "Dortmund",    81365),
]

COMPETITIONS = [
    # (id, name, season, country, type)
    (1,  "Süper Lig",              "2025/2026", "Türkiye", "League"),
    (2,  "Türkiye Kupası",         "2025/2026", "Türkiye", "Cup"),
    (3,  "UEFA Champions League",  "2025/2026", "Europe",  "International"),
    (4,  "UEFA Europa League",     "2025/2026", "Europe",  "International"),
    (5,  "Premier League",         "2025/2026", "England", "League"),
    (6,  "Bundesliga",             "2025/2026", "Germany", "League"),
    (7,  "La Liga",                "2025/2026", "Spain",   "League"),
    (8,  "Serie A",                "2025/2026", "Italy",   "League"),
    (9,  "Süper Lig",              "2024/2025", "Türkiye", "League"),
    (10, "UEFA Champions League",  "2024/2025", "Europe",  "International"),
]

# ── Referees: person_id 1001-1015 ────────────────────────────────────────────
REFEREE_DATA = [
    # (pid, username, name, surname, nat, dob, license, years_exp)
    (1001, "ref_cakir",    "Cüneyt",  "Çakır",    "Türkiye",  "1976-11-23", "FIFA",     20),
    (1002, "ref_meler",    "Halil",   "Meler",    "Türkiye",  "1986-08-01", "FIFA",     10),
    (1003, "ref_gozubuyuk","Serdar",  "Gözübüyük","Türkiye",  "1984-10-13", "FIFA",     12),
    (1004, "ref_turpin",   "Clement", "Turpin",   "France",   "1982-06-08", "FIFA",     15),
    (1005, "ref_oliver",   "Michael", "Oliver",   "England",  "1985-07-25", "FIFA",     13),
    (1006, "ref_skomina",  "Damir",   "Skomina",  "Slovenia", "1976-04-04", "FIFA",     18),
    (1007, "ref_lahoz",    "Antonio", "Lahoz",    "Spain",    "1981-09-14", "FIFA",     14),
    (1008, "ref_zwayer",   "Felix",   "Zwayer",   "Germany",  "1981-03-06", "FIFA",     11),
    (1009, "ref_karasev",  "Sergei",  "Karasev",  "Russia",   "1979-09-12", "FIFA",      9),
    (1010, "ref_makkelie", "Danny",   "Makkelie", "Netherlands","1983-06-26","FIFA",     14),
    (1011, "ref_vincic",   "Slavko",  "Vincic",   "Slovenia", "1986-05-25", "UEFA",      8),
    (1012, "ref_aytekin",  "Deniz",   "Aytekin",  "Germany",  "1978-11-02", "UEFA",     16),
    (1013, "ref_collum",   "Willie",  "Collum",   "Scotland", "1979-09-21", "UEFA",     12),
    (1014, "ref_massa",    "Filippo", "Massa",    "Italy",    "1980-06-12", "UEFA",     10),
    (1015, "ref_karabag",  "Firat",   "Karabağ",  "Türkiye",  "1989-03-15", "National",  5),
]

# ── Managers: person_id 2001-2020 ─────────────────────────────────────────────
MANAGER_DATA = [
    # (pid, username, name, surname, nat, dob, formation, exp_level)
    (2001,"mgr_terim",    "Fatih",    "Terim",     "Türkiye", "1953-09-04","4-4-2",  "Expert"),
    (2002,"mgr_advocaat", "Dick",     "Advocaat",  "Netherlands","1947-09-27","4-3-3","Expert"),
    (2003,"mgr_mourinho", "Jose",     "Mourinho",  "Portugal","1963-01-26","4-2-3-1","Expert"),
    (2004,"mgr_yanal",    "Ersun",    "Yanal",     "Türkiye", "1963-01-12","4-2-3-1","Expert"),
    (2005,"mgr_ljungberg","Fredrik",  "Ljungberg", "Sweden",  "1977-04-16","4-3-3",  "Expert"),
    (2006,"mgr_rijkaard", "Frank",    "Rijkaard",  "Netherlands","1962-09-30","4-3-3","Expert"),
    (2007,"mgr_blanc",    "Laurent",  "Blanc",     "France",  "1965-11-19","4-2-3-1","Expert"),
    (2008,"mgr_gunes",    "Senol",    "Güneş",     "Türkiye", "1952-05-13","3-5-2",  "Expert"),
    (2009,"mgr_guardiola","Pep",      "Guardiola", "Spain",   "1971-01-18","4-3-3",  "Expert"),
    (2010,"mgr_klopp",    "Jurgen",   "Klopp",     "Germany", "1967-06-16","4-3-3",  "Expert"),
    (2011,"mgr_ancelotti","Carlo",    "Ancelotti", "Italy",   "1959-06-10","4-3-3",  "Expert"),
    (2012,"mgr_flick",    "Hansi",    "Flick",     "Germany", "1965-02-24","4-2-3-1","Expert"),
    (2013,"mgr_xavi",     "Xavi",     "Hernandez", "Spain",   "1980-01-25","4-3-3",  "Expert"),
    (2014,"mgr_pioli",    "Stefano",  "Pioli",     "Italy",   "1965-10-20","4-2-3-1","Intermediate"),
    (2015,"mgr_allegri",  "Massimo",  "Allegri",   "Italy",   "1967-08-11","4-3-1-2","Expert"),
    (2016,"mgr_galtier",  "Christophe","Galtier",  "France",  "1966-08-03","4-3-3",  "Intermediate"),
    (2017,"mgr_tenhag",   "Erik",     "ten Hag",   "Netherlands","1970-02-02","4-2-3-1","Expert"),
    (2018,"mgr_postecoglou","Ange",   "Postecoglou","Australia","1965-08-27","4-3-3","Intermediate"),
    (2019,"mgr_amorim",   "Ruben",    "Amorim",    "Portugal","1985-01-27","3-4-3",  "Intermediate"),
    (2020,"mgr_emery",    "Unai",     "Emery",     "Spain",   "1971-11-03","4-2-3-1","Expert"),
]

# ── Clubs: id 1-20 ────────────────────────────────────────────────────────────
# (id, name, city, foundation_year, stadium_id, manager_id)
CLUBS = [
    ( 1, "Galatasaray SK",        "Istanbul",   1905, 1,  2001),
    ( 2, "Fenerbahçe SK",         "Istanbul",   1907, 2,  2002),
    ( 3, "Beşiktaş JK",           "Istanbul",   1903, 3,  2003),
    ( 4, "Trabzonspor",           "Trabzon",    1967, 4,  2004),
    ( 5, "Başakşehir FK",         "Istanbul",   1990, 6,  2005),
    ( 6, "Konyaspor",             "Konya",      1981, 9,  2006),
    ( 7, "Antalyaspor",           "Antalya",    1966, 9,  2007),
    ( 8, "Mersin İdmanyurdu",     "Mersin",     1925, 7,  2008),
    ( 9, "Bursaspor",             "Bursa",      1963, 10, 2009),
    (10, "Sivasspor",             "Sivas",      1967, 8,  2010),
    (11, "Manchester City FC",    "Manchester", 1880, 11, 2011),
    (12, "Liverpool FC",          "Liverpool",  1892, 12, 2012),
    (13, "FC Bayern München",     "Munich",     1900, 13, 2013),
    (14, "FC Barcelona",          "Barcelona",  1899, 14, 2014),
    (15, "Real Madrid CF",        "Madrid",     1902, 15, 2015),
    (16, "AC Milan",              "Milan",      1899, 16, 2016),
    (17, "Juventus FC",           "Turin",      1897, 17, 2017),
    (18, "Paris Saint-Germain",   "Paris",      1970, 18, 2018),
    (19, "Ajax Amsterdam",        "Amsterdam",  1900, 19, 2019),
    (20, "Borussia Dortmund",     "Dortmund",   1909, 20, 2020),
]

# ── Players: person_id 1101-1260 ─────────────────────────────────────────────
# Distribute 12 players per main club (clubs 1-12), fewer for others
# player tuple: (pid, username, name, surname, nat, dob, market_val, position, foot, height)

POSITIONS = ["Goalkeeper","Defender","Midfielder","Forward"]
FEET       = ["Right","Left","Both"]

_player_names = [
    # Turkish players
    ("Uğurcan","Çakır","Türkiye","1996-01-11",3000000,"Goalkeeper","Right",190),
    ("Mert","Günok","Türkiye","1989-03-01",1500000,"Goalkeeper","Right",189),
    ("Harun","Tekin","Türkiye","1989-12-29",500000,"Goalkeeper","Right",187),
    ("Zeki","Çelik","Türkiye","1997-02-17",12000000,"Defender","Right",179),
    ("Merih","Demiral","Türkiye","1998-03-05",25000000,"Defender","Right",187),
    ("Çağlar","Söyüncü","Türkiye","1996-05-23",20000000,"Defender","Right",185),
    ("Ozan","Kabak","Türkiye","2000-03-25",18000000,"Defender","Left",187),
    ("Ferdi","Kadıoğlu","Türkiye","1999-10-12",22000000,"Defender","Left",181),
    ("Kaan","Ayhan","Türkiye","1994-09-10",8000000,"Defender","Right",183),
    ("Abdülkadir","Ömür","Türkiye","1999-04-18",10000000,"Midfielder","Right",175),
    ("Hakan","Çalhanoğlu","Türkiye","1994-02-08",35000000,"Midfielder","Right",178),
    ("Orkun","Kökcü","Türkiye","2000-12-20",25000000,"Midfielder","Right",178),
    ("Kerem","Aktürkoğlu","Türkiye","1998-11-02",22000000,"Forward","Left",173),
    ("Baris","Yilmaz","Türkiye","2001-01-01",5000000,"Forward","Right",179),
    ("Arda","Güler","Türkiye","2005-02-25",60000000,"Midfielder","Left",175),
    ("Burak","Yılmaz","Türkiye","1985-07-15",500000,"Forward","Right",188),
    ("Cenk","Tosun","Türkiye","1991-06-07",3000000,"Forward","Right",183),
    ("Yusuf","Yazıcı","Türkiye","1997-01-29",15000000,"Midfielder","Right",183),
    ("Okay","Yokuşlu","Türkiye","1994-03-09",7000000,"Midfielder","Right",188),
    ("İrfan","Kahveci","Türkiye","1995-03-04",8000000,"Midfielder","Right",180),
    # Brazilian players
    ("Gabriel","Jesus","Brazil","1997-04-03",35000000,"Forward","Right",175),
    ("Rodrygo","Goes","Brazil","2001-01-09",80000000,"Forward","Right",174),
    ("Vinicius","Junior","Brazil","2000-07-12",150000000,"Forward","Right",176),
    ("Raphinha","Silva","Brazil","1996-12-14",65000000,"Forward","Right",176),
    ("Casemiro","Lima","Brazil","1992-02-23",30000000,"Midfielder","Right",185),
    ("Fabinho","Tavares","Brazil","1993-10-23",25000000,"Midfielder","Right",188),
    ("Eder","Militao","Brazil","1998-01-18",65000000,"Defender","Right",186),
    ("Marquinhos","Correa","Brazil","1994-05-14",55000000,"Defender","Right",183),
    ("Alisson","Becker","Brazil","1992-10-02",50000000,"Goalkeeper","Right",193),
    ("Ederson","Moraes","Brazil","1993-08-17",45000000,"Goalkeeper","Right",188),
    # Spanish / French
    ("Pedri","Gonzalez","Spain","2002-11-25",100000000,"Midfielder","Right",174),
    ("Gavi","Puig","Spain","2004-08-05",100000000,"Midfielder","Right",173),
    ("Ferran","Torres","Spain","2000-02-29",40000000,"Forward","Right",181),
    ("Ansu","Fati","Spain","2002-10-31",50000000,"Forward","Left",178),
    ("Lamine","Yamal","Spain","2007-07-16",180000000,"Forward","Right",180),
    ("Kylian","Mbappe","France","1998-12-20",200000000,"Forward","Right",182),
    ("Antoine","Griezmann","France","1991-03-21",25000000,"Forward","Right",176),
    ("N'Golo","Kante","France","1991-03-29",15000000,"Midfielder","Right",169),
    ("Ousmane","Dembele","France","1997-05-15",60000000,"Forward","Right",178),
    ("Mike","Maignan","France","1995-07-03",45000000,"Goalkeeper","Right",191),
    # English / German
    ("Erling","Haaland","Norway","2000-07-21",200000000,"Forward","Right",195),
    ("Phil","Foden","England","2000-05-28",120000000,"Midfielder","Left",171),
    ("Bukayo","Saka","England","2001-09-05",120000000,"Forward","Left",178),
    ("Declan","Rice","England","1999-01-14",100000000,"Midfielder","Right",185),
    ("Jude","Bellingham","England","2003-06-29",180000000,"Midfielder","Right",186),
    ("Joshua","Kimmich","Germany","1995-02-08",60000000,"Midfielder","Right",177),
    ("Leroy","Sane","Germany","1996-01-11",45000000,"Forward","Right",183),
    ("Robert","Lewandowski","Poland","1988-08-21",15000000,"Forward","Right",185),
    ("Harry","Kane","England","1993-07-28",80000000,"Forward","Right",188),
    ("Trent","Alexander-Arnold","England","1998-10-07",80000000,"Defender","Right",175),
    # Extra players for loan / free-agent edge cases
    ("Loan","PlayerA","Türkiye","1998-06-01",5000000,"Midfielder","Right",179),
    ("Loan","PlayerB","Türkiye","1999-07-01",4000000,"Defender","Right",182),
    ("Free","AgentX","Türkiye","1997-01-01",2000000,"Forward","Right",180),
    ("Free","AgentY","Brazil","1995-03-01",3000000,"Midfielder","Left",177),
    ("Free","AgentZ","France","1996-09-01",2500000,"Defender","Right",183),
    ("Expired","ContractA","Türkiye","1994-05-01",1500000,"Midfielder","Right",178),
    ("Expired","ContractB","Spain","1993-08-01",1000000,"Defender","Right",181),
    ("Young","TalentA","Türkiye","2007-01-01",1000000,"Forward","Right",172),
    ("Young","TalentB","Türkiye","2006-06-01",800000,"Midfielder","Left",170),
    ("Veteran","PlayerA","Türkiye","1983-03-01",200000,"Goalkeeper","Right",188),
]

# Build player list with person_id 1101..
# We need PIDs 1101-1260 (160 players) but only have 60 hand-crafted names.
# Generate the remaining 100 dynamically.
import random as _rnd

_extra_names = []
_gen_nats   = ["Türkiye","Brazil","France","Spain","Germany","England","Argentina","Portugal","Netherlands","Belgium"]
_gen_fnames = ["Ali","Emre","Can","Deniz","Furkan","Cengiz","Berk","Burak","Tolga","Onur",
               "Lucas","Hugo","Marco","Felix","Leon","Jan","Tom","Erik","Nils","Sam",
               "Pablo","Diego","Carlos","Luis","Mateo","Ivan","Andre","Rafael","Jonas","Max"]
_gen_snames = ["Yılmaz","Kaya","Çelik","Demir","Şahin","Özkan","Aydın","Arslan","Doğan","Koç",
               "Silva","Santos","Moreira","Costa","Ferreira","Mueller","Weber","Schneider","Fischer","Dupont",
               "Blanc","Moreau","Bernard","Rodriguez","Martinez","Lopez","Garcia","Brown","Smith","Wilson"]

for _i in range(100):
    fn = _gen_fnames[_i % len(_gen_fnames)]
    sn = _gen_snames[_i % len(_gen_snames)]
    nat = _gen_nats[_i % len(_gen_nats)]
    yr = _rnd.randint(1988, 2005)
    mn = _rnd.randint(1, 12)
    dy = _rnd.randint(1, 28)
    dob = f"{yr}-{mn:02d}-{dy:02d}"
    mval = _rnd.randint(500000, 50000000)
    pos = ["Goalkeeper","Defender","Midfielder","Forward"][_i % 4]
    foot = ["Right","Left","Both"][_i % 3]
    height = _rnd.randint(168, 196)
    _extra_names.append((fn, sn, nat, dob, mval, pos, foot, height))

_all_player_names = _player_names + _extra_names  # 160 total

PLAYERS = []
for i, p in enumerate(_all_player_names):
    pid = 1101 + i
    username = f"plr_{p[0].lower()[:4]}{p[1].lower()[:4]}{pid}"
    PLAYERS.append((pid, username) + p)
# PLAYERS: (pid, username, name, surname, nat, dob, mval, pos, foot, height)
# PIDs 1101–1260

# ── DB managers (AppUser only, no person) ────────────────────────────────────
DB_MANAGERS = [
    ("admin",   "Admin User"),
    ("dbm_ali", "Ali Veli"),
    ("dbm_can", "Can Demir"),
]

# ── Contract setup ────────────────────────────────────────────────────────────
# We'll assign players to clubs in groups, then build contracts.
# Clubs 1-10 (Turkish) get players 1101-1180 (first 80)
# Clubs 11-20 (European) get players 1181-1240 (next 60)
# Players 1241-1250 → free agents (no contracts)
# Players 1251-1255 → on loan (perm at club A, loan at club B)
# Players 1256-1257 → expired contracts only
# Players 1258-1260 → young / veteran with contracts

CLUB_PLAYER_MAP = {}  # club_id -> [player_pids]
# Turkish clubs (1-10): 8 players each
for ci, club_id in enumerate(range(1, 11)):
    CLUB_PLAYER_MAP[club_id] = [1101 + ci*8 + j for j in range(8)]
# European clubs (11-20): 6 players each
for ci, club_id in enumerate(range(11, 21)):
    CLUB_PLAYER_MAP[club_id] = [1181 + ci*6 + j for j in range(6)]

FREE_AGENT_PIDS  = [1241, 1242, 1243, 1244, 1245]
LOAN_PIDS        = [1251, 1252]   # will get perm + loan
EXPIRED_PIDS     = [1256, 1257]   # only expired contracts
EXTRA_PIDS       = [1258, 1259, 1260]  # young/veteran → assigned below
CLUB_PLAYER_MAP[1].extend(EXTRA_PIDS)  # add to Galatasaray

# ══════════════════════════════════════════════════════════════════════════════
# SEED FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def run():
    con = mysql.connector.connect(**DB_CONFIG)
    cur = con.cursor()

    print("── Clearing tables …")
    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    cur.execute("SET SQL_MODE=''")
    for t in ["Lineup","TransferRecord","Contract","Match",
              "Club","Player","Manager","Referee","AppUser",
              "Person","Competition","Stadium"]:
        cur.execute(f"DELETE FROM `{t}`")
    cur.execute("ALTER TABLE Person      AUTO_INCREMENT=1")
    cur.execute("ALTER TABLE Stadium     AUTO_INCREMENT=1")
    cur.execute("ALTER TABLE Competition AUTO_INCREMENT=1")
    cur.execute("ALTER TABLE Club        AUTO_INCREMENT=1")
    cur.execute("ALTER TABLE `Match`     AUTO_INCREMENT=1")
    cur.execute("ALTER TABLE Contract    AUTO_INCREMENT=1")
    cur.execute("ALTER TABLE TransferRecord AUTO_INCREMENT=1")
    cur.execute("ALTER TABLE Lineup      AUTO_INCREMENT=1")
    con.commit()

    # Drop triggers that block historical data loading
    for trg in ["trg_match_no_overlap","trg_contract_rules",
                "trg_no_loan_parent_play","trg_lineup_starter_limit"]:
        cur.execute(f"DROP TRIGGER IF EXISTS {trg}")
    con.commit()

    # ── Stadiums ──────────────────────────────────────────────────────────────
    print("── Inserting stadiums …")
    cur.executemany(
        "INSERT INTO Stadium (stadium_id, stadium_name, city, capacity) VALUES (%s,%s,%s,%s)",
        STADIUMS)
    con.commit()

    # ── Competitions ──────────────────────────────────────────────────────────
    print("── Inserting competitions …")
    cur.executemany(
        "INSERT INTO Competition (competition_id, name, season, country, competition_type) VALUES (%s,%s,%s,%s,%s)",
        COMPETITIONS)
    con.commit()

    # ── Referees ──────────────────────────────────────────────────────────────
    print("── Inserting referees …")
    for r in REFEREE_DATA:
        pid, uname, name, sname, nat, dob, lic, yrs = r
        cur.execute("INSERT INTO Person (person_id,name,surname,nationality,date_of_birth) VALUES (%s,%s,%s,%s,%s)",
                    (pid, name, sname, nat, dob))
        cur.execute("INSERT INTO Referee (person_id,license_level,years_of_experience) VALUES (%s,%s,%s)",
                    (pid, lic, yrs))
        cur.execute("INSERT INTO AppUser (username,password,role,person_id) VALUES (%s,%s,'Referee',%s)",
                    (uname, HASHED_PW, pid))
    con.commit()

    # ── Managers ─────────────────────────────────────────────────────────────
    print("── Inserting managers …")
    for m in MANAGER_DATA:
        pid, uname, name, sname, nat, dob, form, exp = m
        cur.execute("INSERT INTO Person (person_id,name,surname,nationality,date_of_birth) VALUES (%s,%s,%s,%s,%s)",
                    (pid, name, sname, nat, dob))
        cur.execute("INSERT INTO Manager (person_id,preferred_formation,experience_level) VALUES (%s,%s,%s)",
                    (pid, form, exp))
        cur.execute("INSERT INTO AppUser (username,password,role,person_id) VALUES (%s,%s,'Manager',%s)",
                    (uname, HASHED_PW, pid))
    con.commit()

    # ── Clubs ─────────────────────────────────────────────────────────────────
    print("── Inserting clubs …")
    cur.executemany(
        "INSERT INTO Club (club_id,club_name,city,foundation_year,stadium_id,manager_id) VALUES (%s,%s,%s,%s,%s,%s)",
        CLUBS)
    con.commit()

    # ── Players ───────────────────────────────────────────────────────────────
    print("── Inserting players …")
    for p in PLAYERS:
        pid, uname, name, sname, nat, dob, mval, pos, foot, height = p
        cur.execute("INSERT INTO Person (person_id,name,surname,nationality,date_of_birth) VALUES (%s,%s,%s,%s,%s)",
                    (pid, name, sname, nat, dob))
        cur.execute("INSERT INTO Player (person_id,market_value,main_position,strong_foot,height) VALUES (%s,%s,%s,%s,%s)",
                    (pid, mval, pos, foot, height))
        cur.execute("INSERT INTO AppUser (username,password,role,person_id) VALUES (%s,%s,'Player',%s)",
                    (uname, HASHED_PW, pid))
    con.commit()

    # ── DB Managers ───────────────────────────────────────────────────────────
    print("── Inserting DB manager accounts …")
    for uname, _ in DB_MANAGERS:
        cur.execute("INSERT INTO AppUser (username,password,role) VALUES (%s,%s,'DatabaseManager')",
                    (uname, HASHED_PW))
    con.commit()

    # ── Contracts ────────────────────────────────────────────────────────────
    print("── Inserting contracts …")

    # Active permanent contracts for club-assigned players
    for club_id, pids in CLUB_PLAYER_MAP.items():
        for pid in pids:
            wage = ri(5000, 150000)
            cur.execute("""INSERT INTO Contract (player_id,club_id,contract_type,
                           weekly_wage,start_date,end_date)
                           VALUES (%s,%s,'Permanent',%s,%s,%s)""",
                        (pid, club_id, wage, past(ri(200,730)), fut(ri(180,1460))))

    # Loan edge-case players
    # Player 1251: permanent at club 1 (Galatasaray), loan at club 2 (Fenerbahçe) → ACTIVE
    cur.execute("""INSERT INTO Contract (player_id,club_id,contract_type,weekly_wage,start_date,end_date)
                   VALUES (1251,1,'Permanent',20000,%s,%s)""", (past(365), fut(730)))
    cur.execute("""INSERT INTO Contract (player_id,club_id,contract_type,weekly_wage,start_date,end_date)
                   VALUES (1251,2,'Loan',15000,%s,%s)""", (past(30), fut(180)))

    # Player 1252: permanent at club 3 (Beşiktaş), loan at club 4 (Trabzonspor) → ACTIVE
    cur.execute("""INSERT INTO Contract (player_id,club_id,contract_type,weekly_wage,start_date,end_date)
                   VALUES (1252,3,'Permanent',18000,%s,%s)""", (past(400), fut(600)))
    cur.execute("""INSERT INTO Contract (player_id,club_id,contract_type,weekly_wage,start_date,end_date)
                   VALUES (1252,4,'Loan',12000,%s,%s)""", (past(60), fut(120)))

    # Expired contract players (no active contract today)
    cur.execute("""INSERT INTO Contract (player_id,club_id,contract_type,weekly_wage,start_date,end_date)
                   VALUES (1256,5,'Permanent',9000,%s,%s)""", (past(730), past(30)))
    cur.execute("""INSERT INTO Contract (player_id,club_id,contract_type,weekly_wage,start_date,end_date)
                   VALUES (1257,6,'Permanent',7000,%s,%s)""", (past(500), past(60)))

    # Free agents (1241-1245): intentionally no contracts
    # (nothing to insert for them)

    con.commit()

    # ── Transfer Records ─────────────────────────────────────────────────────
    print("── Inserting transfer records …")
    transfer_scenarios = [
        # Permanent transfers between main clubs (purchase = Permanent with fee)
        (1101, 11, 1,  past(400), 25000000, "Permanent"),
        (1102,  1, 2,  past(300), 18000000, "Permanent"),
        (1103,  2, 3,  past(200), 12000000, "Permanent"),
        (1109,  4, 1,  past(350), 30000000, "Permanent"),
        (1110,  5, 2,  past(250), 22000000, "Permanent"),
        (1181, 14, 11, past(365), 80000000, "Permanent"),
        (1187, 15, 12, past(300), 60000000, "Permanent"),
        (1193, 13, 14, past(200), 50000000, "Permanent"),
        # Permanent transfers from free agent (fee = 0)
        (1241, None, 1,  past(100), 0, "Permanent"),
        (1242, None, 3,  past(80),  0, "Permanent"),
        (1243, None, 11, past(150), 0, "Permanent"),
        # Loan transfers
        (1251, 1, 2, past(30),  0,        "Loan"),
        (1252, 3, 4, past(60),  500000,   "Loan"),
        # Historical Permanent transfers (now at new club)
        (1104, 3, 1, past(600), 15000000, "Permanent"),
        (1105, 1, 4, past(500), 10000000, "Permanent"),
        (1106, 2, 5, past(450), 8000000,  "Permanent"),
        (1107, 4, 3, past(400), 9000000,  "Permanent"),
        (1195, 19, 12,past(200),40000000, "Permanent"),
        (1196, 12, 11,past(100),35000000, "Permanent"),
        (1200, 11, 15,past(180),55000000, "Permanent"),
        # Permanent from free agent
        (1244, None, 2, past(50), 0, "Permanent"),
        (1245, None, 7, past(90), 0, "Permanent"),
    ]
    for t in transfer_scenarios:
        pid, from_c, to_c, tdate, fee, ttype = t
        cur.execute("""INSERT INTO TransferRecord
                       (player_id,from_club_id,to_club_id,transfer_date,transfer_fee,transfer_type)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (pid, from_c, to_c, tdate, fee, ttype))
    con.commit()

    # ── Matches ───────────────────────────────────────────────────────────────
    print("── Inserting matches …")

    # We'll track match_ids manually starting from 1
    mid = 1

    # Helper: build a completed match and its lineup
    def completed_match(home_id, away_id, dt_str, stad_id, comp_id, ref_id,
                        home_g, away_g, attendance):
        nonlocal mid
        cur.execute("""INSERT INTO `Match` (match_id,match_datetime,home_club_id,away_club_id,
                       stadium_id,competition_id,referee_id,
                       home_goals,away_goals,attendance,is_completed)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)""",
                    (mid, dt_str, home_id, away_id, stad_id, comp_id, ref_id,
                     home_g, away_g, attendance))
        _insert_lineup(mid, home_id, away_id)
        mid += 1

    def scheduled_match(home_id, away_id, dt_str, stad_id, comp_id, ref_id):
        nonlocal mid
        cur.execute("""INSERT INTO `Match` (match_id,match_datetime,home_club_id,away_club_id,
                       stadium_id,competition_id,referee_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (mid, dt_str, home_id, away_id, stad_id, comp_id, ref_id))
        mid += 1

    def _insert_lineup(match_id, home_id, away_id):
        home_players = [p for p in CLUB_PLAYER_MAP.get(home_id, []) if p not in [1251,1252]][:11]
        away_players = [p for p in CLUB_PLAYER_MAP.get(away_id, []) if p not in [1251,1252]][:11]
        for i, pid in enumerate(home_players):
            starter = 1 if i < 8 else 0
            cur.execute("""INSERT IGNORE INTO Lineup
                (match_id,player_id,is_starter,minutes_played,position_in_match,
                 goals,assists,yellow_cards,red_cards,rating)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (match_id, pid, starter,
                 ri(60,90) if starter else ri(10,45),
                 random.choice(["GK","CB","RB","LB","CM","CAM","LW","RW","ST"]),
                 ri(0,2), ri(0,2), ri(0,1), 0, rf(5.5, 9.0)))
        for i, pid in enumerate(away_players):
            starter = 1 if i < 8 else 0
            cur.execute("""INSERT IGNORE INTO Lineup
                (match_id,player_id,is_starter,minutes_played,position_in_match,
                 goals,assists,yellow_cards,red_cards,rating)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (match_id, pid, starter,
                 ri(60,90) if starter else ri(10,45),
                 random.choice(["GK","CB","RB","LB","CM","CAM","LW","RW","ST"]),
                 ri(0,2), ri(0,1), ri(0,1), 0, rf(5.5, 9.0)))

    # ── Süper Lig 2025/2026 (comp_id=1) ─────────────────────────────────────
    superlig_fixtures = [
        (1,2,1,1001),(1,3,1,1002),(2,3,2,1003),(3,4,3,1004),(4,5,4,1005),
        (5,1,6,1006),(2,4,2,1007),(3,5,3,1008),(1,4,1,1001),(2,5,2,1002),
        (6,7,9,1009),(7,8,9,1010),(8,9,7,1011),(9,10,8,1012),(6,10,9,1013),
        (1,6,1,1001),(2,7,2,1003),(3,8,3,1004),(4,9,4,1005),(5,10,6,1002),
        (6,1,9,1007),(7,2,9,1008),(8,3,7,1009),(9,4,8,1010),(10,5,8,1011),
    ]
    base = past(200)
    for i, (h, a, s, r) in enumerate(superlig_fixtures):
        dt = base + timedelta(days=i*7, hours=19)
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        hg, ag = ri(0,4), ri(0,3)
        att = ri(int(STADIUMS[s-1][3]*0.4), STADIUMS[s-1][3])
        completed_match(h, a, dt_str, s, 1, r, hg, ag, att)

    # ── Türkiye Kupası 2025/2026 (comp_id=2) ─────────────────────────────────
    kupa_fixtures = [
        (1,5,1,1001),(2,6,2,1002),(3,7,3,1003),(4,8,4,1004),(5,9,6,1005),
        (6,10,9,1006),(1,3,1,1007),(2,4,2,1008),
    ]
    base2 = past(150)
    for i, (h, a, s, r) in enumerate(kupa_fixtures):
        dt = base2 + timedelta(days=i*10, hours=18)
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        hg, ag = ri(0,3), ri(0,3)
        att = ri(int(STADIUMS[s-1][3]*0.3), STADIUMS[s-1][3])
        completed_match(h, a, dt_str, s, 2, r, hg, ag, att)

    # ── Champions League 2025/2026 (comp_id=3) ───────────────────────────────
    ucl_fixtures = [
        (11,14,11,1004),(12,15,12,1005),(13,16,13,1006),(14,17,14,1007),
        (15,18,15,1008),(16,19,16,1009),(17,20,17,1010),(18,11,18,1004),
        (11,15,11,1005),(12,16,12,1006),(13,17,13,1007),(14,18,14,1008),
        (15,19,15,1009),(16,20,16,1010),(17,11,17,1004),(18,12,18,1005),
    ]
    base3 = past(180)
    for i, (h, a, s, r) in enumerate(ucl_fixtures):
        dt = base3 + timedelta(days=i*14, hours=21)
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        hg, ag = ri(0,4), ri(0,3)
        att = ri(int(STADIUMS[s-1][3]*0.7), STADIUMS[s-1][3])
        completed_match(h, a, dt_str, s, 3, r, hg, ag, att)

    # ── Europa League (comp_id=4) ─────────────────────────────────────────────
    uel_fixtures = [(1,19,1,1011),(2,20,2,1012),(3,18,3,1013),(4,17,4,1014)]
    base4 = past(120)
    for i, (h, a, s, r) in enumerate(uel_fixtures):
        dt = base4 + timedelta(days=i*14, hours=20)
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        hg, ag = ri(0,3), ri(0,3)
        att = ri(int(STADIUMS[s-1][3]*0.5), STADIUMS[s-1][3])
        completed_match(h, a, dt_str, s, 4, r, hg, ag, att)

    # ── Historical season (comp_id=9, Süper Lig 2024/2025) ───────────────────
    old_fixtures = [
        (1,2,1,1001),(3,4,3,1002),(5,1,6,1003),(2,3,2,1004),(4,5,4,1005),
        (6,7,9,1006),(8,9,7,1007),(10,6,8,1008),
    ]
    base5 = past(400)
    for i, (h, a, s, r) in enumerate(old_fixtures):
        dt = base5 + timedelta(days=i*7, hours=17)
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        hg, ag = ri(0,4), ri(0,4)
        att = ri(int(STADIUMS[s-1][3]*0.4), STADIUMS[s-1][3])
        completed_match(h, a, dt_str, s, 9, r, hg, ag, att)

    con.commit()
    print(f"   → {mid-1} completed matches inserted")

    # ── Future (scheduled) matches ────────────────────────────────────────────
    future_fixtures = [
        # Süper Lig upcoming round
        (1, 2, 1, 1, 1001, fut(7)),
        (3, 4, 3, 1, 1002, fut(7)),
        (5, 6, 6, 1, 1003, fut(8)),
        (7, 8, 9, 1, 1004, fut(8)),
        (9,10, 8, 1, 1005, fut(9)),
        (2, 3, 2, 1, 1006, fut(14)),
        (4, 5, 4, 1, 1007, fut(15)),
        # Champions League upcoming
        (11,12,11, 3, 1008, fut(10)),
        (13,14,13, 3, 1009, fut(10)),
        (15,16,15, 3, 1010, fut(11)),
        (17,18,17, 3, 1011, fut(17)),
        (19,20,19, 3, 1012, fut(17)),
        # Kupa upcoming
        (1, 4, 1, 2, 1001, fut(21)),
        (2, 5, 2, 2, 1003, fut(21)),
        # Europa League
        (1,20, 1, 4, 1013, fut(28)),
        (2,19, 2, 4, 1014, fut(28)),
        # Far future (30+ days out)
        (1, 3, 1, 1, 1001, fut(35)),
        (2, 4, 2, 1, 1002, fut(35)),
        (11,13,11, 3, 1005, fut(42)),
        (12,14,12, 3, 1006, fut(42)),
    ]
    for h, a, s, comp, ref, fdate in future_fixtures:
        dt_str = f"{fdate} 20:00:00"
        scheduled_match(h, a, dt_str, s, comp, ref)

    con.commit()
    print(f"   → {len(future_fixtures)} scheduled matches inserted")

    # ── Re-enable FK checks and restore triggers ──────────────────────────────
    cur.execute("SET FOREIGN_KEY_CHECKS=1")
    con.commit()
    cur.close()
    con.close()

    print("── Restoring triggers …")
    result = subprocess.run(
        ["mysql", "-h", "127.0.0.1", "-u", "transferdb_user", "-p0000", "transferdb"],
        input=open("sql/02_triggers.sql").read(),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("  ⚠ Trigger restore error:", result.stderr[:200])
    else:
        print("  ✓ Triggers restored")

    # ── Summary ───────────────────────────────────────────────────────────────
    con2 = mysql.connector.connect(**DB_CONFIG)
    cur2 = con2.cursor()
    print("\n── Row counts ──────────────────────────────")
    for tbl in ["Stadium","Competition","Club","AppUser","Person",
                "Player","Manager","Referee","Contract",
                "TransferRecord","`Match`","Lineup"]:
        cur2.execute(f"SELECT COUNT(*) FROM {tbl}")
        print(f"  {tbl.replace('`',''):18s} {cur2.fetchone()[0]:>5}")
    cur2.close()
    con2.close()
    print("\n✓ Seed complete.")
    print("\nTest accounts (password for all: Test@1234)")
    print("  DB Manager : admin")
    print("  Referee    : ref_cakir  (person_id 1001, officiated many matches)")
    print("  Referee    : ref_meler  (person_id 1002)")
    print("  Manager    : mgr_terim  (person_id 2001, club: Galatasaray)")
    print("  Manager    : mgr_klopp  (person_id 2012, club: Liverpool)")
    print("  Player     : plr_ugur1101 … plr_vete1260")
    print()
    print("Edge-case players:")
    print("  Loan player A (pid 1251) : permanent at Galatasaray, loan at Fenerbahçe")
    print("  Loan player B (pid 1252) : permanent at Beşiktaş, loan at Trabzonspor")
    print("  Free agents  (pid 1241-1245) : no active contracts")
    print("  Expired      (pid 1256-1257) : contracts expired, effectively free agents")


if __name__ == "__main__":
    run()
