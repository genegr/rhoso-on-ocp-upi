---
name: rhoso-discover
description: Read-only discovery and audits of the RHOSO environment - vSphere host networking and capacity, AD DNS, the jump box and the bare-metal data-plane hosts (playbooks/discover.yml), whether the data-plane hosts are identical and meet the RHOSO 18.0 pre-provisioned node prerequisites (playbooks/host_audit.yml), and which switch port sits behind each bond NIC via LLDP/CDP (playbooks/lldp.yml). Use whenever the user asks what is in the lab, wants an inventory or capacity check, asks about OS versions, subscriptions, packages, firmware, NICs, switch ports or VLANs of the compute hosts, or wants to know whether a new host matches the others, even if they just say "check the hosts".
---

# Discovery and audits (read-only)

All three playbooks only read. Run from the toolbox on the jump box (prefix in the `rhoso-jumpbox` skill), always
with `-e env=<name>` (`ls envs/*.yaml`). Reports go to `.state/<env>/` and stay there (they contain environment
values: never copy them into tracked files).

| Playbook | Report | Notes |
|---|---|---|
| `discover.yml [--tags vsphere,dns,jumpbox,edpm]` | `discovery.yml` | A partial run only replaces the parts it collected |
| `host_audit.yml [-e audit_updates=false]` | `host-audit.md` | `audit_updates` refreshes dnf metadata to list pending updates |
| `lldp.yml [-e lldp_wait=70] [-l <host>]` | `lldp-report.md` | tcpdump, receive-only; waits one LLDP (30 s) / CDP (60 s) interval |

## What each checks
- **discover**: datacenters, clusters, ESXi CPU/RAM, datastores, vmnics, vSwitches, port groups with VLAN and security
  policy, VDS port groups; AD: domain SOA, the cluster zone (must not exist before the OCP install), registry names,
  A/PTR of every data-plane host, WinRM port and login; jump box and hosts: OS, kernel, CPU/RAM, NICs (MAC, speed,
  MTU, PCI id), routes, DNS, disks; hosts also subscription cert, NetworkManager profiles, chronyd.
- **host_audit**: packages, kernel, release lock (`releasever`), enabled repos, entitlement, `/dev/kvm`, `cloud-admin`
  user, sudoers drop-ins, pending updates. It answers "are all hosts the same" and requirement V2 in
  `docs/network-requirements.md` (RHEL 9.4/9.6, EUS repos).
- **lldp**: per bond member: switch name, port, native VLAN. The bond is `edpm_hosts[].trunk_nic`, else
  `netcheck.trunk_nic`, else the default-route NIC. Needs `tcpdump` on the host.

## Reading the results
- Hosts that differ in package set: `edpm_prep.yml` with `edpm_align` (`rhoso-edpm-prep` skill) installs what the
  reference host has. Kernel/firmware differences are reported, not fixed.
- Not subscribed or wrong release: fix before `edpm_prep.yml`. Registration is never done by this project.
- No LLDP frame: the switch port may have LLDP off; try `-e lldp_wait=130` for CDP-only switches.
- A new host joining: add it to `edpm_hosts`, run all three with `-l localhost,<host>` (or `--limit`), compare its
  `host-audit.md` and NIC model against the others, then follow `rhoso-netcheck` and `rhoso-edpm-prep`.
