# rs-demo branch `local-mode-monitoring-for-testing`

This branch only exists to save the monitoring (=grafana, loki, tempo) configuration for local mode, which has been removed from the `develop` branch.

To add this configuration to your current branch, run the following:

```bash
# Your current branch to which you want to merge local-mode-monitoring-for-testing
YOUR_BRANCH=...

# Update local-mode-monitoring-for-testing
git fetch
git checkout local-mode-monitoring-for-testing
git merge origin/develop

# Go back to your branch
git checkout $YOUR_BRANCH

# Commit all your local changes
git commit ...
git push

# Copy monitoring configuration
git difftool -d local-mode-monitoring-for-testing

# The meld difftool doesn't work to copy full files, so just grab them by hand
(cd local-mode/config && git checkout local-mode-monitoring-for-testing -- grafana-datasources.yml grafana.ini tempo.yaml)

# Commit your changes if necessary
git add . && git commit -m "merge local-mode-monitoring-for-testing"

# Before merging your branch to develop, cancel your changes.
# Get the commit hash then revert it with: 'git revert -m 1 <hash>'
git log --all --grep="merge local-mode-monitoring-for-testing"
```
