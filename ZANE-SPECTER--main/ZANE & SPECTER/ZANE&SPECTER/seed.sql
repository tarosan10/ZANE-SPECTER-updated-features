-- ============================================================
-- ZANE & SPECTER Law Firm Management Portal: seed.sql
-- Run AFTER schema.sql on a fresh database.
--
-- Password hashes are placeholders (__HASH_<staff_id>__).
-- Run `python gen_hashes.py` to produce seed_ready.sql with real
-- hashes, then load seed_ready.sql instead of this file.
--
-- All dates are relative to CURDATE() so overdue invoices stay
-- overdue and time entries stay inside the last 90 days.
-- ============================================================
USE zane_specter;

-- ------------------------------------------------------------
-- STAFF (12): 3-level hierarchy
--   L1: Managing Partner
--   L2: Partners (+ Admin) report to the Managing Partner
--   L3: Associates / Paralegals report to a Partner
-- Practice areas: Corporate, Litigation, Intellectual Property,
--                 Real Estate, Administration
-- Rows are inserted manager-first so manager_id FKs resolve.
-- ------------------------------------------------------------
INSERT INTO Staff
    (staff_id, name, email, password_hash, role, practice_area, hourly_rate, manager_id, hire_date)
VALUES
    (1,  'Victoria Lex',   'victoria.lex@zanespecter.example',   '__HASH_1__',  'Managing Partner', 'Corporate',              950.00, NULL, '2008-01-14'),
    (2,  'Marcus Hale',    'marcus.hale@zanespecter.example',    '__HASH_2__',  'Partner',          'Corporate',              750.00, 1,    '2011-06-01'),
    (3,  'Priya Raman',    'priya.raman@zanespecter.example',    '__HASH_3__',  'Partner',          'Litigation',             720.00, 1,    '2012-09-17'),
    (4,  'Daniel Okafor',  'daniel.okafor@zanespecter.example',  '__HASH_4__',  'Partner',          'Intellectual Property',  700.00, 1,    '2013-03-04'),
    (5,  'Elena Rossi',    'elena.rossi@zanespecter.example',    '__HASH_5__',  'Partner',          'Real Estate',            680.00, 1,    '2014-11-10'),
    (6,  'Tom Whitfield',  'tom.whitfield@zanespecter.example',  '__HASH_6__',  'Associate',        'Corporate',              400.00, 2,    '2019-08-26'),
    (7,  'Aisha Karim',    'aisha.karim@zanespecter.example',    '__HASH_7__',  'Associate',        'Litigation',             380.00, 3,    '2020-02-03'),
    (8,  'Jonas Berg',     'jonas.berg@zanespecter.example',     '__HASH_8__',  'Associate',        'Intellectual Property',  390.00, 4,    '2020-09-14'),
    (9,  'Sofia Mendes',   'sofia.mendes@zanespecter.example',   '__HASH_9__',  'Associate',        'Real Estate',            360.00, 5,    '2021-05-24'),
    (10, 'Liam Carter',    'liam.carter@zanespecter.example',    '__HASH_10__', 'Paralegal',        'Corporate',              180.00, 2,    '2021-10-11'),
    (11, 'Hannah Brooks',  'hannah.brooks@zanespecter.example',  '__HASH_11__', 'Paralegal',        'Litigation',             175.00, 3,    '2022-04-18'),
    (12, 'Oscar Reyes',    'oscar.reyes@zanespecter.example',    '__HASH_12__', 'Admin',            'Administration',          90.00, 1,    '2016-07-05');

