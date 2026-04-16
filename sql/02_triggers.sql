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
    DECLARE v_home        INT;
    DECLARE v_away        INT;
    DECLARE v_player_club INT DEFAULT NULL;

    -- Determine which club this player belongs to in this match
    SELECT home_club_id, away_club_id
    INTO v_home, v_away
    FROM `Match`
    WHERE match_id = NEW.match_id;

    SELECT club_id INTO v_player_club
    FROM Contract
    WHERE player_id = NEW.player_id
      AND start_date <= CURDATE() AND end_date > CURDATE()
      AND club_id IN (v_home, v_away)
    LIMIT 1;

    -- Count existing starters for THIS CLUB in this match
    SELECT COUNT(*) INTO starter_count
    FROM Lineup l
    JOIN Contract ct ON ct.player_id = l.player_id
      AND ct.start_date <= CURDATE() AND ct.end_date > CURDATE()
      AND ct.club_id = v_player_club
    WHERE l.match_id = NEW.match_id AND l.is_starter = 1;

    IF NEW.is_starter = 1 AND starter_count >= 11 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Squad error: a club cannot have more than 11 starters in a match.';
    END IF;

    -- Count total squad size for THIS CLUB in this match
    SELECT COUNT(*) INTO squad_count
    FROM Lineup l
    JOIN Contract ct ON ct.player_id = l.player_id
      AND ct.start_date <= CURDATE() AND ct.end_date > CURDATE()
      AND ct.club_id = v_player_club
    WHERE l.match_id = NEW.match_id;

    IF squad_count >= 23 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Squad error: a club squad cannot exceed 23 players per match.';
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
      AND CURDATE() >= start_date AND CURDATE() < end_date;
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
          AND CURDATE() >= start_date AND CURDATE() < end_date;

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

    IF NEW.manager_id IS NOT NULL AND (OLD.manager_id IS NULL OR NEW.manager_id <> OLD.manager_id) THEN
        -- Club must not already have a manager (release first)
        IF OLD.manager_id IS NOT NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Manager assignment error: this club already has a manager. Release the current manager first.';
        END IF;

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

    -- Is this player currently on loan? (half-open: start <= today < end)
    SELECT COUNT(*) INTO is_on_loan
    FROM Contract
    WHERE player_id     = NEW.player_id
      AND contract_type = 'Loan'
      AND start_date <= CURDATE() AND end_date > CURDATE();

    IF is_on_loan > 0 THEN
        -- Get the parent club (permanent contract)
        SELECT club_id INTO parent_club_id
        FROM Contract
        WHERE player_id     = NEW.player_id
          AND contract_type = 'Permanent'
          AND start_date <= CURDATE() AND end_date > CURDATE()
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
-- ─────────────────────────────────────────────────────────────
-- TRIGGER 7: Enforce that only eligible players can be added to a match lineup
--   Rule:
--     • A player can appear in Lineup(match_id, player_id) only if they have
--       an ACTIVE contract (Permanent or Loan) with either the home club or
--       the away club of that match (on current date).
--   Purpose:
--     • Prevent selecting players outside the match squad/active roster.
--     • Enforces the "active contract required to be in squad" constraint at DB level.
-- ─────────────────────────────────────────────────────────────

DROP TRIGGER IF EXISTS trg_lineup_requires_active_contract$$
CREATE TRIGGER trg_lineup_requires_active_contract
BEFORE INSERT ON Lineup
FOR EACH ROW
BEGIN
    DECLARE v_home INT;
    DECLARE v_away INT;
    DECLARE v_cnt  INT DEFAULT 0;

    SELECT home_club_id, away_club_id
    INTO v_home, v_away
    FROM `Match`
    WHERE match_id = NEW.match_id;

    -- player must have an active contract with either home or away club
    SELECT COUNT(*) INTO v_cnt
    FROM Contract
    WHERE player_id = NEW.player_id
      AND start_date <= CURDATE() AND end_date > CURDATE()
      AND club_id IN (v_home, v_away);

    IF v_cnt = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Lineup error: player must have an active contract with one of the clubs in this match.';
    END IF;
