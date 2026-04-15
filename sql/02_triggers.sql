-- ============================================================
-- TransferDB Triggers
-- ALL CONSTRAINTS ENFORCED AT DATABASE LEVEL
-- ============================================================

DELIMITER $$

-- ─────────────────────────────────────────────────────────────
-- TRIGGER 1: Prevent match scheduling conflicts (120-minute rule)
--            Fires BEFORE INSERT on Match
-- ─────────────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_match_no_overlap$$
CREATE TRIGGER trg_match_no_overlap
BEFORE INSERT ON `Match`
FOR EACH ROW
BEGIN
    DECLARE conflict_count INT DEFAULT 0;

    -- Stadium conflict
    SELECT COUNT(*) INTO conflict_count
    FROM `Match`
    WHERE stadium_id = NEW.stadium_id
      AND ABS(TIMESTAMPDIFF(MINUTE, match_datetime, NEW.match_datetime)) < 120;

    IF conflict_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Stadium conflict: another match is scheduled within 120 minutes at this stadium.';
    END IF;

    -- Referee conflict
    SELECT COUNT(*) INTO conflict_count
    FROM `Match`
    WHERE referee_id = NEW.referee_id
      AND ABS(TIMESTAMPDIFF(MINUTE, match_datetime, NEW.match_datetime)) < 120;

    IF conflict_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Referee conflict: this referee is assigned to another match within 120 minutes.';
    END IF;

    -- Home club conflict (either as home or away)
    SELECT COUNT(*) INTO conflict_count
    FROM `Match`
    WHERE (home_club_id = NEW.home_club_id OR away_club_id = NEW.home_club_id)
      AND ABS(TIMESTAMPDIFF(MINUTE, match_datetime, NEW.match_datetime)) < 120;

    IF conflict_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Home club conflict: club has another match scheduled within 120 minutes.';
    END IF;

    -- Away club conflict
    SELECT COUNT(*) INTO conflict_count
    FROM `Match`
    WHERE (home_club_id = NEW.away_club_id OR away_club_id = NEW.away_club_id)
      AND ABS(TIMESTAMPDIFF(MINUTE, match_datetime, NEW.match_datetime)) < 120;

    IF conflict_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Away club conflict: club has another match scheduled within 120 minutes.';
    END IF;

    -- Match must be in the future
    IF NEW.match_datetime <= NOW() THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Match must be scheduled for a future date and time.';
    END IF;
END$$

-- ─────────────────────────────────────────────────────────────
-- TRIGGER 2: Enforce max 11 starters when inserting lineup rows
-- ─────────────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_lineup_starter_limit$$
CREATE TRIGGER trg_lineup_starter_limit
BEFORE INSERT ON Lineup
FOR EACH ROW
BEGIN
    DECLARE starter_count INT DEFAULT 0;
    DECLARE squad_count   INT DEFAULT 0;

    -- Count existing starters for this match
    SELECT COUNT(*) INTO starter_count
    FROM Lineup
    WHERE match_id = NEW.match_id AND is_starter = 1;

    IF NEW.is_starter = 1 AND starter_count >= 11 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Squad error: a match cannot have more than 11 starters.';
    END IF;

    -- Count total squad size
    SELECT COUNT(*) INTO squad_count
    FROM Lineup
    WHERE match_id = NEW.match_id;

    IF squad_count >= 23 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Squad error: a match squad cannot exceed 23 players.';
    END IF;
END$$

-- ─────────────────────────────────────────────────────────────
-- TRIGGER 3: Enforce attendance <= stadium capacity on result submission
-- ─────────────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_match_attendance_capacity$$
CREATE TRIGGER trg_match_attendance_capacity
BEFORE UPDATE ON `Match`
FOR EACH ROW
BEGIN
    DECLARE stadium_cap INT DEFAULT 0;

    IF NEW.attendance IS NOT NULL THEN
        SELECT capacity INTO stadium_cap
        FROM Stadium
        WHERE stadium_id = NEW.stadium_id;

        IF NEW.attendance > stadium_cap THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Attendance exceeds stadium capacity.';
        END IF;
    END IF;
