#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${NIWA_PROJECT_ROOT:-/home/niwa/niwa}"
SOURCE="${PROJECT_ROOT}/host/admin/niwa-admin"
TARGET="/usr/local/sbin/niwa-admin"
SUDOERS_TARGET="/etc/sudoers.d/niwa-admin"
TEMP_SUDOERS="$(mktemp)"

cleanup() {
  rm -f "${TEMP_SUDOERS}"
}
trap cleanup EXIT

if [[ ! -f "${SOURCE}" ]]; then
  echo "Missing source wrapper: ${SOURCE}" >&2
  exit 1
fi

cat > "${TEMP_SUDOERS}" <<'EOF'
# NiwaCore restricted administration wrapper.
# The root-owned wrapper validates every accepted action and service name.
niwa ALL=(root) NOPASSWD: /usr/local/sbin/niwa-admin
EOF

sudo /usr/sbin/visudo -cf "${TEMP_SUDOERS}"
sudo install -o root -g root -m 0755 "${SOURCE}" "${TARGET}"
sudo install -o root -g root -m 0440 "${TEMP_SUDOERS}" "${SUDOERS_TARGET}"
sudo /usr/sbin/visudo -cf "${SUDOERS_TARGET}"

# NIWA System asks for hotspot channel changes through this folder.
sudo install -d -m 0755 "${PROJECT_ROOT}/data/hotspot"
# Drop a request left by the panel before the watcher existed: no surprise switch.
sudo rm -rf -- "${PROJECT_ROOT}/data/hotspot/request"
sudo install -o root -g root -m 0644 "${PROJECT_ROOT}/host/admin/niwa-hotspot.path" /etc/systemd/system/niwa-hotspot.path
sudo install -o root -g root -m 0644 "${PROJECT_ROOT}/host/admin/niwa-hotspot.service" /etc/systemd/system/niwa-hotspot.service
sudo systemctl daemon-reload
sudo systemctl enable --now niwa-hotspot.path
sudo systemctl start niwa-hotspot.service

echo
echo "NIWA restricted admin wrapper installed."
echo "Checking passwordless access..."
sudo -n "${TARGET}" import-status
