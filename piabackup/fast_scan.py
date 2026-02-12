# encoding: utf-8
import hashlib
import os

class FastScan:
    @staticmethod
    def directory_fingerprint(path, limit=1000):
        items = []
        count = 0
        for root, dirs, files in os.walk(path):
            for name in files:
                count += 1
                if count > limit:
                    return None
                
                file_path = os.path.join(root, name)
                lmodtime = os.stat(file_path).st_mtime
                items.append(f"{lmodtime} {file_path}")
        
        return hashlib.sha256("\0".join(items).encode('utf-8')).hexdigest()
