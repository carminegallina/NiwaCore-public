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
sudo -n /usr/local/sbin/niwa-admin service-status docker.service
sudo -n /usr/local/sbin/niwa-admin service-restart tailscaled.service
```

The wrapper intentionally does not allow arbitrary commands, package
installation, shutdown or reboot. Rare operating-system changes still require
an explicit password-authorized maintenance session.
