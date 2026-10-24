"""Apply every migration plus the seed to a throwaway local Postgres and exercise the schema."""

import contextlib
import tempfile
from pathlib import Path

import pgserver

HERE = Path(__file__).resolve().parent
MIGRATIONS = sorted((HERE / "migrations").glob("*.sql"))
SEED = HERE / "seed.sql"

SUPABASE_STUBS = """
create role anon nologin;
create role authenticated nologin;
create publication supabase_realtime;
"""

CHECKS = [
    (
        "tables",
        "select string_agg(tablename, ', ' order by tablename) from pg_tables where schemaname='public'",
    ),
    (
        "realtime",
        "select string_agg(tablename, ', ' order by tablename) from pg_publication_tables where pubname='supabase_realtime'",
    ),
    ("policies", "select string_agg(tablename, ', ' order by tablename) from pg_policies"),
    (
        "seed",
        "select string_agg(c.full_name || ' owns ' || p.id, ', ' order by p.id) from residents r join pillows p on p.resident_id=r.id join resident_contacts rc on rc.resident_id=r.id and rc.role='owner' join contacts c on c.id=rc.contact_id",
    ),
]

MANY_TO_MANY = """
insert into residents (id, full_name, preferred_name) values ('00000000-0000-0000-0000-0000000000a1','Dad Test','Dad');
insert into resident_contacts values ('00000000-0000-0000-0000-0000000000a1','00000000-0000-0000-0000-000000000002','son','owner',1);
insert into contacts (id, full_name, phone) values ('00000000-0000-0000-0000-0000000000c2','Nurse Test','+15555550101');
insert into resident_contacts values ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000c2','nurse','contact',2);
insert into contacts (id, full_name, phone) values ('00000000-0000-0000-0000-0000000000c3','Spare Test','+15555550102');
"""

TRIPS = """
insert into events (pillow_id, event_type, device_ts) values
 ('mum','bed_exit','2026-10-24 02:00+00'), ('mum','bed_return','2026-10-24 02:07+00'),
 ('mum','bed_exit','2026-10-24 04:00+00'),
 ('mum','bed_exit','2026-10-24 05:00+00'), ('mum','bed_return','2026-10-24 05:12+00');
"""

BAD = [
    (
        "bad phone",
        "insert into contacts (full_name, phone) values ('x','5551234')",
        "select count(*) from contacts where full_name='x'",
    ),
    (
        "bad command",
        "insert into commands (pillow_id, cmd) values ('mum','explode')",
        "select count(*) from commands where cmd='explode'",
    ),
    (
        "duplicate priority",
        "insert into resident_contacts values ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000c3','x','contact',1)",
        "select count(*) from resident_contacts where relationship='x'",
    ),
    (
        "ack without time",
        "insert into incidents (pillow_id, kind, acked_by) values ('mum','no_return','00000000-0000-0000-0000-000000000002')",
        "select count(*) from incidents",
    ),
]

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    db = pgserver.get_server(tmp, cleanup_mode="stop")
    db.psql(SUPABASE_STUBS)
    for migration in MIGRATIONS:
        db.psql(migration.read_text(encoding="utf-8"))
    db.psql(SEED.read_text(encoding="utf-8"))
    db.psql(SEED.read_text(encoding="utf-8"))  # twice: the seed must be re-runnable
    for name, sql in CHECKS:
        print(f"{name}: {db.psql(sql).strip().splitlines()[2].strip()}")
    db.psql(MANY_TO_MANY)
    print(
        "carer watches:",
        db.psql(
            "select count(*) from resident_contacts where contact_id='00000000-0000-0000-0000-000000000002'"
        )
        .strip()
        .splitlines()[2]
        .strip(),
        "residents",
    )
    print(
        "Margaret has:",
        db.psql(
            "select count(*) from resident_contacts where resident_id='00000000-0000-0000-0000-000000000001'"
        )
        .strip()
        .splitlines()[2]
        .strip(),
        "carers",
    )
    db.psql(TRIPS)
    print("night_trips:")
    print(
        db.psql(
            "select to_char(left_at at time zone 'UTC','HH24:MI') as left_at, round(trip_min::numeric,1) as trip_min from night_trips order by left_at"
        )
    )
    for name, sql, count_sql in BAD:
        with contextlib.suppress(Exception):
            db.psql(sql)
        rows = db.psql(count_sql).strip().splitlines()[2].strip()
        print(f"{name}: {'REJECTED' if rows == '0' else 'ACCEPTED (unexpected)'}")
