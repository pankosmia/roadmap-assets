# roadmap-assets
A place to upload images for roadmap issues

## Images

The roadmap dashboard uploads the images pasted in issues and comments here, as `YYYY/MM/<uuid>.<ext>`.
Do not edit or delete them by hand: issues link to them by URL.

### Orphan cleanup

The workflow `Clean up orphan images` runs every Sunday (and on demand from the Actions tab). It scans the
issues, pull requests and comments of every public, non-archived repository of the organization, and lists the
images that are linked from none of them and were added more than 30 days ago (`scripts/cleanup_orphans.py`).

- It is a **dry run by default**: the orphans are only listed in the run summary. To delete, run the workflow
  manually with **delete** ticked, or set the repository variable `DELETE_ORPHANS` to `true` so that the
  scheduled runs delete too.
- It deletes nothing, and fails, when a scan request fails, when the scan finds nothing, or when more than
  100 files would be deleted (`MAX_DELETE`).
- Limits: it does not see private repositories, discussions, wikis or README files. An image linked only from
  there looks like an orphan: do not use this repository for those. Deleted files stay in the git history, so the
  repository does not shrink; squashing the history is a separate, manual step.
