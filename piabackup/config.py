# encoding: utf-8
import logging

import piabackup.common as common


class Config:
    def __init__(self):
        self.repo = ""
        self.full_check_frequency = common.DEFAULT_CHECK_IVAL
        self.prune_frequency = common.DEFAULT_PRUNE_IVAL
        self.error_check_frequency = common.DEFAULT_ERROR_CHECK_IVAL
        self.bitrot_detection = False
        self.prune_enabled = False
        self.no_lock = False
        self.make_vanished_permanent = True
        self.auto_discovery = False
        self.disclaimer_accepted = False
        self.update_check_enabled = True
        self.update_check_frequency = common.DEFAULT_UPDATE_CHECK_IVAL
        self.update_check_toast_interval = common.DEFAULT_UPDATE_TOAST_IVAL
        self.prescan_file_limit = common.DEFAULT_FILE_SCAN_LIMIT
        self.load()

    def load(self):
        try:
            with common.db_conn as conn:
                cursor = conn.execute("SELECT key, value FROM config")
                data = {row[0]: row[1] for row in cursor.fetchall()}
                
                self.repo = data.get("repo", "")
                self.full_check_frequency = int(data.get("full_check_frequency", common.DEFAULT_CHECK_IVAL))
                self.prune_frequency = int(data.get("prune_frequency", common.DEFAULT_PRUNE_IVAL))
                self.error_check_frequency = int(data.get("error_check_frequency", common.DEFAULT_ERROR_CHECK_IVAL))
                self.bitrot_detection = bool(int(data.get("bitrot_detection", "1")))
                self.prune_enabled = bool(int(data.get("prune_enabled", "0")))
                self.no_lock = bool(int(data.get("no_lock", "0")))
                self.make_vanished_permanent = bool(int(data.get("make_vanished_permanent", "1")))
                self.auto_discovery = bool(int(data.get("auto_discovery", "0")))
                self.disclaimer_accepted = bool(int(data.get("disclaimer_accepted", "0")))
                self.update_check_enabled = bool(int(data.get("update_check_enabled", "1")))
                self.update_check_frequency = int(data.get("update_check_frequency", common.DEFAULT_UPDATE_CHECK_IVAL))
                self.update_check_toast_interval = int(data.get("update_check_toast_interval", common.DEFAULT_UPDATE_TOAST_IVAL))
                self.prescan_file_limit = int(data.get("prescan_file_limit", common.DEFAULT_FILE_SCAN_LIMIT))
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            raise

    def save(self):
        try:
            data = {
                "repo": self.repo,
                "full_check_frequency": str(self.full_check_frequency),
                "prune_frequency": str(self.prune_frequency),
                "error_check_frequency": str(self.error_check_frequency),
                "bitrot_detection": "1" if self.bitrot_detection else "0",
                "prune_enabled": "1" if self.prune_enabled else "0",
                "no_lock": "1" if self.no_lock else "0",
                "make_vanished_permanent": "1" if self.make_vanished_permanent else "0",
                "auto_discovery": "1" if self.auto_discovery else "0",
                "disclaimer_accepted": "1" if self.disclaimer_accepted else "0",
                "update_check_enabled": "1" if self.update_check_enabled else "0",
                "update_check_frequency": str(self.update_check_frequency),
                "update_check_toast_interval": str(self.update_check_toast_interval),
                "prescan_file_limit": str(self.prescan_file_limit)
            }
            with common.db_conn as conn:
                for k, v in data.items():
                    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (k, v))
        except Exception as e:
            logging.error(f"Failed to save config: {e}")
            raise
