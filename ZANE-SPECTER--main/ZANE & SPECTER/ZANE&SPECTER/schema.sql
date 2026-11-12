-- ============================================================
-- ZANE & SPECTER Law Firm Management Portal: schema.sql
-- Target: MySQL 8.0.16+ (CHECK constraints enforced,
--         expression defaults like DEFAULT (CURRENT_DATE) allowed)
-- Safe to re-run: drops tables in dependency order first.
-- ============================================================

CREATE DATABASE IF NOT EXISTS zane_specter
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
USE zane_specter;

DROP VIEW  IF EXISTS ActiveMatters;
DROP TABLE IF EXISTS TimeEntries;
DROP TABLE IF EXISTS Invoices;
DROP TABLE IF EXISTS Matters;
DROP TABLE IF EXISTS Clients;
DROP TABLE IF EXISTS Staff;

-- ------------------------------------------------------------
-- Staff (self-referencing hierarchy via manager_id)
-- ------------------------------------------------------------
CREATE TABLE Staff (
    staff_id       INT AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    email          VARCHAR(120) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    role           ENUM('Managing Partner','Partner','Associate','Paralegal','Admin') NOT NULL,
    practice_area  VARCHAR(60)  NOT NULL,
    hourly_rate    DECIMAL(8,2) NOT NULL CHECK (hourly_rate >= 0),
    manager_id     INT NULL,
    hire_date      DATE NOT NULL,
    FOREIGN KEY (manager_id) REFERENCES Staff(staff_id) ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- Clients
-- ------------------------------------------------------------
CREATE TABLE Clients (
    client_id      INT AUTO_INCREMENT PRIMARY KEY,
    company_name   VARCHAR(150) NOT NULL UNIQUE,
    industry       VARCHAR(80)  NOT NULL,
    contact_email  VARCHAR(120),
    created_at     DATE NOT NULL DEFAULT (CURRENT_DATE)
);

-- ------------------------------------------------------------
-- Matters (cases). RESTRICT: legal records must not vanish
-- when a client or lawyer is removed.
-- ------------------------------------------------------------
CREATE TABLE Matters (
    matter_id       INT AUTO_INCREMENT PRIMARY KEY,
    matter_title    VARCHAR(200) NOT NULL,
    client_id       INT NOT NULL,
    lead_staff_id   INT NOT NULL,
    opposing_party  VARCHAR(150) NULL,
    status          ENUM('Active','On Hold','Closed') NOT NULL DEFAULT 'Active',
    opened_date     DATE NOT NULL,
    FOREIGN KEY (client_id)     REFERENCES Clients(client_id) ON DELETE RESTRICT,
    FOREIGN KEY (lead_staff_id) REFERENCES Staff(staff_id)    ON DELETE RESTRICT
);

-- ------------------------------------------------------------
-- Invoices. Either seeded directly or generated from time entries
-- (see /invoices/generate). Created before TimeEntries because
-- TimeEntries.invoice_id points at it.
-- ------------------------------------------------------------
CREATE TABLE Invoices (
    invoice_id  INT AUTO_INCREMENT PRIMARY KEY,
    matter_id   INT NOT NULL,
    amount      DECIMAL(12,2) NOT NULL CHECK (amount > 0),
    issue_date  DATE NOT NULL,
    due_date    DATE NOT NULL,
    status      ENUM('Paid','Unpaid','Void') NOT NULL DEFAULT 'Unpaid',
    FOREIGN KEY (matter_id) REFERENCES Matters(matter_id) ON DELETE RESTRICT,
    CHECK (due_date >= issue_date)
);

-- ------------------------------------------------------------
-- TimeEntries. RESTRICT: audit trail for billable work.
-- invoice_id IS NULL means the time has not been billed yet. When an
-- invoice is generated, the person's hourly rate at that moment is copied
-- to billed_rate so later rate changes never alter an issued invoice.
-- ------------------------------------------------------------
CREATE TABLE TimeEntries (
    entry_id      INT AUTO_INCREMENT PRIMARY KEY,
    staff_id      INT NOT NULL,
    matter_id     INT NOT NULL,
    hours_logged  DECIMAL(5,2) NOT NULL CHECK (hours_logged > 0 AND hours_logged <= 24),
    entry_date    DATE NOT NULL DEFAULT (CURRENT_DATE),
    description   VARCHAR(500) NOT NULL,
    invoice_id    INT NULL,
    billed_rate   DECIMAL(8,2) NULL CHECK (billed_rate IS NULL OR billed_rate >= 0),
    FOREIGN KEY (staff_id)   REFERENCES Staff(staff_id)      ON DELETE RESTRICT,
    FOREIGN KEY (matter_id)  REFERENCES Matters(matter_id)   ON DELETE RESTRICT,
    FOREIGN KEY (invoice_id) REFERENCES Invoices(invoice_id) ON DELETE RESTRICT
);

-- ------------------------------------------------------------
-- Indexes (frequently filtered / joined columns)
-- ------------------------------------------------------------
CREATE INDEX idx_matters_status   ON Matters(status);
CREATE INDEX idx_invoices_status  ON Invoices(status, due_date);
CREATE INDEX idx_clients_industry ON Clients(industry);
CREATE INDEX idx_time_matter      ON TimeEntries(matter_id);
CREATE INDEX idx_time_unbilled    ON TimeEntries(matter_id, invoice_id);

-- ------------------------------------------------------------
-- View: active matters with client and lead partner resolved.
-- Used by the Matters page (Active filter) and the time-entry form.
-- ------------------------------------------------------------
CREATE VIEW ActiveMatters AS
SELECT m.matter_id,
       m.matter_title,
       c.client_id,
       c.company_name,
       s.staff_id AS lead_staff_id,
       s.name     AS lead_partner,
       m.opposing_party,
       m.opened_date
FROM Matters m
JOIN Clients c ON m.client_id     = c.client_id
JOIN Staff   s ON m.lead_staff_id = s.staff_id
WHERE m.status = 'Active';

-- ------------------------------------------------------------
-- Triggers: no new time on closed matters.
-- Billing a closed matter is fine (final invoice), so the UPDATE
-- trigger only fires when an entry is moved onto a closed matter.
-- DELIMITER is a mysql-client command: run this file with
--   mysql -u root -p < schema.sql
-- ------------------------------------------------------------
DELIMITER //

CREATE TRIGGER trg_time_no_closed_insert
BEFORE INSERT ON TimeEntries
FOR EACH ROW
BEGIN
    IF (SELECT status FROM Matters WHERE matter_id = NEW.matter_id) = 'Closed' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot log time on a closed matter.';
    END IF;
END//

CREATE TRIGGER trg_time_no_closed_update
BEFORE UPDATE ON TimeEntries
FOR EACH ROW
BEGIN
    IF NEW.matter_id <> OLD.matter_id
       AND (SELECT status FROM Matters WHERE matter_id = NEW.matter_id) = 'Closed' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot move time onto a closed matter.';
    END IF;
END//

DELIMITER ;