-- ------------------------------------------------------------
-- CLIENTS (10)
-- Industries with 2+ clients (for the conflict demo):
--   Logistics (2), Energy (2), Technology (2)
-- ------------------------------------------------------------
INSERT INTO Clients (client_id, company_name, industry, contact_email, created_at) VALUES
    (1,  'Northwind Logistics',    'Logistics',          'legal@northwind-logistics.example',  DATE_SUB(CURDATE(), INTERVAL 900 DAY)),
    (2,  'Atlas Freight Holdings', 'Logistics',          'counsel@atlasfreight.example',       DATE_SUB(CURDATE(), INTERVAL 820 DAY)),
    (3,  'Helios Energy Corp',     'Energy',             'legal@heliosenergy.example',         DATE_SUB(CURDATE(), INTERVAL 760 DAY)),
    (4,  'Pinnacle Solar',         'Energy',             'contracts@pinnaclesolar.example',    DATE_SUB(CURDATE(), INTERVAL 640 DAY)),
    (5,  'Cobalt Software',        'Technology',         'legal@cobaltsoft.example',           DATE_SUB(CURDATE(), INTERVAL 580 DAY)),
    (6,  'Nimbus Cloud Systems',   'Technology',         'gc@nimbuscloud.example',             DATE_SUB(CURDATE(), INTERVAL 500 DAY)),
    (7,  'Borealis Pharma',        'Pharmaceuticals',    'legal@borealispharma.example',       DATE_SUB(CURDATE(), INTERVAL 430 DAY)),
    (8,  'Meridian Bank',          'Financial Services', 'compliance@meridianbank.example',    DATE_SUB(CURDATE(), INTERVAL 380 DAY)),
    (9,  'Harbor Retail Group',    'Retail',             'legal@harborretail.example',         DATE_SUB(CURDATE(), INTERVAL 300 DAY)),
    (10, 'Ironclad Construction',  'Construction',       'office@ironcladbuild.example',       DATE_SUB(CURDATE(), INTERVAL 210 DAY));

-- ------------------------------------------------------------
-- MATTERS (15)
-- Final status mix: 10 Active, 2 On Hold, 3 Closed (matters 12-14).
-- Matters 12-14 are inserted as Active and closed after the time
-- entries load, because the trg_time_no_closed_insert trigger blocks
-- time on closed matters.
-- Opposing parties set on 6 matters:
--   Active:  Delta Shipping Co, Vertex Chemical Industries,
--            Orion Retail Partners, Consumer Alliance Group
--   On Hold: Kestrel Developments
--   Closed:  Brightline Analytics  (should NOT trigger a conflict)
-- Lead staff are all Partners / Managing Partner.
-- ------------------------------------------------------------
INSERT INTO Matters
    (matter_id, matter_title, client_id, lead_staff_id, opposing_party, status, opened_date)
VALUES
    (1,  'Acquisition of Regional Carrier',        1,  2, NULL,                          'Active',  DATE_SUB(CURDATE(), INTERVAL 400 DAY)),
    (2,  'Cargo Liability Dispute',                2,  3, 'Delta Shipping Co',           'Active',  DATE_SUB(CURDATE(), INTERVAL 320 DAY)),
    (3,  'Wind Farm Land Lease',                   3,  5, NULL,                          'Active',  DATE_SUB(CURDATE(), INTERVAL 260 DAY)),
    (4,  'Patent Infringement Defense',            4,  4, 'Vertex Chemical Industries', 'Active',  DATE_SUB(CURDATE(), INTERVAL 240 DAY)),
    (5,  'Series B Financing',                     5,  2, NULL,                          'Active',  DATE_SUB(CURDATE(), INTERVAL 200 DAY)),
    (6,  'Trademark Portfolio Registration',       6,  4, NULL,                          'Active',  DATE_SUB(CURDATE(), INTERVAL 180 DAY)),
    (7,  'Drug Patent Licensing',                  7,  4, NULL,                          'Active',  DATE_SUB(CURDATE(), INTERVAL 170 DAY)),
    (8,  'Regulatory Compliance Review',           8,  1, NULL,                          'Active',  DATE_SUB(CURDATE(), INTERVAL 150 DAY)),
    (9,  'Supplier Contract Breach',               9,  3, 'Orion Retail Partners',       'Active',  DATE_SUB(CURDATE(), INTERVAL 120 DAY)),
    (10, 'Commercial Property Dispute',            10, 5, 'Kestrel Developments',        'On Hold', DATE_SUB(CURDATE(), INTERVAL 110 DAY)),
    (11, 'Warehouse Zoning Appeal',                1,  5, NULL,                          'On Hold', DATE_SUB(CURDATE(), INTERVAL 95 DAY)),
    (12, 'Merger with Sunrise Power',              3,  2, NULL,                          'Active',  DATE_SUB(CURDATE(), INTERVAL 450 DAY)),
    (13, 'Employee IP Assignment Dispute',         5,  3, 'Brightline Analytics',        'Active',  DATE_SUB(CURDATE(), INTERVAL 420 DAY)),
    (14, 'Fleet Financing Agreement',              2,  1, NULL,                          'Active',  DATE_SUB(CURDATE(), INTERVAL 380 DAY)),
    (15, 'Consumer Class Action Defense',          8,  3, 'Consumer Alliance Group',     'Active',  DATE_SUB(CURDATE(), INTERVAL 70 DAY));

