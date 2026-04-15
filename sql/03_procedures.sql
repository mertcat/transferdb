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
--   Handles: Transfer record, new Contract, Permanent termination,
--            market value update for purchases.
--   Trigger trg_contract_rules fires on the Contract INSERT.
-- ─────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS register_transfer$$
CREATE PROCEDURE register_transfer(
    IN  p_player_id     INT,
    IN  p_from_club_id  INT,
    IN  p_to_club_id    INT,
    IN  p_transfer_type ENUM('Free','Purchase','Loan'),
    IN  p_transfer_fee  DECIMAL(15,2),
    IN  p_weekly_wage   DECIMAL(10,2),
    IN  p_contract_end  DATE,
    OUT p_transfer_id   INT,
    OUT p_contract_id   INT
)
BEGIN
    DECLARE v_today DATE DEFAULT CURDATE();

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- Validate transfer fee vs type
    IF p_transfer_type = 'Free' AND p_transfer_fee <> 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Transfer error: Free transfers must have fee = 0.';
    END IF;

    -- If Permanent transfer: terminate existing Permanent contract for this player.
    -- Spec §9: "updating its end_date to the new start_date". The active-contract
    -- check uses an inclusive BETWEEN, so we set end_date one day before the new
    -- start to guarantee the old permanent is no longer counted as active and the
    -- trg_contract_rules trigger will accept the new Permanent insert.
    IF p_transfer_type IN ('Free','Purchase') THEN
        UPDATE Contract
        SET end_date = v_today - INTERVAL 1 DAY
        WHERE player_id     = p_player_id
          AND contract_type = 'Permanent'
          AND CURDATE() BETWEEN start_date AND end_date;
    END IF;

    -- Create transfer record
    INSERT INTO TransferRecord
        (player_id, from_club_id, to_club_id, transfer_date, transfer_fee, transfer_type)
    VALUES
        (p_player_id, p_from_club_id, p_to_club_id, v_today, p_transfer_fee, p_transfer_type);

    SET p_transfer_id = LAST_INSERT_ID();

    -- Determine contract type from transfer type
    -- (Free/Purchase → Permanent, Loan → Loan)
    INSERT INTO Contract
        (player_id, club_id, start_date, end_date, weekly_wage, contract_type)
    VALUES (
        p_player_id,
        p_to_club_id,
        v_today,
        p_contract_end,
        p_weekly_wage,
        IF(p_transfer_type = 'Loan', 'Loan', 'Permanent')
    );
    -- NOTE: trg_contract_rules fires here and enforces:
    --   • max 1 Permanent, max 1 Loan
    --   • Loan requires active Permanent elsewhere

    SET p_contract_id = LAST_INSERT_ID();

    -- Update market value for purchases
    IF p_transfer_type = 'Purchase' AND p_transfer_fee > 0 THEN
        UPDATE Player
        SET market_value = p_transfer_fee
        WHERE person_id = p_player_id;
    END IF;

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

    IF NOW() < v_match_dt THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Match result cannot be submitted before the scheduled match time.';
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
