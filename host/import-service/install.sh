#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${NIWA_PROJECT_ROOT:-/home/niwa/niwa}"
SERVICE_ROOT="/opt/niwa-import"
ADMIN_WRAPPER="/usr/local/sbin/niwa-admin"

if [[ -x "${ADMIN_WRAPPER}" ]]; then
  exec sudo -n "${ADMIN_WRAPPER}" import-install
fi

sudo install -d -m 0755 "${SERVICE_ROOT}"
sudo install -d -m 0755 "${SERVICE_ROOT}/static"
sudo install -d -m 0755 /mnt/niwa-import
sudo install -d -m 0755 /mnt/niwa-storage/.niwa_import_staging
sudo install -m 0755 "${PROJECT_ROOT}/host/import-service/niwa_import.py" "${SERVICE_ROOT}/niwa_import.py"
sudo install -m 0644 "${PROJECT_ROOT}/host/import-service/static/niwa-logo.png" "${SERVICE_ROOT}/static/niwa-logo.png"
sudo install -m 0644 "${PROJECT_ROOT}/host/import-service/niwa-import.service" /etc/systemd/system/niwa-import.service
sudo systemctl daemon-reload
sudo systemctl enable niwa-import.service
sudo systemctl restart niwa-import.service
sudo systemctl --no-pager status niwa-import.service
