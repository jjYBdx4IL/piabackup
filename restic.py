# encoding: utf-8
import contextlib
import datetime
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

import piabackup.common as common
from piabackup.config import Config



class Restic:
    def __init__(self):
        self.backup_default_cmd = ["restic",
                    "backup",
                    #"--files-from", str(rootsfn.absolute()),
                    #"--iexclude-file", str(excludesfn.absolute()),
                    "--compression", "max",
                    "--no-scan",
                    "--skip-if-unchanged",
                    #"--read-concurrency", "2", # makes it slower
                    ]
        if common.IS_ADMIN:
            self.backup_default_cmd.append("--use-fs-snapshot")

    def list_snapshots(self, cfg:Config, env, tag, latest_n=None) -> list:
        if tag is None:
            raise Exception("tag param is required for listing snapshots")
        cmd = ["restic",
                "snapshots",
                "--json",
                "--tag", tag,
                ]
        if latest_n is not None and int(latest_n) > 0:
            cmd.extend(["--latest", str(latest_n)])
        if cfg.no_lock:
            cmd.append("--no-lock")
        logging.info(f"running: {' '.join(cmd)}")
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        p = subprocess.Popen(cmd, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        rc = p.wait()
        if rc != 0:
            raise Exception(f"cmd failed: rc = {rc}, stderr = {stderr}")
        if common.IS_DEBUGGER_PRESENT:
            logging.debug(stdout)
        js = json.loads(stdout.splitlines()[0])
        if common.IS_DEBUGGER_PRESENT:
            logging.debug(json.dumps(js, indent=4))
        logging.info("successful")
        for s in js:
            s['_time'] = datetime.datetime.fromisoformat(s['time']).timestamp()
        #js.sort(key=lambda x: x['_time'])
        for i in range(0,len(js)-1):
            if js[i]['_time'] > js[i+1]['_time']:
                raise Exception(f"snapshot times are not in ascending order")
        return js

    def tag_snapshot(self, env, snap_id, tag, remove=False, no_lock=False):
        if snap_id is None or not isinstance(snap_id, str) or len(snap_id) == 0:
            raise Exception("snap_id param is required for tagging")
        if tag is None or not isinstance(tag, str) or len(tag) == 0:
            raise Exception("tag param is required for tagging")
        
        cmd = ["restic", "tag", snap_id]
        if remove:
            cmd.extend(["--remove", tag])
        else:
            cmd.extend(["--add", tag])
        
        if no_lock:
            cmd.append("--no-lock")
            
        logging.info(f"running: {' '.join(cmd)}")
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        p = subprocess.Popen(cmd, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        
        if p.returncode != 0:
            raise Exception(f"tag failed: {stderr}")
        logging.info("tag successful")

    def get_all_paths(self, env, no_lock=False) -> set[Path]:
        cmd = ["restic",
                "snapshots",
                "--json",
                ]
        if no_lock:
            cmd.append("--no-lock")
        logging.info(f"running: {' '.join(cmd)}")
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        p = subprocess.Popen(cmd, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        rc = p.wait()
        if rc != 0:
            raise Exception(f"cmd failed: rc = {rc}, stderr = {stderr}")
        
        js = json.loads(stdout)
        paths = set()
        for s in js:
            if 'paths' in s:
                for p in s['paths']:
                    paths.add(Path(p))
        return paths

    def check_bitrot(self, cfg:Config, env, tag:str, bitrot_snap:str) -> str:
        if tag is None:
            raise Exception("tag param is required for bitrot check")
        if bitrot_snap is None:
            raise Exception("bitrot_snap param is required for bitrot check")

        snaps = self.list_snapshots(cfg, env, tag)

        start_index = 1
        for i in range(0,len(snaps)):
            curr = snaps[i]
            if bitrot_snap == curr['id']:
                start_index = i + 1
                break

        last_checked_snap = bitrot_snap
        for i in range(start_index, len(snaps)):
            prev = snaps[i-1]
            curr = snaps[i]

            cmd = ["restic",
                    "diff", prev['id'], curr['id'],
                    "--json",
                    ]
            if cfg.no_lock:
                cmd.append("--no-lock")

            logging.info(f"running: {' '.join(cmd)} ({curr['time']})")
            
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            p = subprocess.Popen(cmd, encoding='utf-8', text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
            stdout, stderr = p.communicate()
            rc = p.wait()
            if rc != 0:
                raise Exception(f"cmd failed: rc = {rc}, stderr={stderr}")
            
            li = 0
            n_found = 0
            for l in stdout.splitlines():
                li = li + 1
                if l.startswith("{"):
                    js = json.loads(l)
                    if js['message_type'] == 'statistics':
                        logging.debug(l)
                    # {"message_type":"change","path":"/C/Jts/knkeabmblimgifcdgaicnbbhgdgecimiohobcbll/Tue.trd","modifier":"M"}
                    elif js['message_type'] == 'change':
                        if '?' in js['modifier']:
                            logging.error(f"bit rot detected: {l}")
                            n_found = n_found + 1
                    else:
                        raise Exception(f"unexpected line data {l} in line {li}")
                elif li != 1:
                    raise Exception(f"unexpected line data {l} in line {li}")
                
            if n_found > 0:
                # if cmdline_args.check_bitrot_ignore and cmdline_args.check_bitrot_ignore == curr['id']:
                #     logging.error(f"bit rot detected but ignoring because of command line argument")
                # else:
                raise Exception(f"bit rot detected, aborting")
            
            last_checked_snap = curr['id']
            if common.shutdown_requested: break

        logging.info("successful")
        return last_checked_snap

    def run_backup_cmd(self, backup_path:Path, env, docheck=False, no_lock=False, iexclude:str=None):
        if backup_path is None:
            raise Exception("no backup_path defined")
        if env is None:
            raise Exception("no env param defined")
        cmd = self.backup_default_cmd.copy()
        if no_lock:
            cmd.append("--no-lock")
        cmd.append("--json")
        cmd.append("--quiet")
        if docheck:
            cmd.append("--force")
            cmd.append("--no-cache")
        cmd.extend(["--tag", backup_path.as_posix()])
        
        with common.handle_iexclude_file(iexclude, backup_path) as iexclude_path:
            if iexclude_path:
                cmd.extend(["--iexclude-file", iexclude_path])

            cmd.append(str(backup_path))

            logging.info(f"running: {common.quote_command(cmd)}")
    
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    
            p = subprocess.Popen(cmd, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
            stdout, stderr = p.communicate()
            
            summary = None
            err = False
            for l in stdout.splitlines() + stderr.splitlines():
                if l.startswith("{"):
                    js = json.loads(l)
                    if js['message_type'] == 'summary':
                        logging.info(l)
                        summary = l
                    # elif js['message_type'] == 'exit_error':
                    #     logging.warning(l)
                    elif js['message_type'] == 'error':
                        # if js['error']['message'].startswith("incomplete metadata for "):
                        #     logging.warning(l)
                        # this is to 'support' (or rather ignore) the cygin symlinks issue... instead please just don't use them
                        # elif js['error']['message'].endswith(": unsupported file type \"irregular\""):
                        #     logging.warning(l)
                        # elif js['error']['message'].startswith("failed to create snapshot for "):
                        #     logging.warning(l)
                        # else:
                        logging.error(l)
                        err = True
                    else:
                        logging.error(f"unexpected output: {l}")
                        err = True

            rc = p.wait()
            #if (rc != 0 and rc != 3) or err:
            if rc or err:
                raise Exception(f"backup failed: rc = {rc}")
            if summary is None:
                raise Exception("backup failed: no summary found in output")
            logging.info("backup successful")
            return summary

    def run_check_cmd(self, env, no_lock=False, segment:int=None):
        if segment is None:
            raise Exception("segment param is required for check")
        if segment < 1 or segment > common.FULL_CHECK_SEGMENTS:
            raise Exception(f"segment param must be between 1 and {common.FULL_CHECK_SEGMENTS}")
        cmd = ["restic",
               "check",
               "--quiet",
               "--read-data-subset", f"{segment}/{common.FULL_CHECK_SEGMENTS}"
            ]
        if no_lock:
            cmd.append("--no-lock")
        
        logging.info(f"running: {' '.join(cmd)}")
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        p = subprocess.Popen(cmd, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        
        rx = re.compile(("error for tree [0-9a-f]+:"
                        "|  tree [0-9a-f]+: node \".*\" with invalid type \"irregular\""
                        "|"
                        "|The repository is damaged and must be repaired.*"
                        "|Fatal: repository contains errors"), re.MULTILINE)

        err = False
        for l in stderr.splitlines():
            if rx.match(l) is None:
                logging.error(f"unexpected output: {l}")
                err = True

        rc = p.wait()
        if (rc != 0 and rc != 1) or err:
            if stderr is not None:
                logging.error(stderr.rstrip())
            raise Exception(f"check failed: rc = {rc}")
        logging.info("check successful")

    def forget_some(self, tag:str, env):
        if tag is None:
            raise Exception("tag param is required for pruning")
        cmd = ["restic",
                "forget",
                "--keep-hourly", "72",
                "--keep-daily", "72",
                "--keep-weekly", "72",
                "--keep-monthly", "72",
                "--keep-yearly", "72",
                "--keep-tag", "permanent",
                "--prune",
                "--compression", "max",
                "--tag", tag,
                ]
        logging.info(f"running: {' '.join(cmd)}")
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        p = subprocess.Popen(cmd, text=True, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        rc = p.wait()
        if rc != 0:
            logging.info(stdout)
            logging.info(stderr)
            raise Exception(f"cmd failed: rc = {rc}")
        logging.info("successful")

    def unlock(self, env, remove_all=False):
        cmd = ["restic", "unlock"]
        if remove_all:
            cmd.append("--remove-all")
            
        logging.info(f"running: {' '.join(cmd)}")
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        p = subprocess.Popen(cmd, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        
        if p.returncode != 0:
            raise Exception(f"unlock failed: {stderr}")
        logging.info("unlock successful")

    def ls(self, env, snapshot_id, no_lock=False):
        cmd = ["restic", "ls", "--json", snapshot_id]
        if no_lock:
            cmd.append("--no-lock")
        
        logging.info(f"running: {' '.join(cmd)}")
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        p = subprocess.Popen(cmd, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        
        if p.returncode != 0:
            raise Exception(f"ls failed: {stderr}")
            
        results = []
        for line in stdout.splitlines():
            try:
                if not line.startswith("{"): continue
                item = json.loads(line)
                if item.get("struct_type") == "node":
                    results.append(item)
            except:
                pass
        return results

    def restore(self, env, snapshot_id, target, include=None, no_lock=False):
        cmd = ["restic", "restore", snapshot_id, "--target", str(target), "--json", "--overwrite", "never"]
        if include:
            cmd.extend(["--include", include])
        if no_lock:
            cmd.append("--no-lock")
            
        logging.info(f"running: {' '.join(cmd)}")
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        p = subprocess.Popen(cmd, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        
        summary = None
        errmsgs = []
        err = False
        for l in stdout.splitlines() + stderr.splitlines():
            if l.startswith("{"):
                js = json.loads(l)
                if js['message_type'] == 'summary':
                    logging.info(l)
                    summary = l
                elif js['message_type'] == 'status':
                    pass
                elif js['message_type'] == 'exit_error':
                    pass
                elif js['message_type'] == 'error':
                    errmsgs.append(js['error']['message'])
                    if js['error']['message'].startswith("failed to restore timestamp of "):
                        logging.info(l)
                    else:
                        logging.error(l)
                        err = True
                else:
                    logging.error(f"unexpected output: {l}")
                    err = True

        rc = p.wait()
        if (rc != 0 and rc != 1) or err:
            if stderr is not None:
                logging.error(stderr.rstrip())
            raise Exception(f"restore failed: rc = {rc}")
        if summary is None:
            raise Exception("restore failed: no summary found in output")
        logging.info("restore successful")
        return summary, errmsgs

    def find(self, env, pattern, no_lock=False):
        cmd = ["restic", "find", pattern, "--json"]
        if no_lock:
            cmd.append("--no-lock")
            
        logging.info(f"running: {' '.join(cmd)}")
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        p = subprocess.Popen(cmd, text=True, encoding='utf-8', stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        
        if p.returncode != 0:
            raise Exception(f"find failed: {stderr}")
            
        results = []
        for line in stdout.splitlines():
            try:
                if not line.startswith("["): continue
                items = json.loads(line)
                for item in items:
                    if "snapshot" in item:
                        results.append(item)
            except:
                pass
        return results
