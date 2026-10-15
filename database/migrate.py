"""Apply ordered SQL migrations transactionally; never rewrite applied migrations."""
import argparse
import hashlib
import os
from pathlib import Path
import re

import psycopg

MIGRATIONS = Path(__file__).with_name('migrations')


def migration_sql(raw):
    """Remove only the template's outer transaction, not PL/pgSQL BEGIN blocks.

    Hashes always use the original bytes. Transaction control within migration
    bodies is unsupported: the runner owns the transaction for the whole batch.
    """
    text = raw.decode('utf-8')
    leading = r'\A((?:\s|--[^\n]*(?:\n|$))*)BEGIN\s*;'
    if re.match(leading, text, re.IGNORECASE):
        trailing = r'COMMIT\s*;((?:\s|--[^\n]*(?:\n|$))*)\Z'
        if not re.search(trailing, text, re.IGNORECASE):
            raise ValueError('Migration BEGIN must have a matching outer COMMIT')
        text = re.sub(leading, r'\1', text, count=1, flags=re.IGNORECASE)
        text = re.sub(trailing, r'\1', text, count=1, flags=re.IGNORECASE)
    return text


def migrate(dsn, folder=MIGRATIONS):
    with psycopg.connect(dsn) as conn:
        conn.execute('SET LOCAL search_path TO public')
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
            conn.execute(migration_sql(raw))
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
