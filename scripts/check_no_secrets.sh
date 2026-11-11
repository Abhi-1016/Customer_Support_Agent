#!/usr/bin/env bash
set -euo pipefail

echo "Running security check: Grepping for vendor key patterns (vach_, AQ.)..."

# Grep for keys excluding backend/.env, .git, node_modules, and .venv
if grep -rnEI --exclude-dir={.git,node_modules,.venv,venv} --exclude="backend/.env" "vach_\|AQ\." . ; then
    echo "ERROR: Exposed vendor API key found outside backend/.env!"
    exit 1
else
    echo "SUCCESS: No vendor API keys exposed outside backend/.env."
    exit 0
fi

