import os
import platform
import piabackup.common as common

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
{home}\Documents
{home}\Saved Games
{localappdata}\dlcache
{localappdata}\FalloutShelter
{localappdata}\Hinterland
{localappdata}\kenshi
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
            common.log.debug(f"Failed to get LocalLow from registry: {e}")
            return os.path.join(home, 'AppData', 'LocalLow')

    def scan(self) -> list[str]:
        found = []
        for d in self.dirs:
            d = d.strip()
            if os.path.isdir(d):
                found.append(d)
        return found
