# encoding: utf-8
import json
import logging
import time
from pathlib import Path

import piabackup.common as common


class BackupDir:
    def __init__(self, id, path, enabled='auto', fastscan_fingerprint="1", error='', last_run=0.0, frequency=common.DEFAULT_FREQ, next_run=0.0, bitrot_snap="", summary="", last_prune=0.0, n_backups_since_last_perm_tag=0, iexclude=''):
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
        self.n_backups_since_last_perm_tag = int(n_backups_since_last_perm_tag)
        self.iexclude = iexclude

    def get_current_snapshot_id(self):
        return json.loads(self.summary)['snapshot_id']

    def get_tag(self):
        return self.path.as_posix()

    @staticmethod
    def load_dirs():
        with common.db_conn as conn:
            return [BackupDir(*r) 
                            for r in conn.execute("SELECT id, path, enabled, fastscan_fingerprint, error, last_run, frequency, next_run, bitrot_snap, summary, last_prune, n_backups_since_last_perm_tag, iexclude FROM backup_dirs ORDER BY id").fetchall()]

    def delete(self):
        if self.id is None:
             raise ValueError("Cannot delete BackupDir without id")
        common.db_conn.execute("DELETE FROM backup_dirs WHERE id=?", (self.id,))

    # UI save (insert or update) - does not update fastscan_fingerprint, error, last_run, next_run or bitrot_snap as those are managed by the worker thread and should not be changed from the UI. Only enabled and frequency can be changed from the UI.
    def save_ui(self):
        if self.id is None:
            common.db_conn.execute("INSERT INTO backup_dirs (path, enabled, fastscan_fingerprint, error, last_run, frequency, next_run, bitrot_snap, summary, last_prune, n_backups_since_last_perm_tag, iexclude) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                         (str(self.path), self.enabled, self.fastscan_fingerprint, self.error, self.last_run, self.frequency, self.next_run, self.bitrot_snap, self.summary, self.last_prune, self.n_backups_since_last_perm_tag, self.iexclude))
        else:
            common.db_conn.execute("UPDATE backup_dirs SET enabled=?, frequency=?, iexclude=? WHERE id=?", 
                                     (self.enabled, self.frequency, self.iexclude, self.id))

    def schedule_run_now(self):
        common.db_conn.execute("UPDATE backup_dirs SET next_run=0 WHERE id=?", (self.id,))

    @staticmethod
    def fetch_overdue_backup_row():
        row = common.db_conn.execute("""
                SELECT id, path, enabled, fastscan_fingerprint, error, last_run, frequency, next_run, bitrot_snap, summary, last_prune, n_backups_since_last_perm_tag, iexclude 
                FROM backup_dirs 
                WHERE enabled != 'no' AND next_run <= ?
                ORDER BY next_run ASC LIMIT 1
            """, (time.time(),)).fetchone()
        logging.debug(f"fetch_overdue_backup_row: {row}")
        if not row:
            return None
        return BackupDir(*row)

    @staticmethod
    def fetch_enabled_backup_rows() -> list['BackupDir']:
        with common.db_conn as conn:
            rows = conn.execute("""
                    SELECT id, path, enabled, fastscan_fingerprint, error, last_run, frequency, next_run, bitrot_snap, summary, last_prune, n_backups_since_last_perm_tag, iexclude 
                    FROM backup_dirs 
                    WHERE enabled != 'no'
                    ORDER BY next_run ASC
                """).fetchall()
        return [BackupDir(*row) for row in rows]

    def save_backup_result(self):
        if self.id is None:
            raise ValueError("Cannot save backup result for BackupDir without id")
        self.last_run = time.time()
        if self.error:
            self.next_run = self.last_run + 300
        else:
            self.next_run = self.last_run + (self.frequency if self.frequency > common.MIN_FREQUENCY else common.MIN_FREQUENCY)
        with common.db_conn as conn:            
            cur = conn.execute("UPDATE backup_dirs SET error=?, last_run=?, next_run=?, summary=?, fastscan_fingerprint=?, bitrot_snap=?, last_prune=?, n_backups_since_last_perm_tag=? WHERE id=?", 
                        (self.error, self.last_run, self.next_run, self.summary, self.fastscan_fingerprint, self.bitrot_snap, self.last_prune, self.n_backups_since_last_perm_tag, self.id))
            if cur.rowcount != 1:
                raise Exception(f"Failed to update backup result for BackupDir with id {self.id}")
