-- ============================================================
-- TransferDB Schema
-- CMPE 321 – Spring 2026
-- ============================================================

SET FOREIGN_KEY_CHECKS = 0;
SET SQL_MODE = 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO';

-- ─────────────────────────────────────────
-- USERS (login / role dispatch)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS AppUser (
    username     VARCHAR(50)  NOT NULL,
    password     VARCHAR(255) NOT NULL,   -- bcrypt hash
    role         ENUM('DatabaseManager','Player','Manager','Referee') NOT NULL,
    person_id    INT          NULL,        -- NULL for DB Managers
    PRIMARY KEY (username)
);

-- ─────────────────────────────────────────
-- PERSON (super-type)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Person (
    person_id     INT          NOT NULL AUTO_INCREMENT,
    name          VARCHAR(100) NOT NULL,
    surname       VARCHAR(100) NOT NULL,
    nationality   VARCHAR(100) NOT NULL,
    date_of_birth DATE         NOT NULL,
    PRIMARY KEY (person_id)
);

-- ─────────────────────────────────────────
-- SUB-TYPES
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Player (
    person_id    INT             NOT NULL,
    market_value DECIMAL(15,2)   NOT NULL CHECK (market_value > 0),
    main_position ENUM('Goalkeeper','Defender','Midfielder','Forward') NOT NULL,
    strong_foot  ENUM('Right','Left','Both') NOT NULL,
    height       INT             NOT NULL CHECK (height > 0),
    PRIMARY KEY (person_id),
    FOREIGN KEY (person_id) REFERENCES Person(person_id)
);

CREATE TABLE IF NOT EXISTS Manager (
    person_id            INT          NOT NULL,
    preferred_formation  VARCHAR(20)  NOT NULL,
    experience_level     VARCHAR(100) NOT NULL,
    PRIMARY KEY (person_id),
    FOREIGN KEY (person_id) REFERENCES Person(person_id)
);

CREATE TABLE IF NOT EXISTS Referee (
    person_id           INT         NOT NULL,
    license_level       VARCHAR(20) NOT NULL,
    years_of_experience INT         NOT NULL CHECK (years_of_experience >= 0),
    PRIMARY KEY (person_id),
    FOREIGN KEY (person_id) REFERENCES Person(person_id)
);

-- ─────────────────────────────────────────
-- STADIUM
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Stadium (
    stadium_id   INT          NOT NULL AUTO_INCREMENT,
    stadium_name VARCHAR(150) NOT NULL,
    city         VARCHAR(100) NOT NULL,
    capacity     INT          NOT NULL CHECK (capacity > 0),
    PRIMARY KEY (stadium_id)
);

-- ─────────────────────────────────────────
-- CLUB  (manager_id nullable to allow temp no-manager)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Club (
    club_id         INT          NOT NULL AUTO_INCREMENT,
    club_name       VARCHAR(150) NOT NULL,
    city            VARCHAR(100) NOT NULL,
    foundation_year INT          NOT NULL,
    stadium_id      INT          NULL,
    manager_id      INT          NULL,
    PRIMARY KEY (club_id),
    UNIQUE (club_name),
    UNIQUE (manager_id),
    FOREIGN KEY (stadium_id)  REFERENCES Stadium(stadium_id),
    FOREIGN KEY (manager_id)  REFERENCES Manager(person_id)
);

-- ─────────────────────────────────────────
-- COMPETITION
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Competition (
    competition_id   INT          NOT NULL AUTO_INCREMENT,
    name             VARCHAR(100) NOT NULL,
    season           VARCHAR(20)  NOT NULL,
    country          VARCHAR(100) NOT NULL,
    competition_type ENUM('League','Cup','International') NOT NULL,
    PRIMARY KEY (competition_id),
    UNIQUE (name, season)
);

