-- Additive only. Keep this ledger across rollback/restart for idempotency.
CREATE TABLE IF NOT EXISTS adv_transactions (
    mac CHAR(17) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    token CHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    request_json TEXT NOT NULL,
    status SMALLINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (mac, token)
) ENGINE=InnoDB;
