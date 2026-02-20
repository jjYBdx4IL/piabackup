# PiaBackup

## Why the name?

Because 'paranoia backup' was a bit too long.

## INSTALLATION

* MSIX: open properties dialog for MSIX file -> Signatures -> Details -> View -> Install -> Local Machine -> Trusted CA
* Auto-start on logon will fail after every update because the version is included in the installation path due to how MSIX is implemented. Just click that button in the settings dialog to update the task scheduler entry.

## Description

A forget/prune is treated as an extended backup if bitrot detection is enabled.
For bitrot detection to work also implicitly for the client side, we run the 'prune augmented'
backup with a full checksumming of all files, so we have a carbon copy of the client's files
including bit flips. Then we diff the subsequent snapshots against each other to find checksum changes
that aren't accompanied by metadata changes, which is a strong signal of bitrot. If we find such
cases, the forget/prune is not executed until the situation is resolved by the user.

Bitrot on the server/repository side is to be detected via full checks independently.

Another tweak is to backup each directory via its own tag (= its path). That prevents forget/prune
to affect deleted root backup directories, which is probably what one usually wants. Otherwise, if we
put everything into the same snapshot history, the deleted directories will eventually get lost
to forget/prunes. With our solution, the backups will simply pause for the deleted directories,
and they will automatically resume if the directories reappear again.

Vanished folders, for which we have done backups, are automatically tagged with 'permanent' (or
rather their latest backup snapshot is). The forget --prune command excludes snapshots that are tagged
with 'permanent'. If you run a prune manually, you WILL delete those snapshots because restic by default
doesn't care about tags when pruning unless you explicitly tell it so.

## Monitoring

* UI thread regularly checks for enabled backups with errors set.
* It also checks whether full repo check is overdue (last run older than 2*interval).
* If something is found, the user gets periodically nagged via toast messages.
* Prune and bitrot checks report errors as part of the backup. If there are issues,
  the backup keeps running upgraded to "full client data read, bitrot check, then prune"
  until everything finishes without error. That way the periodic prune/bitrot/full read checks
  produce a sticky/non-flaky error status for the backup.

## To-Do

* UI support to fix detected bit rot.
  * Manually skip snapshot for bit rot detection?
  * Bit rot specific file exclusions?
* Limit fast backup retries to a certain count.
* Max file size support.
* Better history browsing (similar to Windows File History?).
* Extended/individual tests to check whether we want to back up specific backup root dirs even if they
  exist? Simplest case: they are empty. We should treat them as not there and pause backups. For some
  directories we may want to identify them by extended mechanisms and maybe even in semi-random locations
  by their contents.

## Commands

* `sqlite3 sqlite.db ".schema" ; sqlite3 -line sqlite.db "select * from config; select * from status" ; sqlite3 -line sqlite.db "select * from backup_dirs limit 2; select * from update_checker;"`


--
git@nas:py.git@a1bd95b06a2fe46713bbaa77194172e37e2bbe18
