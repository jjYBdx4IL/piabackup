# encoding: utf-8
import hashlib
import logging
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from tkinter import messagebox


class ToolsInstaller:
    def __init__(self, bin_dl_dir: Path, app_name: str):
        self.bin_dl_dir = bin_dl_dir
        self.app_name = app_name

    def calculate_file_hash(self, filepath):
        hasher = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    def check_and_install_tools(self, tools):
        for name, info in tools.items():
            self._check_and_install_tools(name, info)

    def _check_and_install_tools(self, name, info):
        exe_path = self.bin_dl_dir / info["exe"]
        installed = False
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        if exe_path.exists():
            try:
                # Check version
                p = subprocess.run([str(exe_path), "version"], capture_output=True, text=True, startupinfo=startupinfo)
                if p.returncode == 0:
                    line1 = p.stdout.splitlines()[0].strip()
                    if line1 == info["ver"]:
                        logging.debug(f"{name} version verified: {line1}")
                        installed = True
                    else:
                        logging.warning(f"{name} version mismatch: expected '{info['ver']}', got '{line1}'")
            except Exception as e:
                logging.warning(f"Failed to check version for {name}: {e}")
        
        if not installed:
            if not messagebox.askyesno(self.app_name, f"{name} is missing or outdated.\nDo you want to download it now?\n\nURL: {info['url']}"):
                raise Exception(f"User cancelled download of {name}")

            logging.info(f"Downloading {name} from {info['url']}...")
            zip_fn = self.bin_dl_dir / f"{name}.zip"
            try:
                if os.path.exists(zip_fn):
                    os.remove(zip_fn)
                if os.path.exists(exe_path):
                    os.remove(exe_path)
                urllib.request.urlretrieve(info["url"], zip_fn)
                
                # Verify checksum
                downloaded_hash = self.calculate_file_hash(zip_fn)
                if downloaded_hash.lower() != info["sha256"].lower():
                    os.remove(zip_fn)
                    logging.error(f"SHA256 mismatch for {name}. Expected {info['sha256']}, got {downloaded_hash}")
                    raise ValueError(f"SHA256 mismatch for {name}. Downloaded file hash: {downloaded_hash}")
                logging.info(f"SHA256 verified for {name}")

                with zipfile.ZipFile(zip_fn, 'r') as zf:
                    with zf.open(info["zip_path"]) as src, open(exe_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                
                logging.info(f"Installed {name} to {exe_path}")
            except Exception as e:
                logging.error(f"Failed to install {name}: {e}")
                raise e
            finally:
                if zip_fn.exists():
                    os.remove(zip_fn)

            if not exe_path.exists():
                raise Exception(f"Failed to install {name}")
            
            # Check version
            p = subprocess.run([str(exe_path), "version"], capture_output=True, text=True, startupinfo=startupinfo)
            if p.returncode != 0:
                raise Exception(f"Failed to run {name} after installation: {p.stderr}")
            line1 = p.stdout.splitlines()[0].strip()
            if line1 == info["ver"]:
                logging.debug(f"{name} version verified: {line1}")
            else:
                raise Exception(f"{name} version mismatch: expected '{info['ver']}', got '{line1}'")

        # Check for license file independently
        if "license_url" in info and "license_filename" in info:
            lic_path = self.bin_dl_dir / info["license_filename"]
            if not lic_path.exists():
                try:
                    logging.info(f"Downloading license for {name}...")
                    urllib.request.urlretrieve(info["license_url"], lic_path)
                except Exception as e:
                    logging.warning(f"Failed to download license for {name}: {e}")
