# encoding: utf-8
import sqlite3

import piabackup.common as common


class DB:
    @staticmethod
    def init_db():
        if common.db_conn is not None:
            raise Exception()
        common.db_conn = sqlite3.connect(common.DB_PATH)
        with common.db_conn as conn:
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
                "make_vanished_permanent": "1",
                "auto_discovery": "0",
                "disclaimer_accepted": "0",
                "update_check_enabled": "1",
                "update_check_frequency": str(common.DEFAULT_UPDATE_CHECK_IVAL),
                "update_check_toast_interval": str(common.DEFAULT_UPDATE_TOAST_IVAL),
                "prescan_file_limit": str(common.DEFAULT_FILE_SCAN_LIMIT)
            }
            for k, v in defaults_config.items():
                conn.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
            
            # Default status
            defaults_status = {
                "last_full_check": "0",
                "last_full_check_segment": "-1"
            }
            for k, v in defaults_status.items():
                conn.execute("INSERT OR IGNORE INTO status (key, value) VALUES (?, ?)", (k, v))
