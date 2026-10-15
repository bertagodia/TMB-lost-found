"""Apply ordered SQL migrations transactionally; never rewrite applied migrations."""
import argparse
import hashlib
import os
from pathlib import Path

import psycopg
from psycopg import sql

MIGRATIONS = Path(__file__).with_name('migrations')
INTEGRATION_MIGRATION = '002_prototype_integration.sql'
APPLICATION_TABLES = frozenset({
    'extraction_runs', 'found_objects', 'http_submissions', 'lost_reports',
    'object_reviews', 'photos', 'report_contacts', 'report_matches',
})


def apply_migration(conn, path, raw):
    if path.name == INTEGRATION_MIGRATION:
        # Migration 001 already contains these integrated tables and photo fields.
        conn.execute('''CREATE TABLE http_submissions (
            object_id text PRIMARY KEY REFERENCES found_objects(id),
            request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$')
        )''')
        return
    conn.execute(raw.decode('utf-8'))


def migrate(dsn, folder=MIGRATIONS):
    with psycopg.connect(dsn) as conn:
        conn.execute('SELECT pg_advisory_lock(734103001)')
        try:
            return _migrate_locked(conn, folder)
        finally:
            conn.execute('SELECT pg_advisory_unlock(734103001)')


def _migrate_locked(conn, folder):
    conn.execute('CREATE SCHEMA IF NOT EXISTS tmb')
    conn.execute('SET search_path = tmb, pg_catalog')
    conn.execute('CREATE TABLE IF NOT EXISTS public.tmb_schema_migrations '
                 '(version text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT clock_timestamp())')
    applied = dict(conn.execute('SELECT version, sha256 FROM public.tmb_schema_migrations').fetchall())
    files = sorted(folder.glob('[0-9][0-9][0-9]_*.sql'))
    known = {path.name for path in files}
    if set(applied) - known:
        raise ValueError('Database contains migrations absent from this checkout')
    for path in files:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if path.name in applied:
            if applied[path.name] != digest:
                raise ValueError(f'Applied migration changed: {path.name}')
            continue
        if applied and path.name < max(applied):
            raise ValueError('Cannot insert a migration before an applied version')
        conn.execute('SET search_path = tmb, pg_catalog')
        apply_migration(conn, path, raw)
        conn.execute('INSERT INTO public.tmb_schema_migrations(version,sha256) VALUES (%s,%s)', (path.name,digest))
        applied[path.name] = digest
    return len(files)


def repair_empty_application_tables(dsn):
    with psycopg.connect(dsn) as conn:
        ledger = conn.execute("SELECT to_regclass('public.tmb_schema_migrations')").fetchone()[0]
        if ledger:
            applied = conn.execute('SELECT count(*) FROM public.tmb_schema_migrations').fetchone()[0]
            if applied:
                raise ValueError('No es repararà una base de dades amb migracions registrades.')

        tables = conn.execute('''SELECT schemaname, tablename FROM pg_tables
            WHERE schemaname IN ('public', 'tmb') AND tablename <> 'tmb_schema_migrations'
            ORDER BY schemaname, tablename''').fetchall()
        unexpected = [(schema, table) for schema, table in tables if table not in APPLICATION_TABLES]
        if unexpected:
            raise ValueError(f'Hi ha taules fora de l’esquema WP4; no s’ha esborrat res: {unexpected}')

        counts = []
        for schema, table in tables:
            count = conn.execute(
                sql.SQL('SELECT count(*) FROM {}.{}').format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            ).fetchone()[0]
            if count:
                counts.append((schema, table, count))
        if counts:
            raise ValueError(f'Hi ha dades; no s’ha esborrat res: {counts}')

        for schema, table in tables:
            conn.execute(
                sql.SQL('DROP TABLE {}.{} CASCADE').format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            )
        return len(tables)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair-empty', action='store_true',
                        help='Drop only empty WP4 tables when no migrations are recorded.')
    args = parser.parse_args()
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        parser.exit(1, 'Set DATABASE_URL first.\n')
    if args.repair_empty:
        print(f'Removed {repair_empty_application_tables(dsn)} empty WP4 tables.')
    print(f'Database ready: {migrate(dsn)} migrations verified.')


if __name__ == '__main__':
    main()
