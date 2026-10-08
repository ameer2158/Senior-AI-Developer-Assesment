"""
Meridian Technologies — Assessment Database Setup
Run once to create and populate meridian.db in the current directory.
Usage: python setup_database.py
"""

import sqlite3
from datetime import date

DB_PATH = "meridian.db"


def setup():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()

    # ── Schema ──────────────────────────────────────────────────────────────

    c.executescript("""
    CREATE TABLE IF NOT EXISTS departments (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        budget_gbp  INTEGER NOT NULL,
        office_floor TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS employees (
        id           INTEGER PRIMARY KEY,
        name         TEXT NOT NULL,
        email        TEXT NOT NULL UNIQUE,
        role         TEXT NOT NULL,
        department_id INTEGER REFERENCES departments(id),
        manager_id   INTEGER REFERENCES employees(id),
        hire_date    TEXT NOT NULL,
        salary_gbp   INTEGER NOT NULL,
        location     TEXT NOT NULL CHECK(location IN ('London','Manchester','Remote')),
        is_active    INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS projects (
        id            INTEGER PRIMARY KEY,
        name          TEXT NOT NULL,
        description   TEXT,
        department_id INTEGER REFERENCES departments(id),
        lead_id       INTEGER REFERENCES employees(id),
        status        TEXT NOT NULL CHECK(status IN ('Active','On Hold','Completed','Cancelled')),
        start_date    TEXT NOT NULL,
        deadline      TEXT,
        budget_gbp    INTEGER
    );

    CREATE TABLE IF NOT EXISTS leave_requests (
        id            INTEGER PRIMARY KEY,
        employee_id   INTEGER REFERENCES employees(id),
        leave_type    TEXT NOT NULL CHECK(leave_type IN ('Annual','Sick','Compassionate','Study','Parental','Volunteering')),
        start_date    TEXT NOT NULL,
        end_date      TEXT NOT NULL,
        days_count    INTEGER NOT NULL,
        status        TEXT NOT NULL CHECK(status IN ('Pending','Approved','Declined','Cancelled')),
        approved_by_id INTEGER REFERENCES employees(id)
    );

    CREATE TABLE IF NOT EXISTS equipment (
        id            INTEGER PRIMARY KEY,
        employee_id   INTEGER REFERENCES employees(id),
        category      TEXT NOT NULL,
        model         TEXT NOT NULL,
        serial_number TEXT NOT NULL UNIQUE,
        assigned_date TEXT NOT NULL,
        returned_date TEXT
    );
    """)

    # ── Departments ──────────────────────────────────────────────────────────

    departments = [
        (1, "Engineering",          1_200_000, "Floor 3"),
        (2, "Data & AI",              800_000, "Floor 3"),
        (3, "People & Culture",       350_000, "Floor 1"),
        (4, "Finance",                400_000, "Floor 2"),
        (5, "Product",                600_000, "Floor 2"),
        (6, "Legal & Compliance",     300_000, "Floor 1"),
        (7, "IT",                     500_000, "Floor 3"),
    ]
    c.executemany("INSERT OR IGNORE INTO departments VALUES (?,?,?,?)", departments)

    # ── Employees ────────────────────────────────────────────────────────────

    employees = [
        # id, name, email, role, dept_id, manager_id, hire_date, salary, location, is_active
        (1,  "Sarah Chen",        "sarah.chen@meridian.tech",        "VP Engineering",           1,  None, "2019-03-11", 145000, "London",     1),
        (2,  "James Okafor",      "james.okafor@meridian.tech",      "Engineering Lead",         1,  1,    "2020-06-01", 112000, "London",     1),
        (3,  "Priya Nair",        "priya.nair@meridian.tech",        "Senior Engineer",          1,  2,    "2021-09-13", 95000,  "London",     1),
        (4,  "Tom Hargreaves",    "tom.hargreaves@meridian.tech",    "Software Engineer",        1,  2,    "2022-02-07", 78000,  "Manchester", 1),
        (5,  "Aisha Patel",       "aisha.patel@meridian.tech",       "Software Engineer",        1,  2,    "2023-05-22", 74000,  "Remote",     1),
        (6,  "Marcus Webb",       "marcus.webb@meridian.tech",       "Head of Data & AI",        2,  None, "2020-01-15", 130000, "London",     1),
        (7,  "Lena Fischer",      "lena.fischer@meridian.tech",      "Senior Data Scientist",    2,  6,    "2021-04-19", 98000,  "London",     1),
        (8,  "David Osei",        "david.osei@meridian.tech",        "ML Engineer",              2,  6,    "2022-08-08", 92000,  "Remote",     1),
        (9,  "Rachel Kim",        "rachel.kim@meridian.tech",        "HR Director",              3,  None, "2018-07-02", 110000, "London",     1),
        (10, "Oliver Marsh",      "oliver.marsh@meridian.tech",      "HR Business Partner",      3,  9,    "2021-11-30", 72000,  "London",     1),
        (11, "Fatima Al-Amin",    "fatima.alamin@meridian.tech",     "Finance Manager",          4,  None, "2019-10-14", 95000,  "London",     1),
        (12, "George Tan",        "george.tan@meridian.tech",        "Financial Analyst",        4,  11,   "2023-01-09", 65000,  "London",     1),
        (13, "Nina Johansson",    "nina.johansson@meridian.tech",    "Head of Product",          5,  None, "2020-03-23", 125000, "London",     1),
        (14, "Ravi Sharma",       "ravi.sharma@meridian.tech",       "Product Manager",          5,  13,   "2022-07-11", 88000,  "Manchester", 1),
        (15, "Clara Bouchard",    "clara.bouchard@meridian.tech",    "General Counsel",          6,  None, "2019-05-06", 140000, "London",     1),
        (16, "Ben Adeyemi",       "ben.adeyemi@meridian.tech",       "IT Manager",               7,  None, "2020-09-28", 90000,  "London",     1),
        (17, "Zoe Williams",      "zoe.williams@meridian.tech",      "Systems Administrator",    7,  16,   "2021-06-14", 68000,  "London",     1),
        (18, "Carlos Rivera",     "carlos.rivera@meridian.tech",     "Senior Engineer",          1,  2,    "2021-12-01", 94000,  "London",     1),
        (19, "Mei Tanaka",        "mei.tanaka@meridian.tech",        "Data Engineer",            2,  6,    "2023-03-06", 82000,  "Remote",     1),
        (20, "Ahmed Hassan",      "ahmed.hassan@meridian.tech",      "Software Engineer",        1,  2,    "2020-11-16", 80000,  "Manchester", 0),
    ]
    c.executemany("INSERT OR IGNORE INTO employees VALUES (?,?,?,?,?,?,?,?,?,?)", employees)

    # ── Projects ─────────────────────────────────────────────────────────────

    projects = [
        # id, name, description, dept_id, lead_id, status, start_date, deadline, budget
        (1, "Project Atlas",     "Redesign of the core data platform for real-time analytics",               2, 6,  "Active",    "2024-01-10", "2024-12-31", 350000),
        (2, "Project Helios",    "Internal HR self-service portal rebuild",                                   3, 9,  "Active",    "2024-03-01", "2024-09-30", 120000),
        (3, "Project Vega",      "Client-facing API gateway v2",                                              1, 2,  "Active",    "2024-02-15", "2025-01-31", 280000),
        (4, "Project Orion",     "Machine learning model for churn prediction",                               2, 7,  "Completed", "2023-06-01", "2024-01-31", 180000),
        (5, "Project Solaris",   "Vendor management platform integration",                                    4, 11, "On Hold",   "2024-04-01", "2024-11-30", 95000),
        (6, "Project Nova",      "Security posture review and tooling upgrade",                               7, 16, "Active",    "2024-05-01", "2024-10-31", 150000),
        (7, "Project Meridian X","Next-generation product discovery experiment",                              5, 13, "Active",    "2024-06-01", "2025-03-31", 400000),
        (8, "Project Cetus",     "Legacy data migration to cloud warehouse",                                  2, 8,  "Completed", "2023-01-15", "2023-12-31", 220000),
        (9, "Project Aquila",    "Compliance automation for GDPR reporting",                                  6, 15, "Active",    "2024-07-01", "2024-12-31", 110000),
        (10,"Project Lyra",      "Employee onboarding workflow automation",                                   3, 10, "Active",    "2024-08-01", "2025-02-28", 85000),
    ]
    c.executemany("INSERT OR IGNORE INTO projects VALUES (?,?,?,?,?,?,?,?,?)", projects)

    # ── Leave Requests ───────────────────────────────────────────────────────

    leave_requests = [
        # id, emp_id, type, start, end, days, status, approved_by
        (1,  3,  "Annual",       "2024-08-05", "2024-08-16", 10, "Approved",  2),
        (2,  5,  "Annual",       "2024-09-02", "2024-09-06",  5, "Approved",  2),
        (3,  7,  "Annual",       "2024-07-22", "2024-07-26",  5, "Approved",  6),
        (4,  4,  "Sick",         "2024-06-10", "2024-06-11",  2, "Approved",  2),
        (5,  12, "Annual",       "2024-10-14", "2024-10-18",  5, "Pending",   None),
        (6,  8,  "Study",        "2024-09-16", "2024-09-17",  2, "Approved",  6),
        (7,  14, "Annual",       "2024-08-19", "2024-08-23",  5, "Approved",  13),
        (8,  19, "Annual",       "2024-11-04", "2024-11-08",  5, "Pending",   None),
        (9,  17, "Compassionate","2024-07-01", "2024-07-03",  3, "Approved",  16),
        (10, 18, "Annual",       "2024-09-23", "2024-09-27",  5, "Approved",  2),
        (11, 5,  "Annual",       "2024-12-23", "2024-12-31",  7, "Pending",   None),
        (12, 3,  "Volunteering", "2024-10-04", "2024-10-04",  1, "Approved",  2),
    ]
    c.executemany("INSERT OR IGNORE INTO leave_requests VALUES (?,?,?,?,?,?,?,?)", leave_requests)

    # ── Equipment ────────────────────────────────────────────────────────────

    equipment = [
        # id, emp_id, category, model, serial, assigned_date, returned_date
        (1,  1,  "Laptop",   "MacBook Pro 14 M3",  "MBP-2024-001", "2024-01-15", None),
        (2,  2,  "Laptop",   "MacBook Pro 14 M3",  "MBP-2024-002", "2024-01-15", None),
        (3,  3,  "Laptop",   "MacBook Pro 14 M3",  "MBP-2023-045", "2021-09-13", None),
        (4,  4,  "Laptop",   "MacBook Pro 14 M3",  "MBP-2022-031", "2022-02-07", None),
        (5,  5,  "Laptop",   "MacBook Air 13 M2",  "MBA-2023-022", "2023-05-22", None),
        (6,  6,  "Laptop",   "MacBook Pro 16 M3",  "MBP-2024-006", "2024-01-15", None),
        (7,  7,  "Laptop",   "MacBook Pro 14 M3",  "MBP-2021-088", "2021-04-19", None),
        (8,  8,  "Laptop",   "MacBook Air 13 M2",  "MBA-2022-055", "2022-08-08", None),
        (9,  9,  "Laptop",   "MacBook Pro 16 M3",  "MBP-2018-003", "2018-07-02", None),
        (10, 10, "Laptop",   "MacBook Air 13 M2",  "MBA-2021-099", "2021-11-30", None),
        (11, 20, "Laptop",   "MacBook Pro 14 M3",  "MBP-2020-044", "2020-11-16", "2024-03-01"),
        (12, 3,  "Monitor",  "Dell U2723D 27\"",   "MON-2021-045", "2021-09-13", None),
        (13, 2,  "Monitor",  "Dell U2723D 27\"",   "MON-2020-012", "2020-06-01", None),
        (14, 1,  "Monitor",  "LG 27UK850 27\"",    "MON-2024-001", "2024-01-15", None),
    ]
    c.executemany("INSERT OR IGNORE INTO equipment VALUES (?,?,?,?,?,?,?)", equipment)

    conn.commit()
    conn.close()
    print(f"✓ Database created: {DB_PATH}")
    print("  Tables: departments, employees, projects, leave_requests, equipment")

    # Quick summary
    conn = sqlite3.connect(DB_PATH)
    for table in ["departments", "employees", "projects", "leave_requests", "equipment"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n} rows")
    conn.close()


if __name__ == "__main__":
    setup()