-- ------------------------------------------------------------
-- TIME ENTRIES (40): staff 1-11, all within the last 90 days
-- (the Admin does not bill time). All start unbilled (invoice_id NULL).
-- ------------------------------------------------------------
INSERT INTO TimeEntries (staff_id, matter_id, hours_logged, entry_date, description) VALUES
    (6,  1,  6.50, DATE_SUB(CURDATE(), INTERVAL 85 DAY), 'Due diligence review of target carrier contracts'),
    (6,  1,  4.25, DATE_SUB(CURDATE(), INTERVAL 80 DAY), 'Drafted asset purchase agreement schedules'),
    (2,  1,  3.00, DATE_SUB(CURDATE(), INTERVAL 78 DAY), 'Partner review of purchase agreement draft'),
    (10, 1,  5.00, DATE_SUB(CURDATE(), INTERVAL 75 DAY), 'Compiled corporate records for data room'),
    (6,  5,  7.00, DATE_SUB(CURDATE(), INTERVAL 70 DAY), 'Prepared Series B term sheet comparison'),
    (2,  5,  2.50, DATE_SUB(CURDATE(), INTERVAL 68 DAY), 'Negotiation call with lead investor counsel'),
    (10, 5,  4.00, DATE_SUB(CURDATE(), INTERVAL 66 DAY), 'Organized cap table and board consents'),
    (7,  2,  8.00, DATE_SUB(CURDATE(), INTERVAL 64 DAY), 'Reviewed cargo manifests and shipping records'),
    (3,  2,  3.50, DATE_SUB(CURDATE(), INTERVAL 62 DAY), 'Strategy session on liability defense'),
    (11, 2,  6.25, DATE_SUB(CURDATE(), INTERVAL 60 DAY), 'Indexed discovery documents'),
    (7,  2,  5.75, DATE_SUB(CURDATE(), INTERVAL 57 DAY), 'Drafted responses to interrogatories'),
    (8,  4,  6.00, DATE_SUB(CURDATE(), INTERVAL 55 DAY), 'Prior art search for patent defense'),
    (4,  4,  2.75, DATE_SUB(CURDATE(), INTERVAL 53 DAY), 'Reviewed invalidity contentions'),
    (8,  6,  4.50, DATE_SUB(CURDATE(), INTERVAL 51 DAY), 'Prepared trademark application filings'),
    (4,  6,  1.50, DATE_SUB(CURDATE(), INTERVAL 49 DAY), 'Client call on trademark portfolio priorities'),
    (8,  7,  7.50, DATE_SUB(CURDATE(), INTERVAL 47 DAY), 'Analyzed licensing terms for patent family'),
    (4,  7,  3.25, DATE_SUB(CURDATE(), INTERVAL 45 DAY), 'Negotiated royalty provisions with licensee'),
    (9,  3,  5.50, DATE_SUB(CURDATE(), INTERVAL 44 DAY), 'Title search and review of lease parcels'),
    (5,  3,  2.00, DATE_SUB(CURDATE(), INTERVAL 42 DAY), 'Reviewed draft wind farm land lease'),
    (9,  3,  6.75, DATE_SUB(CURDATE(), INTERVAL 40 DAY), 'Drafted easement and access agreements'),
    (1,  8,  3.00, DATE_SUB(CURDATE(), INTERVAL 38 DAY), 'Reviewed regulatory examination findings'),
    (6,  8,  8.00, DATE_SUB(CURDATE(), INTERVAL 36 DAY), 'Compliance gap analysis across lending products'),
    (10, 8,  4.75, DATE_SUB(CURDATE(), INTERVAL 34 DAY), 'Prepared compliance report exhibits'),
    (7,  9,  5.25, DATE_SUB(CURDATE(), INTERVAL 33 DAY), 'Analyzed supplier contract breach claims'),
    (3,  9,  2.25, DATE_SUB(CURDATE(), INTERVAL 31 DAY), 'Settlement strategy meeting with client'),
    (11, 9,  3.75, DATE_SUB(CURDATE(), INTERVAL 29 DAY), 'Gathered supplier correspondence'),
    (7,  15, 6.50, DATE_SUB(CURDATE(), INTERVAL 28 DAY), 'Researched class certification standards'),
    (3,  15, 4.00, DATE_SUB(CURDATE(), INTERVAL 14 DAY), 'Drafted motion to dismiss outline'),
    (11, 15, 5.00, DATE_SUB(CURDATE(), INTERVAL 9 DAY),  'Prepared document production set'),
    (9,  10, 4.50, DATE_SUB(CURDATE(), INTERVAL 23 DAY), 'Reviewed construction contract and change orders'),
    (5,  10, 2.50, DATE_SUB(CURDATE(), INTERVAL 21 DAY), 'Mediation preparation call'),
    (9,  11, 3.25, DATE_SUB(CURDATE(), INTERVAL 20 DAY), 'Researched zoning appeal procedure'),
    (5,  11, 1.75, DATE_SUB(CURDATE(), INTERVAL 5 DAY),  'Hearing preparation with client'),
    (6,  12, 5.00, DATE_SUB(CURDATE(), INTERVAL 88 DAY), 'Post-closing filings for merger'),
    (2,  12, 2.00, DATE_SUB(CURDATE(), INTERVAL 87 DAY), 'Partner sign-off on closing checklist'),
    (11, 13, 3.50, DATE_SUB(CURDATE(), INTERVAL 86 DAY), 'Final file review and archiving'),
    (8,  13, 4.25, DATE_SUB(CURDATE(), INTERVAL 84 DAY), 'Closing correspondence on IP assignment dispute'),
    (1,  14, 2.50, DATE_SUB(CURDATE(), INTERVAL 89 DAY), 'Final review of fleet financing documents'),
    (10, 14, 3.75, DATE_SUB(CURDATE(), INTERVAL 83 DAY), 'Filed UCC termination statements'),
    (6,  5,  6.00, DATE_SUB(CURDATE(), INTERVAL 3 DAY),  'Updated investor disclosure schedules');

