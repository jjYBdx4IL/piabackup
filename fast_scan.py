# encoding: utf-8
import hashlib
import os

class FastScan:
    @staticmethod
    def directory_fingerprint(path, limit=1000):
        hasher = hashlib.sha256()
        count = 0
        for root, dirs, files in os.walk(path):
            for name in files + dirs:
                count += 1
                if count > limit:
                    return None
                
                file_path = os.path.join(root, name)
                lmodtime = os.stat(file_path).st_mtime
                
                hasher.update(f"{lmodtime} {file_path}\0".encode('utf-8'))
        
        return hasher.hexdigest()
