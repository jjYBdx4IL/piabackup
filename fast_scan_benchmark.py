# encoding: utf-8
import os
import sys
import time

# Ensure we can import from the package even if running this script directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from piabackup.fast_scan import FastScan

class Benchmark:
    @staticmethod
    def count_items(path):
        file_count = 0
        dir_count = 0
        stack = [path]
        while stack:
            current_dir = stack.pop()
            try:
                with os.scandir(current_dir) as it:
                    for entry in it:
                        if entry.is_dir(follow_symlinks=False):
                            dir_count += 1
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            file_count += 1
            except OSError:
                continue
        return dir_count, file_count

    @staticmethod
    def run(path):
        print(f"Benchmarking FastScan on: {path}")
        if not os.path.exists(path):
            print("Error: Path does not exist.")
            return

        print("Counting files and directories...")
        dir_count, file_count = Benchmark.count_items(path)
        total_items = dir_count + file_count
        print(f"Found {dir_count} directories and {file_count} files (Total: {total_items})")

        print("Running benchmark for at least 10 seconds...")
        print("-" * 40)

        iterations = 0
        start_time = time.time()
        
        while True:
            FastScan.directory_fingerprint(path)
            iterations += 1
            if time.time() - start_time >= 10.0:
                break

        total_time = time.time() - start_time
        
        print("-" * 40)
        print(f"Total time: {total_time:.4f}s")
        print(f"Iterations: {iterations}")
        print(f"Avg time per run: {total_time / iterations:.4f}s")
        
        if total_time > 0:
            items_per_sec = (total_items * iterations) / total_time
            print(f"Traversed items per second: {items_per_sec:.2f}")

if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    Benchmark.run(target_dir)