"""Debug ingestion_log duplicates."""
import sqlite3

conn = sqlite3.connect("finance.db")

# Check duplicates
print("=== Files with multiple log entries ===")
c = conn.execute("""
    SELECT source_file, COUNT(*) as cnt
    FROM ingestion_log
    GROUP BY source_file
    HAVING cnt > 1
    ORDER BY cnt DESC
    LIMIT 10
""")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]} entries")

print("\n=== Sample hash comparison ===")
c = conn.execute("""
    SELECT source_file, source_hash, status
    FROM ingestion_log
    WHERE source_file = ?
""", ("monthly-statement.pdf",))
for row in c.fetchall():
    print(f"  {row[0]}: hash={row[1][:24]}... status={row[2]}")

print("\n=== All log statuses ===")
c = conn.execute("SELECT status, COUNT(*) FROM ingestion_log GROUP BY status")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== Summary ===")
c = conn.execute("SELECT COUNT(DISTINCT source_file) FROM ingestion_log")
print(f"  Unique files: {c.fetchone()[0]}")
c = conn.execute("SELECT COUNT(*) FROM ingestion_log")
print(f"  Total log entries: {c.fetchone()[0]}")
c = conn.execute("SELECT COUNT(DISTINCT source_hash) FROM ingestion_log")
print(f"  Unique hashes: {c.fetchone()[0]}")

conn.close()
