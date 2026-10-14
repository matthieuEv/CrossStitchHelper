#!/usr/bin/env bash
# Assembles an integration branch: main plus every open, non-draft pull request
# targeting main, merged in pull request number order. This is what testers get
# as a pre-release image (`.github/workflows/integration.yml`); the pull
# requests themselves stay open and are merged into main one by one, as usual.
#
# Conflicts between pull requests are resolved once by hand, recorded by
# `git rerere` and replayed on every rebuild. Recorded resolutions are shared
# through the `rerere-cache` branch.
#
# Locally (run it from a clean checkout; it switches to the integration branch):
#   .github/scripts/assemble-integration.sh [--exclude 66,70]
#   It stops on a conflict no recorded resolution covers. Edit the conflicting
#   files to resolve it (no `git add` needed), then run the same command again:
#   the resolution is recorded and everything is reassembled. Once the whole set
#   merges, new resolutions are pushed to `rerere-cache`.
#
# In CI:
#   .github/scripts/assemble-integration.sh --ci --branch integration/v2.0.0 [--exclude 66,70]
#   An unresolved conflict fails the run; nothing is ever pushed by the script.
set -euo pipefail

branch=integration/local
exclude=""
ci=false
while (($#)); do
  case "$1" in
    --branch) branch=$2; shift 2 ;;
    --exclude) exclude=$2; shift 2 ;;
    --ci) ci=true; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

cache_branch=rerere-cache
rr_cache="$(git rev-parse --git-common-dir)/rr-cache"
git_rr() { git -c rerere.enabled=true -c rerere.autoUpdate=true "$@"; }

# Resuming after a conflict was resolved by hand: record it, then start over.
if git rev-parse -q --verify MERGE_HEAD >/dev/null; then
  git_rr rerere
  git merge --abort
fi

if ! git diff --quiet HEAD; then
  echo "The working tree has uncommitted changes: commit or stash them first." >&2
  exit 1
fi

# Load the shared resolutions.
mkdir -p "$rr_cache"
cache_commit=""
if git fetch -q origin "$cache_branch" 2>/dev/null; then
  cache_commit=$(git rev-parse FETCH_HEAD)
  git archive "$cache_commit" | tar -xmf - -C "$rr_cache"
fi

# Builds a tree of the recorded resolutions (pre/post images only) and prints it.
cache_tree() {
  local dir file entry
  for dir in "$rr_cache"/*/; do
    # Unresolved conflicts have no postimage: nothing to share.
    compgen -G "${dir}postimage*" >/dev/null || continue
    entry=$(for file in "$dir"preimage* "$dir"postimage*; do
      printf '100644 blob %s\t%s\n' "$(git hash-object -w "$file")" "$(basename "$file")"
    done | git mktree)
    printf '040000 tree %s\t%s\n' "$entry" "$(basename "$dir")"
  done | git mktree
}

git fetch -q origin main
git checkout -q -B "$branch" origin/main

excluded=" $(tr -cs '0-9' ' ' <<<"$exclude") "
prs=$(gh pr list --base main --state open --limit 200 --json number,title,isDraft \
  --jq '[.[] | select(.isDraft | not)] | sort_by(.number) | .[] | "\(.number)\t\(.title)"')

included=()
skipped=()
while IFS=$'\t' read -r number title; do
  [[ -n $number ]] || continue
  if [[ $excluded == *" $number "* ]]; then
    skipped+=("$number"$'\t'"$title")
    continue
  fi
  git fetch -q origin "pull/$number/head"
  sha=$(git rev-parse FETCH_HEAD)
  if ! git_rr merge -q --no-ff -m "Merge #$number: $title" FETCH_HEAD >/dev/null; then
    unresolved=$(git diff --name-only --diff-filter=U)
    if [[ -n $unresolved ]]; then
      echo >&2
      echo "#$number ($title) conflicts with the pull requests merged before it, in:" >&2
      sed 's/^/  /' <<<"$unresolved" >&2
      if $ci; then
        git merge --abort
        echo "::error::#$number conflicts with no recorded resolution. Run .github/scripts/assemble-integration.sh locally to resolve it, or exclude #$number."
      else
        echo "Resolve these files, then run $0 again." >&2
      fi
      exit 1
    fi
    # Every conflict was replayed from a recorded resolution.
    git commit -q --no-edit
  fi
  included+=("$number"$'\t'"$sha"$'\t'"$title")
done <<<"$prs"

report() {
  echo "Base: \`main\` at \`$(git rev-parse --short origin/main)\`"
  echo
  echo "| PR | Commit | Title |"
  echo "|---|---|---|"
  local entry number sha title
  for entry in ${included[@]+"${included[@]}"}; do
    IFS=$'\t' read -r number sha title <<<"$entry"
    echo "| #$number | \`${sha:0:7}\` | $title |"
  done
  if ((${#skipped[@]})); then
    echo
    echo "Excluded:"
    for entry in "${skipped[@]}"; do
      IFS=$'\t' read -r number title <<<"$entry"
      echo "- #$number $title"
    done
  fi
}
report
if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  { echo "## Integration branch \`$branch\`"; echo; report; } >>"$GITHUB_STEP_SUMMARY"
fi

# Share the resolutions recorded on this run.
if ! $ci; then
  tree=$(cache_tree)
  if [[ -z $cache_commit || $tree != "$(git rev-parse "$cache_commit^{tree}")" ]]; then
    commit=$(git commit-tree "$tree" ${cache_commit:+-p "$cache_commit"} -m "Update recorded conflict resolutions")
    git push -q origin "$commit:refs/heads/$cache_branch"
    echo "Pushed the new conflict resolutions to $cache_branch."
  fi
  echo "Assembled on $branch (not pushed: integration.yml rebuilds it)."
fi
