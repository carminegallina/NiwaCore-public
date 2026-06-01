#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${NIWA_PROJECT_ROOT:-/home/niwa/niwa}"
SERVICE_ROOT="/opt/niwa-import"

sudo install -d -m 0755 "${SERVICE_ROOT}"
sudo install -d -m 0755 /mnt/niwa-import
sudo install -d -m 0755 /mnt/niwa-storage/.niwa_import_staging
sudo install -m 0755 "${PROJECT_ROOT}/host/import-service/niwa_import.py" "${SERVICE_ROOT}/niwa_import.py"
sudo install -m 0644 "${PROJECT_ROOT}/host/import-service/niwa-import.service" /etc/systemd/system/niwa-import.service
sudo systemctl daemon-reload
sudo systemctl enable --now niwa-import.service
sudo systemctl --no-pager status niwa-import.service
