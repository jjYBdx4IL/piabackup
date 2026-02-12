# encoding: utf-8
import datetime
import json
from pathlib import Path
import re
import subprocess
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

    def list_snapshots(self, cfg:Config, env, tag) -> list:
        if tag is None:
            raise Exception("tag param is required for listing snapshots")
        cmd = ["restic",
                "snapshots",
                "--json",
                "--tag", tag,
                ]
        if cfg.no_lock:
            cmd.append("--no-lock")
        common.log.info(f"running: {' '.join(cmd)}")
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        p = subprocess.Popen(cmd, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        rc = p.wait()
        if rc != 0:
            raise Exception(f"cmd failed: rc = {rc}, stderr = {stderr}")
        if common.IS_DEBUGGER_PRESENT:
            common.log.debug(stdout)
        js = json.loads(stdout.splitlines()[0])
        if common.IS_DEBUGGER_PRESENT:
            common.log.debug(json.dumps(js, indent=4))
        common.log.info("successful")
        for s in js:
            s['_time'] = datetime.datetime.fromisoformat(s['time']).timestamp()
        #js.sort(key=lambda x: x['_time'])
        for i in range(0,len(js)-1):
            if js[i]['_time'] > js[i+1]['_time']:
                raise Exception(f"snapshot times are not in ascending order")
        return js

    def get_all_paths(self, env, no_lock=False) -> set[Path]:
        cmd = ["restic",
                "snapshots",
                "--json",
                ]
        if no_lock:
            cmd.append("--no-lock")
        common.log.info(f"running: {' '.join(cmd)}")
        
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

            common.log.info(f"running: {' '.join(cmd)} ({curr['time']})")
            
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
                        common.log.debug(l)
                    # {"message_type":"change","path":"/C/Jts/knkeabmblimgifcdgaicnbbhgdgecimiohobcbll/Tue.trd","modifier":"M"}
                    elif js['message_type'] == 'change':
                        if '?' in js['modifier']:
                            common.log.error(f"bit rot detected: {l}")
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

        common.log.info("successful")
        return last_checked_snap

    def run_backup_cmd(self, backup_path:Path, env, docheck=False, no_lock=False):
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
        cmd.extend(("--tag", backup_path.as_posix(), str(backup_path)))
        common.log.info(f"running: {' '.join(cmd)}")
        
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
                    common.log.info(l)
                    summary = l
                elif js['message_type'] == 'exit_error':
                    common.log.warning(l)
                elif js['message_type'] == 'error':
                    if js['error']['message'].startswith("incomplete metadata for "):
                        common.log.warning(l)
                    elif js['error']['message'].endswith(": unsupported file type \"irregular\""):
                        common.log.warning(l)
                    elif js['error']['message'].startswith("failed to create snapshot for "):
                        common.log.warning(l)
                    else:
                        common.log.error(l)
                        err = True
                else:
                    common.log.error(f"unexpected output: {l}")
                    err = True

        rc = p.wait()
        if (rc != 0 and rc != 3) or err:
            raise Exception(f"backup failed: rc = {rc}")
        if summary is None:
            raise Exception("backup failed: no summary found in output")
        common.log.info("backup successful")
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
        
        common.log.info(f"running: {' '.join(cmd)}")
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
                common.log.error(f"unexpected output: {l}")
                err = True

        rc = p.wait()
        if (rc != 0 and rc != 1) or err:
            if stderr is not None:
                common.log.error(stderr.rstrip())
            raise Exception(f"check failed: rc = {rc}")
        common.log.info("check successful")

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
                "--prune",
                "--compression", "max",
                "--tag", tag,
                ]
        common.log.info(f"running: {' '.join(cmd)}")
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        p = subprocess.Popen(cmd, text=True, env=env, startupinfo=startupinfo)
        stdout, stderr = p.communicate()
        rc = p.wait()
        if rc != 0:
            common.log.info(stdout)
            common.log.info(stderr)
            raise Exception(f"cmd failed: rc = {rc}")
        common.log.info("successful")

    def ls(self, env, snapshot_id, no_lock=False):
        cmd = ["restic", "ls", "--json", snapshot_id]
        if no_lock:
            cmd.append("--no-lock")
        
        common.log.info(f"running: {' '.join(cmd)}")
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
            
        common.log.info(f"running: {' '.join(cmd)}")
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
                    common.log.info(l)
                    summary = l
                elif js['message_type'] == 'status':
                    pass
                elif js['message_type'] == 'exit_error':
                    pass
                elif js['message_type'] == 'error':
                    errmsgs.append(js['error']['message'])
                    if js['error']['message'].startswith("failed to restore timestamp of "):
                        common.log.info(l)
                    else:
                        common.log.error(l)
                        err = True
                else:
                    common.log.error(f"unexpected output: {l}")
                    err = True

        rc = p.wait()
        if (rc != 0 and rc != 1) or err:
            if stderr is not None:
                common.log.error(stderr.rstrip())
            raise Exception(f"restore failed: rc = {rc}")
        if summary is None:
            raise Exception("restore failed: no summary found in output")
        common.log.info("restore successful")
        return summary, errmsgs

    def find(self, env, pattern, no_lock=False):
        cmd = ["restic", "find", pattern, "--json"]
        if no_lock:
            cmd.append("--no-lock")
            
        common.log.info(f"running: {' '.join(cmd)}")
        
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
