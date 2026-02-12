# encoding: utf-8
import json
from pathlib import Path
import sqlite3
import time
import piabackup.common as common

class BackupDir:
    def __init__(self, id, path, enabled='auto', fastscan_fingerprint="1", error='', last_run=0.0, frequency=common.DEFAULT_FREQ, next_run=0.0, bitrot_snap="", summary="", last_prune=0.0):
        self.id = id
        self.path = Path(path)
        self.enabled = enabled
        self.fastscan_fingerprint = str(fastscan_fingerprint)
        self.error = error
        self.last_run = float(last_run)
        self.frequency = frequency
        self.next_run = float(next_run)
        self.bitrot_snap = bitrot_snap
        self.summary = summary
        self.last_prune = float(last_prune)

    def get_current_snapshot_id(self):
        return json.loads(self.summary)['snapshot_id']

    def get_tag(self):
        return self.path.as_posix()

    @staticmethod
    def load_dirs():
        with sqlite3.connect(common.DB_PATH) as conn:
            return [BackupDir(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]) 
                            for r in conn.execute("SELECT id, path, enabled, fastscan_fingerprint, error, last_run, frequency, next_run, bitrot_snap, summary, last_prune FROM backup_dirs ORDER BY id").fetchall()]

    def delete(self, conn):
        if self.id is None:
             raise ValueError("Cannot delete BackupDir without id")
        conn.execute("DELETE FROM backup_dirs WHERE id=?", (self.id,))

    # UI save (insert or update) - does not update fastscan_fingerprint, error, last_run, next_run or bitrot_snap as those are managed by the worker thread and should not be changed from the UI. Only enabled and frequency can be changed from the UI.
    def save_ui(self, conn):
        if self.id is None:
            conn.execute("INSERT INTO backup_dirs (path, enabled, fastscan_fingerprint, error, last_run, frequency, next_run, bitrot_snap, summary, last_prune) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                         (str(self.path), self.enabled, self.fastscan_fingerprint, self.error, self.last_run, self.frequency, self.next_run, self.bitrot_snap, self.summary, self.last_prune))
        else:
            conn.execute("UPDATE backup_dirs SET enabled=?, frequency=? WHERE id=?", 
                                     (self.enabled, self.frequency, self.id))

    def schedule_run_now(self, conn):
        conn.execute("UPDATE backup_dirs SET next_run=0 WHERE id=?", (self.id,))

    @staticmethod
    def fetch_overdue_backup_row(conn):
        row = conn.execute("""
                SELECT id, path, enabled, fastscan_fingerprint, error, last_run, frequency, next_run, bitrot_snap, summary, last_prune 
                FROM backup_dirs 
                WHERE enabled != 'no' AND next_run <= ?
                ORDER BY next_run ASC LIMIT 1
            """, (time.time(),)).fetchone()
        common.log.debug(f"fetch_overdue_backup_row: {row}")
        if not row:
            return None
        return BackupDir(*row)

    @staticmethod
    def fetch_enabled_backup_rows(conn):
        rows = conn.execute("""
                SELECT id, path, enabled, fastscan_fingerprint, error, last_run, frequency, next_run, bitrot_snap, summary, last_prune 
                FROM backup_dirs 
                WHERE enabled != 'no'
                ORDER BY next_run ASC
            """).fetchall()
        if common.IS_DEBUGGER_PRESENT:
            common.log.debug(f"fetch_enabled_backup_rows: {rows}")
        return [BackupDir(*row) for row in rows]

    def save_backup_result(self, conn):
        if self.id is None:
            raise ValueError("Cannot save backup result for BackupDir without id")
        self.last_run = time.time()
        if self.error:
            self.next_run = self.last_run + 300
        else:
            self.next_run = self.last_run + (self.frequency if self.frequency > common.MIN_FREQUENCY else common.MIN_FREQUENCY)
        cur = conn.execute("UPDATE backup_dirs SET error=?, last_run=?, next_run=?, summary=?, fastscan_fingerprint=?, bitrot_snap=?, last_prune=? WHERE id=?", 
                    (self.error, self.last_run, self.next_run, self.summary, self.fastscan_fingerprint, self.bitrot_snap, self.last_prune, self.id))
        if cur.rowcount != 1:
            raise Exception(f"Failed to update backup result for BackupDir with id {self.id}")
