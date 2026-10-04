# NIWA restricted administration

`niwa-admin` provides a small root-owned wrapper for the administrative actions
that NIWA needs during normal maintenance. It avoids granting unrestricted
passwordless root access to the SSH account.

Install once from the Raspberry:

```bash
cd ~/niwa
chmod +x host/admin/install.sh host/admin/niwa-admin
host/admin/install.sh
```

The installer asks for the Raspberry password during the one-time setup. After
installation, the allowed actions work without a password:

```bash
sudo -n /usr/local/sbin/niwa-admin import-status
sudo -n /usr/local/sbin/niwa-admin import-install
sudo -n /usr/local/sbin/niwa-admin import-restart
sudo -n /usr/local/sbin/niwa-admin hotspot-up
sudo -n /usr/local/sbin/niwa-admin hotspot-channel 6
sudo -n /usr/local/sbin/niwa-admin service-status docker.service
sudo -n /usr/local/sbin/niwa-admin service-restart tailscaled.service
```

`hotspot-channel` accepts only 1, 6 and 11, the non-overlapping 2.4 GHz
channels. NIWA-AP drops for a few seconds and clients reconnect on their own;
if the hotspot does not come back up, the previous channel is restored.

The installer also adds `niwa-hotspot.path` and `niwa-hotspot.service`: NIWA
System writes a channel to `data/hotspot/request` and the path unit runs
`niwa-admin hotspot-request`, which validates it and writes
`data/hotspot/status.json`. The container never gets root or NetworkManager
access.

The wrapper intentionally does not allow arbitrary commands, package
installation, shutdown or reboot. Rare operating-system changes still require
an explicit password-authorized maintenance session.