-- Close matters 12-14 now that their time entries are in.
UPDATE Matters SET status = 'Closed' WHERE matter_id IN (12, 13, 14);

-- ------------------------------------------------------------
-- INVOICES (20): 8 Paid, 8 Unpaid, 4 Void
-- Seeded directly (not derived from time entries).
--
-- Paid revenue by lead partner (Leaderboard order):
--   Marcus Hale 133,000 > Daniel Okafor 85,000 > Victoria Lex 47,000
--   > Priya Raman 28,500 > Elena Rossi 19,000
--
-- Overdue (Unpaid, due_date < today), grouped by client:
--   Harbor Retail Group   16,500  (2 invoices)  -> shown
--   Atlas Freight         12,000  (2 x 6,000)   -> shown (HAVING demo)
--   Northwind Logistics   11,000  (1 invoice)   -> shown
--   Meridian Bank          8,000  (1 invoice)   -> hidden by HAVING
-- Also: 2 Unpaid invoices not yet due (excluded by date filter),
--       and a Void invoice that is past due (excluded by status).
-- ------------------------------------------------------------
INSERT INTO Invoices (matter_id, amount, issue_date, due_date, status) VALUES
    -- Paid (8)
    (1,  42000.00, DATE_SUB(CURDATE(), INTERVAL 200 DAY), DATE_SUB(CURDATE(), INTERVAL 170 DAY), 'Paid'),
    (5,  36000.00, DATE_SUB(CURDATE(), INTERVAL 150 DAY), DATE_SUB(CURDATE(), INTERVAL 120 DAY), 'Paid'),
    (12, 55000.00, DATE_SUB(CURDATE(), INTERVAL 300 DAY), DATE_SUB(CURDATE(), INTERVAL 270 DAY), 'Paid'),
    (2,  28500.00, DATE_SUB(CURDATE(), INTERVAL 180 DAY), DATE_SUB(CURDATE(), INTERVAL 150 DAY), 'Paid'),
    (3,  19000.00, DATE_SUB(CURDATE(), INTERVAL 100 DAY), DATE_SUB(CURDATE(), INTERVAL 70 DAY),  'Paid'),
    (7,  61000.00, DATE_SUB(CURDATE(), INTERVAL 220 DAY), DATE_SUB(CURDATE(), INTERVAL 190 DAY), 'Paid'),
    (4,  24000.00, DATE_SUB(CURDATE(), INTERVAL 90 DAY),  DATE_SUB(CURDATE(), INTERVAL 60 DAY),  'Paid'),
    (14, 47000.00, DATE_SUB(CURDATE(), INTERVAL 260 DAY), DATE_SUB(CURDATE(), INTERVAL 230 DAY), 'Paid'),

    -- Unpaid (8): 6 overdue, 2 not yet due
    (2,   6000.00, DATE_SUB(CURDATE(), INTERVAL 70 DAY),  DATE_SUB(CURDATE(), INTERVAL 40 DAY),  'Unpaid'),
    (2,   6000.00, DATE_SUB(CURDATE(), INTERVAL 55 DAY),  DATE_SUB(CURDATE(), INTERVAL 25 DAY),  'Unpaid'),
    (9,   9500.00, DATE_SUB(CURDATE(), INTERVAL 80 DAY),  DATE_SUB(CURDATE(), INTERVAL 50 DAY),  'Unpaid'),
    (9,   7000.00, DATE_SUB(CURDATE(), INTERVAL 50 DAY),  DATE_SUB(CURDATE(), INTERVAL 20 DAY),  'Unpaid'),
    (15,  8000.00, DATE_SUB(CURDATE(), INTERVAL 60 DAY),  DATE_SUB(CURDATE(), INTERVAL 30 DAY),  'Unpaid'),
    (1,  11000.00, DATE_SUB(CURDATE(), INTERVAL 45 DAY),  DATE_SUB(CURDATE(), INTERVAL 15 DAY),  'Unpaid'),
    (5,  15000.00, DATE_SUB(CURDATE(), INTERVAL 10 DAY),  DATE_ADD(CURDATE(), INTERVAL 20 DAY),  'Unpaid'),
    (7,  22000.00, DATE_SUB(CURDATE(), INTERVAL 5 DAY),   DATE_ADD(CURDATE(), INTERVAL 25 DAY),  'Unpaid'),

    -- Void (4)
    (10,  5000.00, DATE_SUB(CURDATE(), INTERVAL 120 DAY), DATE_SUB(CURDATE(), INTERVAL 90 DAY),  'Void'),
    (11,  3200.00, DATE_SUB(CURDATE(), INTERVAL 100 DAY), DATE_SUB(CURDATE(), INTERVAL 70 DAY),  'Void'),
    (13, 12000.00, DATE_SUB(CURDATE(), INTERVAL 140 DAY), DATE_SUB(CURDATE(), INTERVAL 110 DAY), 'Void'),
    (6,   4500.00, DATE_SUB(CURDATE(), INTERVAL 60 DAY),  DATE_SUB(CURDATE(), INTERVAL 30 DAY),  'Void');

-- ------------------------------------------------------------
-- Quick sanity check (expected: 12, 10, 15, 40, 20)
-- ------------------------------------------------------------
SELECT (SELECT COUNT(*) FROM Staff)       AS staff,
       (SELECT COUNT(*) FROM Clients)     AS clients,
       (SELECT COUNT(*) FROM Matters)     AS matters,
       (SELECT COUNT(*) FROM TimeEntries) AS time_entries,
       (SELECT COUNT(*) FROM Invoices)    AS invoices;
