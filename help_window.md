# Configuration Help

## General Settings
- Start application on Windows logon: Automatically starts the backup agent in the background. However! It is better to use the Windows Task Scheduler to run PiaBackup with elevated privileges so restic can make use of Windows VSS snapshots for cleaner backups.
- Enable automatic backup path discovery: If enabled, the application will periodically (every 24 hours) scan for known important directories (like game saves, documents, etc.) and automatically add them to your backup list with 'auto' enabled status. You will be notified via a toast message when new paths are added. This is functionally the same as the Auto Detect button.
- Make vanished root folders' latest backups permanent: If a configured backup directory is missing (e.g. deleted or external drive disconnected), the last successful snapshot for that directory is automatically tagged as 'permanent'. This prevents the pruning process from deleting your last good backup of that data due to aging.
- Enable Prescan: If enabled, the application will quickly scan file modification times to decide whether the backup needs to run (avoids hogging the system due to unnecessary VSS snapshots).
- Wait for user idle before backing up: If enabled, backups will be delayed if you are actively using the computer. The program determines the inactivity timeout by looking up the system standby timeouts at startup and taking 70% of the smaller of both values. If it cannot determine that value, it falls back to 5 minutes. The maximum wait for user inactivity is half the backup period set for the backup directory.

## Restic Configuration
PiaBackup uses its own installations of restic and rclone so it runs against pre-defined versions of those tools and we can be sure of their exact behavior. Those tools are installed in '%USERPROFILE%\AppData\Local\py_apps\piabackup\dl'. When setting up rclone config, you might want to use the same version installed in that path (maybe add that path to your user Path env var).

- Repository: The location where backups are stored. Can be a local folder (ie. 'local:D:\ResticRepo1') or a remote location supported by rclone (ie. 'rclone:gdrive:.restic_repos/1' where 'gdrive' is a rclone config name that you need to configure and test outside of this app.).
- Full Check Frequency: How often to verify the integrity of all data in the repository. It does the following in the listed order:
  - Delete restic's local cache.
  - Forces restic to run a full check on the repository. Restic will download the complete repository via network in that step so it can take a long time to finish. This should work as a bitrot check on the repository data.
- Enable Prune: thin out snapshot history according to internal schedule.
- Enable Bitrot Detection: check subsequent snapshots for content changes without metadata changes.
Bitrot detection and prune run at the full check frequency. A full check on the per backup dir level includes in order of listing:
- Backup with full checksumming on client side while ignoring client side caches.
- Bitrot detection up to latest backup snapshot.
- Prune.
- Warning! I neither recommend pruning nor rewrites on consumer grade hardware because it introduces additional potential for bitrot due to rewrites of likely good backup data.

## Snapshot Management
- You can browse snapshots by right-clicking a backup directory and selecting 'Browse'.
- In the snapshot list, right-click a snapshot to toggle the 'permanent' tag. Snapshots tagged as 'permanent' are excluded from pruning (retention policy), meaning they will be kept indefinitely.
- However, be aware that the restic command line tool itself doesn't care about tags when pruning unless explicitly told to do so. Keep that in mind when manually managing your repo.

## Warnings
- PiaBackup can be configured to run restic with the --no-lock option. You probably shouldn't touch this unless you know exactly what you are doing and what this program's code is doing!!!

## Backup Directories
- Add folders you want to back up.
- You can set individual frequencies for each folder.
- Each folder uses its own path as a tag. That makes restic treat them as independent backups and deleting one of those folders completely won't make you automatically lose it eventually to the prune gods.

## Setting up a Local Repository
1. Create a folder on your external drive or secondary disk (e.g., D:\Backups).
2. In the Settings > Repository field, enter the path (e.g., local:D:\Backups).
3. Click 'Test Connection'.
4. If the repository is not initialized, you will be asked to initialize it. Click Yes.
5. You will be prompted to set a password. Remember this password! Without it, your backups are inaccessible.

## Setting up a Remote Repository (via rclone)
1. Ensure rclone is installed (the app attempts to download it if missing).
2. Open a command prompt/terminal and run: rclone config
3. Follow the interactive setup to configure your remote (e.g., Google Drive, S3, B2). Name it (e.g., 'gdrive').
4. In the Settings > Repository field, enter the rclone path: rclone:remote_name:bucket_name/path
   Example: rclone:gdrive:backups/piarepo
5. Click 'Test Connection' and follow initialization steps if necessary.
