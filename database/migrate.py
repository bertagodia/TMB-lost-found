"""Apply ordered SQL migrations transactionally; never rewrite applied migrations."""
import argparse
import hashlib
import os
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).with_name('migrations')


def migrate(dsn, folder=MIGRATIONS):
    with psycopg.connect(dsn) as conn:
        # Serializes independent deployment processes as well as individual migrations.
        conn.execute('SELECT pg_advisory_xact_lock(734103001)')
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
            conn.execute(raw.decode('utf-8'))
            conn.execute('INSERT INTO public.tmb_schema_migrations(version,sha256) VALUES (%s,%s)', (path.name,digest))
            applied[path.name] = digest
        return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        parser.exit(1, 'Set DATABASE_URL first.\n')
    print(f'Database ready: {migrate(dsn)} migrations verified.')


if __name__ == '__main__':
    main()
