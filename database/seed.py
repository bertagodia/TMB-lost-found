"""Insert idempotent, fictitious development records (no real image files)."""
import argparse
import os
from pathlib import Path

import psycopg


def seed(dsn):
    with psycopg.connect(dsn) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(734103002)')
        conn.execute(Path(__file__).with_name('demo.sql').read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', required=True, action='store_true', help='Confirm use of fictitious development records')
    parser.parse_args()
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        parser.exit(1,'Set DATABASE_URL first.\n')
    seed(dsn)
    print('Demo records ready; photo references are placeholders, not real files.')


if __name__ == '__main__':
    main()
