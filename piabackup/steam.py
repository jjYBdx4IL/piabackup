import logging
import os
import platform
import winreg

import vdf


class SteamScanner:
    def get_steam_base_path(self):
        """Detects the main Steam installation path based on the OS."""
        system = platform.system()
        
        if system == "Windows":
            try:
                # Registry lookup is the most reliable method on Windows
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
                path, _ = winreg.QueryValueEx(key, "SteamPath")
                return path
            except FileNotFoundError:
                # Fallback for default installation
                return r"C:\Program Files (x86)\Steam"
                
        elif system == "Linux":
            # Common Linux paths (native and flatpak)
            paths = [
                os.path.expanduser("~/.local/share/Steam"),
                os.path.expanduser("~/.steam/steam"),
                os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam")
            ]
            for p in paths:
                if os.path.exists(p):
                    return p
                    
        elif system == "Darwin": # macOS
            path = os.path.expanduser("~/Library/Application Support/Steam")
            if os.path.exists(path):
                return path
                
        return None

    def get_steam_libraries(self, base_path):
        """Parses libraryfolders.vdf to find all installation directories."""
        vdf_path = os.path.join(base_path, "steamapps", "libraryfolders.vdf")
        
        if not os.path.exists(vdf_path):
            print(f"Error: libraryfolders.vdf not found at {vdf_path}")
            return []

        libraries = []
        
        try:
            with open(vdf_path, 'r', encoding='utf-8') as f:
                data = vdf.load(f)
                
            # The structure is usually {"libraryfolders": {"0": {...}, "1": {...}}}
            folders = data.get("libraryfolders", {})
            
            for key, value in folders.items():
                if isinstance(value, dict) and "path" in value:
                    libraries.append(value["path"])
                    
        except Exception as e:
            print(f"Error parsing VDF: {e}")
            
        return libraries

    def scan_games_in_library(self, library_path):
        """Scans a library folder for installed games (appmanifest_*.acf)."""
        steamapps_path = os.path.join(library_path, "steamapps")
        games = []
        
        if not os.path.exists(steamapps_path):
            return games

        for filename in os.listdir(steamapps_path):
            if filename.startswith("appmanifest_") and filename.endswith(".acf"):
                try:
                    filepath = os.path.join(steamapps_path, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        manifest = vdf.load(f)
                        
                    # Extract game name and install directory
                    app_state = manifest.get("AppState", {})
                    game_name = app_state.get("name", "Unknown")
                    install_dir = app_state.get("installdir", "Unknown")
                    
                    full_install_path = os.path.join(steamapps_path, "common", install_dir)
                    games.append({"name": game_name, "path": full_install_path})
                    
                except Exception:
                    continue
                    
        return games

    def scan_all(self):
        base_steam = self.get_steam_base_path()
        found = {}
        if base_steam:
            logging.debug(f"Main Steam Path: {base_steam}")
            logging.debug("-" * 40)
            
            libs = self.get_steam_libraries(base_steam)
            
            for lib in libs:
                logging.debug(f"Scanning Library: {lib}")
                games = self.scan_games_in_library(lib)
                
                if not games:
                    logging.debug("  No games found or empty library.")
                
                for game in games:
                    logging.debug(f"  Found: {game['name']}")
                    logging.debug(f"    -> {game['path']}")
                    found[game['name']] = game['path']
        else:
            logging.debug("Could not locate Steam installation.")
        return found