END$$

-- ─────────────────────────────────────────────────────────────
-- TRIGGER 8: Enforce suspensions (Red card and 5 Yellow cards)
-- ─────────────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_lineup_suspension_check$$
CREATE TRIGGER trg_lineup_suspension_check
BEFORE INSERT ON Lineup
FOR EACH ROW
BEGIN
    DECLARE v_comp_id INT;
    DECLARE v_season VARCHAR(20);
    DECLARE v_match_dt DATETIME;
    DECLARE v_home_club INT;
    DECLARE v_away_club INT;
    DECLARE v_player_club INT;

    DECLARE v_club_last_dt DATETIME;
    DECLARE v_player_last_match_id INT;
    DECLARE v_player_last_dt DATETIME;
    DECLARE v_red_cards INT DEFAULT 0;
    
    DECLARE v_total_yellows INT DEFAULT 0;
    DECLARE v_last_match_yellows INT DEFAULT 0;
    DECLARE v_prev_yellows INT DEFAULT 0;

    -- 1. Get Match Info
    SELECT c.competition_id, c.season, m.match_datetime, m.home_club_id, m.away_club_id
    INTO v_comp_id, v_season, v_match_dt, v_home_club, v_away_club
    FROM `Match` m
    JOIN Competition c ON m.competition_id = c.competition_id
    WHERE m.match_id = NEW.match_id;

    -- 2. Find player club for this match
    SELECT club_id INTO v_player_club
    FROM Contract
    WHERE player_id = NEW.player_id
      AND start_date <= DATE(v_match_dt) AND end_date > DATE(v_match_dt)
      AND club_id IN (v_home_club, v_away_club)
    LIMIT 1;

    IF v_player_club IS NOT NULL THEN
        -- 3. Club's Last Match DT
        SELECT MAX(match_datetime) INTO v_club_last_dt
        FROM `Match`
        WHERE competition_id = v_comp_id
          AND (home_club_id = v_player_club OR away_club_id = v_player_club)
          AND is_completed = 1
          AND match_datetime < v_match_dt;

        -- 4. Player's Last Match in this Comp/Season
        SELECT m.match_id, m.match_datetime, l.red_cards, l.yellow_cards
        INTO v_player_last_match_id, v_player_last_dt, v_red_cards, v_last_match_yellows
        FROM Lineup l
        JOIN `Match` m ON l.match_id = m.match_id
        JOIN Competition c ON m.competition_id = c.competition_id
        WHERE c.competition_id = v_comp_id
          AND c.season = v_season
          AND m.match_datetime < v_match_dt
          AND m.is_completed = 1
          AND l.player_id = NEW.player_id
        ORDER BY m.match_datetime DESC
        LIMIT 1;

        -- If the player has played before, and hasn't served suspension
        IF v_player_last_match_id IS NOT NULL AND (v_club_last_dt IS NULL OR v_club_last_dt <= v_player_last_dt) THEN
            
            -- Red card check
            IF v_red_cards > 0 THEN
                SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'Suspension error: player is suspended due to a red card in their last match.';
            END IF;

            -- Yellow card accumulation check
            SELECT COALESCE(SUM(l.yellow_cards), 0)
            INTO v_total_yellows
            FROM Lineup l
            JOIN `Match` m ON l.match_id = m.match_id
            JOIN Competition c ON m.competition_id = c.competition_id
            WHERE c.competition_id = v_comp_id
              AND c.season = v_season
              AND m.match_datetime <= v_player_last_dt
              AND m.is_completed = 1
              AND l.player_id = NEW.player_id;

            SET v_prev_yellows = v_total_yellows - v_last_match_yellows;

            IF FLOOR(v_total_yellows / 5) > FLOOR(v_prev_yellows / 5) THEN
                SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'Suspension error: player is suspended due to yellow card accumulation (5 cards).';
            END IF;
        END IF;
    END IF;
END$$

DELIMITER ;
