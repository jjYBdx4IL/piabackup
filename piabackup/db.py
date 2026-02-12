# encoding: utf-8
import sqlite3
import time
import piabackup.common as common

class DB:
    @staticmethod
    def init_db():
        with sqlite3.connect(common.DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS status (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS backup_dirs (id INTEGER PRIMARY KEY, path TEXT, enabled TEXT, fastscan_fingerprint TEXT, error TEXT, last_run REAL, frequency INTEGER, next_run REAL, bitrot_snap TEXT, summary TEXT, last_prune REAL)")
            
            # Default config
            defaults_config = {
                "repo": "",
                "full_check_frequency": str(common.DEFAULT_CHECK_IVAL),
                "prune_frequency": str(common.DEFAULT_PRUNE_IVAL),
                "error_check_frequency": str(common.DEFAULT_ERROR_CHECK_IVAL),
                "bitrot_detection": "1",
                "prune_enabled": "0",
                "no_lock": "0",
                "auto_discovery": "0",
                "disclaimer_accepted": "0",
                "update_check_enabled": "1",
                "update_check_frequency": str(common.DEFAULT_UPDATE_CHECK_IVAL),
                "update_check_toast_interval": str(common.DEFAULT_UPDATE_TOAST_IVAL)
            }
            for k, v in defaults_config.items():
                conn.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
            
            # Default status
            defaults_status = {
                "last_full_check": "0",
                "last_full_check_segment": "0",
                "last_update_check": "0",
                "last_update_toast": "0",
                "cached_latest_version": ""
            }
            for k, v in defaults_status.items():
                conn.execute("INSERT OR IGNORE INTO status (key, value) VALUES (?, ?)", (k, v))

    @staticmethod
    def is_full_check_due(conn):
        last_full_check = float(conn.execute("SELECT value FROM status WHERE key = 'last_full_check'").fetchone()[0])
        full_check_frequency = float(conn.execute("SELECT value FROM config WHERE key = 'full_check_frequency'").fetchone()[0])
        return time.time() >= last_full_check + full_check_frequency
