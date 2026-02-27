# encoding: utf-8
import hashlib
import os

class FastScan:
    @staticmethod
    def directory_fingerprint(path):
        hasher = hashlib.sha256()
        stack = [path]
        
        while stack:
            current_dir = stack.pop()
            try:
                with os.scandir(current_dir) as it:
                    for entry in it:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            try:
                                st = entry.stat()
                                hasher.update(f"{st.st_mtime} {entry.path}\0".encode('utf-8'))
                            except OSError:
                                pass
            except OSError:
                continue
        
        return hasher.hexdigest()
