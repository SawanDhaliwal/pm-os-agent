#!/usr/bin/env bash
# Copy the PM team into your personal Claude Code folder (~/.claude) so it works in every repo.
# Safe to re-run after you edit a file here: changed files are backed up as .bak before being replaced.
# Usage: ./install.sh            install
#        ./install.sh --dry-run  show what would change
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
dest="${CLAUDE_HOME:-$HOME/.claude}"
dry=0
[[ "${1:-}" == "--dry-run" ]] && dry=1

install_file() {  # $1 = source file, $2 = destination file
  if [[ -f "$2" ]] && cmp -s "$1" "$2"; then
    echo "  unchanged  ${2#"$dest"/}"
    return
  fi
  local action="added    "
  [[ -f "$2" ]] && action="updated  "
  echo "  $action ${2#"$dest"/}"
  if (( dry == 0 )); then
    mkdir -p "$(dirname "$2")"
    [[ -f "$2" ]] && cp "$2" "$2.bak"
    cp "$1" "$2"
  fi
}

echo "Installing the PM team into $dest"
for f in "$here"/agents/*.md; do
  install_file "$f" "$dest/agents/$(basename "$f")"
done
for d in "$here"/skills/*/; do
  name="$(basename "$d")"
  install_file "$d/SKILL.md" "$dest/skills/$name/SKILL.md"
done
(( dry == 1 )) && echo "Dry run: nothing was changed."
echo "Done. Start a new Claude Code session, then type /agents to see the team."
