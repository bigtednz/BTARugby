"""Apply a SQL Server script with GO batch separators."""

from __future__ import annotations

import argparse
import os
import re
import sys

try:
    import pyodbc
except ImportError:  # pragma: no cover
    pyodbc = None


DEFAULT_CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=BIGTEDS;"
    "DATABASE=RugbyAnalytics;"
    "Trusted_Connection=yes;"
    "Encrypt=no;"
    "TrustServerCertificate=yes;"
)


def split_batches(sql_text: str) -> list[str]:
    return [batch.strip() for batch in re.split(r"^\s*GO\s*$", sql_text, flags=re.IGNORECASE | re.MULTILINE) if batch.strip()]


def run(path: str) -> None:
    if pyodbc is None:
        raise RuntimeError("pyodbc is required for SQL Server access")
    connection_string = os.getenv("BTA_SQL_CONNECTION_STRING") or DEFAULT_CONNECTION_STRING
    with open(path, "r", encoding="utf-8") as handle:
        batches = split_batches(handle.read())
    conn = pyodbc.connect(connection_string, autocommit=False)
    cursor = conn.cursor()
    for index, batch in enumerate(batches, start=1):
        try:
            cursor.execute(batch)
            while cursor.nextset():
                pass
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(f"Failed batch {index} in {path}: {exc}") from exc
    conn.commit()
    conn.close()
    print(f"Applied {path}: {len(batches)} batches")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a SQL Server script using pyodbc")
    parser.add_argument("path")
    args = parser.parse_args()
    run(args.path)


if __name__ == "__main__":
    main()
