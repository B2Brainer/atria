#!/usr/bin/env bash
# Provisions the standalone Python runtime + locked backend dependencies that
# electron-builder bundles as `extraResources` (Increment 6, resolved
# packaging decision): a `uv`-managed CPython distribution, with the
# project's locked dependency set installed directly into it (no PyInstaller
# or other freezing tool) — plus a copy of the backend source
# (`core`/`adapters`/`api`), so the packaged application never requires
# Python, `uv`, or Node.js development tooling on the target machine.
#
# Verified (manually, this increment): the resulting runtime and its
# compiled extension modules (including the macOS-Keychain-binding
# `pyobjc-framework-security`) tolerate being moved to an arbitrary absolute
# path after installation — required here, since `uv python install`'s
# `--install-dir` bakes in whatever path is given at install time, and this
# script's output is later copied again by electron-builder into the .app
# bundle's `Contents/Resources`.
set -euo pipefail

# `pwd -P` (not plain `pwd`): resolves any symlink component in this
# script's own invocation path, so REPO_ROOT (and every destructive `rm -rf`
# target derived from it below) is always this script's real location on
# disk, never a logical, not-yet-resolved path through a symlinked
# directory or a symlinked invocation of this script itself.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
RESOURCES_DIR="$REPO_ROOT/desktop/resources"
PYTHON_DIST_DIR="$RESOURCES_DIR/python-dist"
BACKEND_DIR="$RESOURCES_DIR/backend"
PYTHON_VERSION="3.13"

mkdir -p "$RESOURCES_DIR"
# Defensive, cheap to check: if some prior state ever left python-dist/ or
# backend/ as a symlink (never created as one by this script), resolve-then-
# rm-rf below would follow it and delete whatever it points at, not a
# directory under this repo.
for path in "$PYTHON_DIST_DIR" "$BACKEND_DIR"; do
  if [ -L "$path" ]; then
    echo "error: $path is a symlink, refusing to remove it" >&2
    exit 1
  fi
done
rm -rf "$PYTHON_DIST_DIR" "$BACKEND_DIR"

echo "==> Installing standalone CPython $PYTHON_VERSION into $PYTHON_DIST_DIR"
uv python install "$PYTHON_VERSION" --install-dir "$PYTHON_DIST_DIR"

# `--install-dir` produces a version-and-platform-qualified directory (e.g.
# cpython-3.13.14-macos-x86_64-none/) plus an unqualified symlink
# (cpython-3.13-macos-x86_64-none) that points at it via an ABSOLUTE path —
# not relocatable. Resolve the symlink once, here, and keep only the real
# directory's contents directly under python-dist/, so nothing under this
# directory depends on an absolute path baked in at this build step.
# `-print -quit` (not `| head -n1`): under `pipefail`, `head` closing the
# pipe after its first line sends `find` a SIGPIPE, which `pipefail` would
# report as this command's (non-zero) exit status even though `head` itself
# succeeded -- `-quit` makes `find` itself stop after the first match, with
# no pipe for it to be killed by.
RUNTIME_DIR="$(find "$PYTHON_DIST_DIR" -maxdepth 1 -type d -name 'cpython-*' -print -quit)"
if [ -z "$RUNTIME_DIR" ]; then
  echo "error: could not locate the installed CPython runtime directory" >&2
  exit 1
fi
TMP_RUNTIME="$RESOURCES_DIR/.python-dist-runtime-tmp"
rm -rf "$TMP_RUNTIME"
mv "$RUNTIME_DIR" "$TMP_RUNTIME"
rm -rf "$PYTHON_DIST_DIR"
mv "$TMP_RUNTIME" "$PYTHON_DIST_DIR"

PYTHON_EXE="$PYTHON_DIST_DIR/bin/python3"
if [ ! -x "$PYTHON_EXE" ]; then
  echo "error: expected a python3 executable at $PYTHON_EXE" >&2
  exit 1
fi

echo "==> Installing locked backend dependencies into the standalone runtime"
REQUIREMENTS_FILE="$(mktemp)"
trap 'rm -f "$REQUIREMENTS_FILE"' EXIT
(cd "$REPO_ROOT" && uv export --locked --no-dev --no-emit-project --format requirements-txt -o "$REQUIREMENTS_FILE")
uv pip install --python "$PYTHON_EXE" -r "$REQUIREMENTS_FILE" --no-deps --break-system-packages

echo "==> Copying backend source (core/, adapters/, api/)"
mkdir -p "$BACKEND_DIR"
for pkg in core adapters api; do
  cp -R "$REPO_ROOT/$pkg" "$BACKEND_DIR/$pkg"
  find "$BACKEND_DIR/$pkg" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
done

echo "==> Verifying the bundled runtime imports the bundled backend source"
# BACKEND_DIR reaches the interpreter via its environment, not by string-
# interpolating a shell variable into inline Python source (which would
# break, or worse, inject code, were this path ever to contain a quote or
# backslash).
ATRIA_BACKEND_DIR="$BACKEND_DIR" "$PYTHON_EXE" -c "
import os
import sys
sys.path.insert(0, os.environ['ATRIA_BACKEND_DIR'])
from adapters.credentials.adapter import CredentialAdapter
from adapters.persistence.adapter import PersistenceAdapter
from api.composition import Composition
print('build-python-dist.sh: bundled runtime + backend import OK')
"

echo "==> Done: $PYTHON_DIST_DIR and $BACKEND_DIR are ready for electron-builder extraResources"