END$$

-- ─────────────────────────────────────────────────────────────
-- TRIGGER 4: Contract rules
--   a) Max 2 active contracts (1 Permanent + 1 Loan)
--   b) Loan requires an active Permanent contract at another club
-- ─────────────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_contract_rules$$
CREATE TRIGGER trg_contract_rules
BEFORE INSERT ON Contract
FOR EACH ROW
BEGIN
    DECLARE permanent_count INT DEFAULT 0;
    DECLARE loan_count      INT DEFAULT 0;
    DECLARE parent_count    INT DEFAULT 0;

    -- Count current active contracts
    SELECT
        SUM(contract_type = 'Permanent'),
        SUM(contract_type = 'Loan')
    INTO permanent_count, loan_count
    FROM Contract
    WHERE player_id = NEW.player_id
      AND CURDATE() BETWEEN start_date AND end_date;

    IF NEW.contract_type = 'Permanent' THEN
        IF permanent_count >= 1 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Contract error: player already has an active Permanent contract. Terminate it first.';
        END IF;
    END IF;

    IF NEW.contract_type = 'Loan' THEN
        IF loan_count >= 1 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Contract error: player already has an active Loan contract.';
        END IF;

        -- Loan requires an active Permanent contract at a DIFFERENT club
        SELECT COUNT(*) INTO parent_count
        FROM Contract
        WHERE player_id     = NEW.player_id
          AND contract_type = 'Permanent'
          AND club_id      <> NEW.club_id
          AND CURDATE() BETWEEN start_date AND end_date;

        IF parent_count = 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Loan error: player must have an active Permanent contract at another club before being loaned.';
        END IF;
    END IF;
END$$

-- ─────────────────────────────────────────────────────────────
-- TRIGGER 5: One manager per club, one club per manager
-- ─────────────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_club_manager_unique$$
CREATE TRIGGER trg_club_manager_unique
BEFORE UPDATE ON Club
FOR EACH ROW
BEGIN
    DECLARE existing_club INT DEFAULT 0;

    IF NEW.manager_id IS NOT NULL AND NEW.manager_id <> OLD.manager_id THEN
        -- Check new manager not already assigned elsewhere
        SELECT COUNT(*) INTO existing_club
        FROM Club
        WHERE manager_id = NEW.manager_id
          AND club_id   <> NEW.club_id;

        IF existing_club > 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Manager assignment error: this manager is already assigned to another club.';
        END IF;
    END IF;
END$$

-- ─────────────────────────────────────────────────────────────
-- TRIGGER 6: Prevent loaned player playing for parent club
-- ─────────────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_no_loan_parent_play$$
CREATE TRIGGER trg_no_loan_parent_play
BEFORE INSERT ON Lineup
FOR EACH ROW
BEGIN
    DECLARE parent_club_id  INT DEFAULT NULL;
    DECLARE match_club_id   INT DEFAULT NULL;
    DECLARE is_on_loan      INT DEFAULT 0;

    -- Is this player currently on loan?
    SELECT COUNT(*) INTO is_on_loan
    FROM Contract
    WHERE player_id     = NEW.player_id
      AND contract_type = 'Loan'
      AND CURDATE() BETWEEN start_date AND end_date;

    IF is_on_loan > 0 THEN
        -- Get the parent club (permanent contract)
        SELECT club_id INTO parent_club_id
        FROM Contract
        WHERE player_id     = NEW.player_id
          AND contract_type = 'Permanent'
          AND CURDATE() BETWEEN start_date AND end_date
        LIMIT 1;

        -- Check if this match involves the parent club
        SELECT home_club_id INTO match_club_id
        FROM `Match`
        WHERE match_id = NEW.match_id;

        IF match_club_id = parent_club_id THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Lineup error: loaned player cannot play for their parent club.';
        END IF;

        SELECT away_club_id INTO match_club_id
        FROM `Match`
        WHERE match_id = NEW.match_id;

        IF match_club_id = parent_club_id THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Lineup error: loaned player cannot play for their parent club.';
        END IF;
    END IF;
END$$

DELIMITER ;
