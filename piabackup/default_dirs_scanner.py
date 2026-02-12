# encoding: utf-8
import logging
import os
import platform


class DefaultDirsScanner:
    def __init__(self):
        prevent_match_str = " 798fsd9fhj3lknfldf98u3"
        if platform.system() == "Windows":
            localappdata = os.environ.get('LOCALAPPDATA', prevent_match_str)
            roaming = os.environ.get('APPDATA', prevent_match_str)
            home = os.environ.get('USERPROFILE', prevent_match_str)
            programdata = os.environ.get('ALLUSERSPROFILE', prevent_match_str)
            programfiles_x86 = os.environ.get('ProgramFiles(x86)', prevent_match_str)
            programfiles = os.environ.get('ProgramFiles', prevent_match_str)
            locallow = self._get_locallow(home)
            self.dirs = fr'''
C:\Jts
{programfiles_x86}\Steam\userdata
{programdata}\Arturia\Presets
{home}\.gnupg
{home}\.ssh
{home}\AndroidStudioProjects
 -/*/build/
 -/*/app/build/
{home}\Documents
{home}\Saved Games
{localappdata}\dlcache
{localappdata}\FalloutShelter
{localappdata}\Hinterland
{localappdata}\kenshi
{localappdata}\py_apps\piabackup
 -/dl/
{localappdata}\User Data
{locallow}\Assemble Entertainment
{locallow}\Cyan Worlds
{locallow}\Daggerfall Workshop
{locallow}\Obsidian Entertainment
{roaming}\7DaysToDie
{roaming}\Bay 12 Games\Dwarf Fortress
{roaming}\Code\User
{roaming}\D16 Group
{roaming}\endless-sky
{roaming}\IO Interactive
{roaming}\rclone
{roaming}\ResidualVM
{roaming}\ScummVM
{roaming}\Steinberg
{roaming}\Surge XT
'''.splitlines()
        else:
            raise Exception("DefaultDirsScanner is only implemented for Windows at this time")

    def _get_locallow(self, home):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                path, _ = winreg.QueryValueEx(key, "{A520A1A4-1780-4FF6-BD18-167343C5AF16}")
                return os.path.expandvars(path)
        except Exception as e:
            logging.debug(f"Failed to get LocalLow from registry: {e}")
            return os.path.join(home, 'AppData', 'LocalLow')

    def scan(self) -> list:
        found = []
        i = 0
        while i < len(self.dirs):
            d = self.dirs[i].strip()
            i += 1

            if not d or d.startswith('-'):
                continue

            if os.path.isdir(d):
                exclusions = []
                # Peek ahead for exclusions. The next lines belong to this `d`.
                peek_i = i
                while peek_i < len(self.dirs):
                    peek_line = self.dirs[peek_i].strip()
                    if peek_line.startswith('-'):
                        exclusions.append(peek_line[1:].strip())
                        peek_i += 1
                    else:
                        break
                
                found.append({'path': d, 'exclusions': exclusions})
                i = peek_i # Jump `i` to after the exclusions
        return found
