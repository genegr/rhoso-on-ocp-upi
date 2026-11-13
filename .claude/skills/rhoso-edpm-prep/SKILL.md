---
name: rhoso-edpm-prep
description: Prepare the pre-provisioned RHEL 9 bare-metal data-plane (EDPM / compute) hosts for RHOSO 18.0 - authorize the toolbox SSH key for root (playbooks/edpm_ssh_key.yml), add the pre-configured ctlplane VLAN connection (playbooks/edpm_ctlplane.yml), then release lock, exactly the RHOSO EUS repositories, UTC, package alignment with a reference host, dnf distro-sync and reboot into the new kernel (playbooks/edpm_prep.yml). Use whenever the user wants to onboard or re-prepare a compute host, fix repos/subscription release, update or align packages, reboot hosts into a new kernel, get SSH or the ctlplane address working on a host, or add a new compute node before the data-plane deployment.
---

# Data-plane host preparation

The hosts are already installed and registered (this project never registers them; `discover.yml` checks it). The
three playbooks run in order, from the toolbox with `-e env=<name>` (prefix in the `rhoso-jumpbox` skill). They
**change bare-metal hosts**: `--check --diff` first, show it, explicit go-ahead, and for the first real run of a
change `-l <one host>`.

## 1. `edpm_ssh_key.yml` (one-time per host)
Logs in as root with `vault_edpm_root_password` (sshpass in the toolbox) and authorizes the toolbox key
`.state/ssh/id_ed25519.pub` (comment `rhoso-toolbox`). After it, every playbook uses the key. The same key becomes
`dataplane-ansible-ssh-private-key-secret` for the operator.

## 2. `edpm_ctlplane.yml`
Pre-provisioned prerequisite (N3): connection `rhoso-ctlplane` = VLAN `<ctlplane vlan>` on `trunk_nic` (default
`bond0`), address `<ctlplane subnet>.<the host's management host number>`, no gateway, no DNS, IPv6 off, MTU from
`rhoso.networks`. Then waits for SSH on that address. Existing connections are never modified; os-net-config
(`configure-network` service) replaces this connection during the data-plane deployment.

## 3. `edpm_prep.yml`
```bash
ansible-playbook playbooks/edpm_prep.yml -e env=<name> --check --diff                 # preview
ansible-playbook playbooks/edpm_prep.yml -e env=<name>                                # lock, repos, UTC; previews distro-sync
ansible-playbook playbooks/edpm_prep.yml -e env=<name> -e distro_sync=true [-e reboot=true]
```
- Release lock `edpm_rhel_release` (default 9.6); `rhsm_repository purge: true` = exactly `edpm_repos` (default: BaseOS/
  AppStream/HA EUS, fast-datapath, rhoso-18.0, rhceph-7-tools, which `download-cache` needs for ceph-common even
  without Ceph). Time zone UTC.
- `dnf distro-sync --assumeno` preview, summarized (install/upgrade/downgrade/remove). It runs only with
  `-e distro_sync=true` and only when the preview has a transaction. Show the summary (downgrades and removals
  especially) before the go-ahead.
- `edpm_align: {reference: <host>, hosts: [...]}`: hosts installed with a smaller package set get the names the
  reference has (versions from the locked repos). Nothing is removed; kernel/boot-loader/EFI packages are excluded.
  The reference must be in the play (`-l` includes it).
- `-e reboot=true` reboots only hosts whose newest installed kernel isn't running (timeout 30 min, one host at a time
  is safest with `-l`).

## Checks afterwards
`host_audit.yml` (`rhoso-discover` skill): same release, repos and package set on every host, running kernel = newest.
A host that is already a deployed compute: drain or disable its nova-compute and migrate instances off before a
reboot; after it, run the data plane for that host (`rhoso-dataplane` skill).
