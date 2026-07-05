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

echo
echo "NIWA restricted admin wrapper installed."
echo "Checking passwordless access..."
sudo -n "${TARGET}" import-status