-- ─────────────────────────────────────────
-- MATCH
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `Match` (
    match_id        INT      NOT NULL AUTO_INCREMENT,
    match_datetime  DATETIME NOT NULL,
    attendance      INT      NULL     CHECK (attendance IS NULL OR attendance >= 0),
    home_goals      INT      NULL     CHECK (home_goals IS NULL OR home_goals >= 0),
    away_goals      INT      NULL     CHECK (away_goals IS NULL OR away_goals >= 0),
    home_club_id    INT      NOT NULL,
    away_club_id    INT      NOT NULL,
    stadium_id      INT      NOT NULL,
    competition_id  INT      NOT NULL,
    referee_id      INT      NOT NULL,
    is_completed    TINYINT(1) NOT NULL DEFAULT 0,
    PRIMARY KEY (match_id),
    CHECK (home_club_id <> away_club_id),
    FOREIGN KEY (home_club_id)   REFERENCES Club(club_id),
    FOREIGN KEY (away_club_id)   REFERENCES Club(club_id),
    FOREIGN KEY (stadium_id)     REFERENCES Stadium(stadium_id),
    FOREIGN KEY (competition_id) REFERENCES Competition(competition_id),
    FOREIGN KEY (referee_id)     REFERENCES Referee(person_id)
);

-- ─────────────────────────────────────────
-- CONTRACT
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Contract (
    contract_id   INT             NOT NULL AUTO_INCREMENT,
    player_id     INT             NOT NULL,
    club_id       INT             NOT NULL,
    start_date    DATE            NOT NULL,
    end_date      DATE            NOT NULL,
    weekly_wage   DECIMAL(10,2)   NOT NULL CHECK (weekly_wage > 0),
    contract_type ENUM('Permanent','Loan') NOT NULL,
    PRIMARY KEY (contract_id),
    CHECK (end_date > start_date),
    FOREIGN KEY (player_id) REFERENCES Player(person_id),
    FOREIGN KEY (club_id)   REFERENCES Club(club_id)
);

-- ─────────────────────────────────────────
-- TRANSFER RECORD
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS TransferRecord (
    transfer_id   INT             NOT NULL AUTO_INCREMENT,
    player_id     INT             NOT NULL,
    from_club_id  INT NULL,
    to_club_id    INT             NOT NULL,
    transfer_date DATE            NOT NULL,
    transfer_fee  DECIMAL(15,2)   NOT NULL,
    transfer_type ENUM('Free','Purchase','Loan') NOT NULL,
    PRIMARY KEY (transfer_id),
    CHECK (from_club_id <> to_club_id),
    CHECK (
        (transfer_type = 'Free'     AND transfer_fee = 0)
     OR (transfer_type IN ('Purchase','Loan') AND transfer_fee >= 0)
    ),
    FOREIGN KEY (player_id)    REFERENCES Player(person_id),
    FOREIGN KEY (from_club_id) REFERENCES Club(club_id),
    FOREIGN KEY (to_club_id)   REFERENCES Club(club_id)
);

-- ─────────────────────────────────────────
-- LINEUP  (match participation & stats)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Lineup (
    match_id         INT            NOT NULL,
    player_id        INT            NOT NULL,
    is_starter       TINYINT(1)     NOT NULL,
    minutes_played   INT            NOT NULL CHECK (minutes_played >= 0 AND minutes_played <= 120),
    position_in_match VARCHAR(20)   NOT NULL,
    goals            INT            NOT NULL DEFAULT 0 CHECK (goals >= 0),
    assists          INT            NOT NULL DEFAULT 0 CHECK (assists >= 0),
    yellow_cards     INT            NOT NULL DEFAULT 0 CHECK (yellow_cards IN (0,1,2)),
    red_cards        INT            NOT NULL DEFAULT 0 CHECK (red_cards IN (0,1)),
    rating           DECIMAL(3,1)   NOT NULL CHECK (rating >= 1.0 AND rating <= 10.0),
    PRIMARY KEY (match_id, player_id),
    FOREIGN KEY (match_id)  REFERENCES `Match`(match_id),
    FOREIGN KEY (player_id) REFERENCES Player(person_id)
);

SET FOREIGN_KEY_CHECKS = 1;
