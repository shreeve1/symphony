#!/usr/bin/env bash
# validate-syntax — parse-check the edited file. Fail-closed (exit 2) on syntax errors.
# Covers the languages present in this repo: Python, JSON, shell.
set -u
path=$(jq -r '.tool_input.file_path // empty')
[ -z "$path" ] && exit 0
[ -f "$path" ] || exit 0

case "$path" in
  *.json)
    if ! jq . "$path" >/dev/null 2>&1; then
      echo "Invalid JSON in $path — fix before continuing." >&2
      exit 2
    fi ;;
  *.py)
    if command -v python3 >/dev/null 2>&1; then
      if ! python3 -m py_compile "$path" 2>/dev/null; then
        echo "Python syntax error in $path." >&2
        exit 2
      fi
    elif command -v python >/dev/null 2>&1; then
      if ! python -m py_compile "$path" 2>/dev/null; then
        echo "Python syntax error in $path." >&2
        exit 2
      fi
    fi ;;
  *.sh|*.bash)
    if ! bash -n "$path" 2>/dev/null; then
      echo "Bash syntax error in $path." >&2
      exit 2
    fi ;;
esac
exit 0
