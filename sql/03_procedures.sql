-- ============================================================
-- TransferDB Stored Procedures
-- ============================================================

DELIMITER $$

-- ─────────────────────────────────────────────────────────────
-- PROCEDURE: schedule_match
--   Validates all business rules and inserts a new match.
--   The INSERT will also fire trg_match_no_overlap.
-- ─────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS schedule_match$$
CREATE PROCEDURE schedule_match(
    IN  p_datetime       DATETIME,
    IN  p_stadium_id     INT,
    IN  p_home_club_id   INT,
    IN  p_away_club_id   INT,
    IN  p_referee_id     INT,
    IN  p_competition_id INT,
    OUT p_new_match_id   INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- Sanity: clubs must differ (also enforced by CHECK)
    IF p_home_club_id = p_away_club_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'A club cannot play against itself.';
    END IF;

    -- Trigger trg_match_no_overlap handles the 120-min rule & future check
    INSERT INTO `Match`
        (match_datetime, home_club_id, away_club_id, stadium_id, competition_id, referee_id)
    VALUES
        (p_datetime, p_home_club_id, p_away_club_id, p_stadium_id, p_competition_id, p_referee_id);

    SET p_new_match_id = LAST_INSERT_ID();
    COMMIT;
END$$

-- ─────────────────────────────────────────────────────────────
-- PROCEDURE: register_transfer
--   transfer_type = contract type: 'Permanent' or 'Loan'
--   p_to_club_id may be NULL (player released → becomes free agent)
--
--   When to_club_id IS NOT NULL:
--     1. If Permanent: terminate existing active Permanent (set end_date = today)
--     2. Insert TransferRecord
--     3. Insert new Contract at to_club
--     4. For Permanent with fee > 0: update player market_value
--   When to_club_id IS NULL (release):
--     1. Terminate active contracts (Permanent and/or Loan)
--     2. Insert TransferRecord with to_club_id = NULL
--     3. No new contract created
-- ─────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS register_transfer$$
CREATE PROCEDURE register_transfer(
    IN  p_player_id      INT,
    IN  p_from_club_id   INT,
    IN  p_to_club_id     INT,
    IN  p_transfer_type  ENUM('Permanent','Loan'),
    IN  p_transfer_fee   DECIMAL(15,2),
    IN  p_weekly_wage    DECIMAL(10,2),
    IN  p_contract_end   DATE,
    OUT p_transfer_id    INT,
    OUT p_contract_id    INT
)
BEGIN
    DECLARE v_today DATE DEFAULT CURDATE();

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- ── Release path: to_club_id is NULL ──
    IF p_to_club_id IS NULL THEN
        -- Terminate all active contracts (half-open: start <= today < end)
        UPDATE Contract
        SET end_date = v_today
        WHERE player_id = p_player_id
          AND start_date <= v_today AND end_date > v_today;

        -- Record the transfer (to_club = NULL means release)
        INSERT INTO TransferRecord
            (player_id, from_club_id, to_club_id, transfer_date, transfer_fee, transfer_type)
        VALUES
            (p_player_id, p_from_club_id, NULL, v_today, p_transfer_fee, p_transfer_type);

        SET p_transfer_id = LAST_INSERT_ID();
        SET p_contract_id = NULL;

        COMMIT;
    ELSE
        -- ── Normal transfer path ──

        -- If Permanent: terminate existing active Permanent
        IF p_transfer_type = 'Permanent' THEN
            UPDATE Contract
            SET end_date = v_today
            WHERE player_id     = p_player_id
              AND contract_type = 'Permanent'
              AND start_date <= v_today AND end_date > v_today;
        END IF;

        -- If Loan: terminate existing active Loan (allows loan-to-loan change)
        IF p_transfer_type = 'Loan' THEN
            UPDATE Contract
            SET end_date = v_today
            WHERE player_id     = p_player_id
              AND contract_type = 'Loan'
              AND start_date <= v_today AND end_date > v_today;
        END IF;

        -- Create transfer record
        INSERT INTO TransferRecord
            (player_id, from_club_id, to_club_id, transfer_date, transfer_fee, transfer_type)
        VALUES
            (p_player_id, p_from_club_id, p_to_club_id, v_today, p_transfer_fee, p_transfer_type);

        SET p_transfer_id = LAST_INSERT_ID();

        -- Create new contract (trg_contract_rules fires here)
        INSERT INTO Contract
            (player_id, club_id, start_date, end_date, weekly_wage, contract_type)
        VALUES (
            p_player_id,
            p_to_club_id,
            v_today,
            p_contract_end,
            p_weekly_wage,
            p_transfer_type
        );

        SET p_contract_id = LAST_INSERT_ID();

        -- Update market value for Permanent transfers with fee > 0
        IF p_transfer_type = 'Permanent' AND p_transfer_fee > 0 THEN
            UPDATE Player
            SET market_value = p_transfer_fee
            WHERE person_id = p_player_id;
        END IF;

        COMMIT;
    END IF;
END$$

-- ─────────────────────────────────────────────────────────────
-- PROCEDURE: end_loan
--   Terminates a player's active loan contract and records the
--   return transfer to the parent (permanent) club.
--   Enforced at DB level: if no active loan exists → error.
-- ─────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS end_loan$$
CREATE PROCEDURE end_loan(
    IN  p_player_id    INT,
    OUT p_transfer_id  INT
)
BEGIN
    DECLARE v_loan_club INT DEFAULT NULL;
    DECLARE v_perm_club INT DEFAULT NULL;
    DECLARE v_today     DATE DEFAULT CURDATE();

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- Find active loan contract
    SELECT club_id INTO v_loan_club
    FROM Contract
    WHERE player_id     = p_player_id
      AND contract_type = 'Loan'
      AND start_date <= v_today AND end_date > v_today
    LIMIT 1;

    IF v_loan_club IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Player does not have an active loan contract.';
    END IF;

    -- Find parent (permanent) club
    SELECT club_id INTO v_perm_club
    FROM Contract
    WHERE player_id     = p_player_id
      AND contract_type = 'Permanent'
      AND start_date <= v_today AND end_date > v_today
    LIMIT 1;

    -- Terminate the loan
    UPDATE Contract
    SET end_date = v_today
    WHERE player_id     = p_player_id
      AND contract_type = 'Loan'
      AND start_date <= v_today AND end_date > v_today;

    -- Record the loan return transfer
    INSERT INTO TransferRecord
        (player_id, from_club_id, to_club_id, transfer_date, transfer_fee, transfer_type)
    VALUES
        (p_player_id, v_loan_club, v_perm_club, v_today, 0, 'Loan');

    SET p_transfer_id = LAST_INSERT_ID();

    COMMIT;
END$$

-- ─────────────────────────────────────────────────────────────
-- PROCEDURE: submit_match_result
--   Only the assigned referee may submit; match time must have passed.
-- ─────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS submit_match_result$$
CREATE PROCEDURE submit_match_result(
    IN p_match_id    INT,
    IN p_referee_id  INT,   -- must equal the assigned referee
    IN p_home_goals  INT,
    IN p_away_goals  INT,
    IN p_attendance  INT
)
BEGIN
    DECLARE v_assigned_ref INT;
    DECLARE v_match_dt     DATETIME;

    SELECT referee_id, match_datetime
    INTO   v_assigned_ref, v_match_dt
    FROM   `Match`
    WHERE  match_id = p_match_id;

    IF v_assigned_ref IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Match not found.';
    END IF;

    IF v_assigned_ref <> p_referee_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Only the assigned referee may submit results for this match.';
    END IF;

    IF NOW() < DATE_ADD(v_match_dt, INTERVAL 120 MINUTE) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Match result cannot be submitted before 120 minutes after the scheduled kick-off.';
    END IF;

    -- trg_match_attendance_capacity fires on UPDATE
    UPDATE `Match`
    SET home_goals   = p_home_goals,
        away_goals   = p_away_goals,
        attendance   = p_attendance,
        is_completed = 1
    WHERE match_id = p_match_id;
END$$

DELIMITER ;
