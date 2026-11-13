---
name: rhoso-netcheck
description: Validate the RHOSO network layout before deploying anything - the dedicated vSphere port groups with relaxed security for macvlan and the jump box test vNICs (playbooks/netcheck_vsphere.yml), then temporary VLAN interfaces and a macvlan probe container proving L2 adjacency, MTU (DF pings), iSCSI portals, SSH, registries, DNS and time sync between the jump box and the bare-metal hosts (playbooks/netcheck.yml), checked against docs/network-requirements.md. Use whenever the user wants to test or prove the networks, VLANs, trunks, MTU/jumbo frames, iSCSI reachability, free IP ranges, create or fix the RHOSO port groups, add or remove test vNICs, clean up after a netcheck, or debug why a host can't reach another on a VLAN, even if they just say "check the network".
---

# Network validation (the gate before any deployment)

`docs/network-requirements.md` lists each requirement (V*, N*, S*), its source and the check that proves it.
Nothing is deployed before netcheck passes. Both playbooks **change shared infrastructure** (vSphere, the jump box,
the bare-metal hosts): run with `--check --diff`, show the output, and get the user's explicit go-ahead before a real
run. Prefix and `-e env=<name>` as in the `rhoso-jumpbox` skill.

## 1. vSphere side: `netcheck_vsphere.yml`
| Tag | Does |
|---|---|
| `portgroups` | dedicated port groups from `vsphere.portgroups` (standard vSwitch or `dvswitch:`), VLAN, and with `relaxed: true` promiscuous + forged transmits + MAC changes (macvlan NADs need them, N5). `portgroups_relax_existing` only relaxes existing groups; `portgroups_retired` moves vNICs off and removes old ones. Kept afterwards: the OCP VMs use them |
| `nics` | one test vNIC per `jumpbox.test_nics` entry, hot-added only if missing |
| `cleanup` | removes the test vNICs (only with `--tags cleanup`) |

The VDS path uses `plugins/modules/vmware_dvpg_security.py`, which sets only the security policy
(`community.vmware.vmware_dvs_portgroup` would rebuild the whole port group).

## 2. Hosts and jump box: `netcheck.yml`
```bash
ansible-playbook playbooks/netcheck.yml -e env=<name> [--limit localhost,jumpbox,<host>,...] [-e keep=true]
```
1. Planned ranges (`netcheck.free_ranges`, NAD/MetalLB/allocation, floating IPs) must not answer: checked before any
   test interface exists.
2. Jump box: test vNICs up at MTU 9000 (systemd-networkd); a probe container with one macvlan leg per test network
   (`netcheck.probe_ips`). `probe: false` NICs get the test address themselves.
3. Hosts: temporary `rhoso-test-*` NetworkManager connections only (VLANs on `trunk_nic` for
   `host_vlan_networks`, addresses on iSCSI NICs that have none). Host test IP = `<subnet>.<host_ip_base + n>`, so
   test networks must be /24. Existing connections are never touched.
4. Checks: DF pings per network and MTU (`netcheck.mtus`, 1472/8972 payloads) both ways, host to host on L2-only VLANs
   (separates switch from vSphere problems), neighbour table, TCP 3260 to each fabric's array portals, SSH to every
   ctlplane address, HTTPS to `netcheck.urls`, DNS through AD, chronyd.
5. Cleanup always runs and leaves hosts exactly as found (`-e keep=true` keeps everything for debugging; then
   `--tags cleanup` removes it). Report: `.state/<env>/netcheck-report.md`.

## Reading failures
- Probe → host fails but host → host works on the same VLAN: vSphere side (port group VLAN, security policy, vNIC on
  the wrong group). Both fail: switch side (VLAN not on the trunk, see `lldp.yml` for the port).
- 1500 works, 9000 fails: MTU on a switch/vSwitch in the path. Record per network; the design decides which networks
  run jumbo.
- A planned address answers: the range is not free. Pick another range in `envs/<env>.yaml`, never "probably unused".
- iSCSI: each fabric must reach its own portals; cross-fabric reachability isn't required.
