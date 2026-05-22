#!/usr/bin/env bash
# Wiki frontmatter validator — guards the compile-graph contract.
#
# A wiki article that uses inline `[[wikilinks]]` MUST also declare them in
# the YAML frontmatter `related:` array. Graphify's free `build_from_vault`
# path reads `related:` to wire graph edges; inline-only wikilinks are
# invisible to the graph.
#
# Root cause: 2026-05-22 compile-graph disconnect — 15 wiki articles shipped
# with inline wikilinks but no `related:` arrays, leaving graph.json blind
# to the synthesized layer until the post-mortem rebuild pass.
#
# Wire into pre-commit (.git/hooks/pre-commit) OR call from a Claude Code
# PostToolUse hook on Write events under */wiki/*.md.

set -euo pipefail

WIKI_FILES=()
if [[ $# -gt 0 ]]; then
  # Arguments are filenames — validate each.
  WIKI_FILES=("$@")
else
  # No args — read staged changes (pre-commit mode).
  while IFS= read -r f; do
    [[ -n "$f" ]] && WIKI_FILES+=("$f")
  done < <(git diff --cached --name-only --diff-filter=ACM | grep -E '(^|/)wiki/[^/]+\.md$' || true)
fi

if [[ ${#WIKI_FILES[@]} -eq 0 ]]; then
  exit 0
fi

violations=()
for f in "${WIKI_FILES[@]}"; do
  [[ -f "$f" ]] || continue
  case "$f" in
    */wiki/*.md) ;;
    *) continue ;;
  esac

  # Extract body (everything after the second `---`).
  body=$(awk '/^---$/{n++; next} n>=2{print}' "$f")
  # Extract frontmatter (between first and second `---`).
  fm=$(awk '/^---$/{n++; if(n==2) exit; next} n==1{print}' "$f")

  # Skip files with no frontmatter at all.
  [[ -z "$fm" ]] && continue

  # Find inline wikilinks in body (excluding anchor-only `[[#foo]]`).
  inline=$(echo "$body" | grep -oE '\[\[[^#\]|][^]|]*\]\]' | sort -u || true)

  if [[ -z "$inline" ]]; then
    continue  # no wikilinks → no requirement
  fi

  if ! echo "$fm" | grep -qE '^related:'; then
    violations+=("$f: has [[wikilinks]] but no 'related:' frontmatter array")
  fi
done

if [[ ${#violations[@]} -gt 0 ]]; then
  cat >&2 <<EOF
[wiki-frontmatter-related] BLOCKED — ${#violations[@]} wiki file(s) violate compile-graph contract:

$(printf '  - %s\n' "${violations[@]}")

Fix: add inline [[wikilinks]] to the frontmatter \`related:\` array, e.g.
  ---
  ...
  related:
    - "[[glossary]]"
    - "[[scope]]"
  ---

Background: Graphify's build_from_vault reads frontmatter \`related:\` to
wire graph edges. Inline wikilinks alone are invisible to the graph.
Root cause: 2026-05-22 compile-graph disconnect post-mortem.
EOF
  exit 1
fi

exit 0
