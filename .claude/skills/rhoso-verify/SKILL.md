---
name: rhoso-verify
description: Functional end-to-end verification of the deployed RHOSO 18.0 cloud before Tempest, via playbooks/verify.yml in the toolbox - the kept base objects (external provider network with a floating-IP pool, flavors, CirrOS image on Glance-on-Cinder), then a temporary project with one instance per compute and floating IPs (placement, metadata key, DHCP, MTU, north-south SSH, east-west pings), the router gateway chassis, a Pure volume with multipath on both iSCSI fabrics, boot from volume and live migration, with a PASS/FAIL report and full cleanup. Use whenever the user wants to know whether the cloud actually works, test instances, floating IPs, volumes or live migration, create the external network, image or flavors, rerun or clean up a verification, or prepare for Tempest.
---

# Functional verification (`playbooks/verify.yml`)

Run from the toolbox on the jump box (prefix in `rhoso-jumpbox`), always `-e env=<name>`. It **changes** vSphere (a
test vNIC on the jump box), the jump box (a temporary address) and the cloud: `--check --diff` first (prints the
plan and stops before any cloud change), then the user's go-ahead. Real runs take 20-30 min: background with
`.state/rhoso-verify.log`; the report is `.state/<env>/verify-report.md`.

```bash
ansible-playbook playbooks/verify.yml -e env=<name> --check --diff
ansible-playbook playbooks/verify.yml -e env=<name> [--skip-tags migration] [-e keep=true]
ansible-playbook playbooks/verify.yml -e env=<name> --tags cleanup     # after keep=true or an interrupted run
```

## Config (`envs/<env>.yaml`)
`networks.external` (VLAN on physnet `datacentre`, a /24), `rhoso.verify.external` (`gateway`, `pool: [first, last]`
host numbers) and `rhoso.verify.jumpbox_ip`, plus the `jumpbox.test_nics` entry with `network: external` (its port
group gets the test vNIC). Image, flavors, project name and tenant CIDR are role defaults
(`roles/rhoso_verify/defaults/main.yml`).

## Phases (tags)
| Tag | Kept? | Checks |
|---|---|---|
| `base` | yes (Tempest needs them) | external network + no-DHCP subnet with the pool; flavors; CirrOS image `active` and stored as `image-<id>` volume on `@pure` |
| `smoke` | no | instance ACTIVE on each compute (`--availability-zone nova:<host>`); SSH to each floating IP from the test leg; login with the metadata key, DHCP address, MTU = network MTU; ping from the first instance to all others |
| `gateway` | — | INFO only: router gateway port binding, OVN gateway chassis priorities, distributed FIP setting |
| `storage` | no | volume in-use; `multipath -ll` on the compute shows PURE with ≥ 2 active paths; iSCSI sessions on both fabrics; guest writes/reads a marker on `/dev/vdb`; boot-from-volume instance reachable |
| `migration` | no | live migration (`--os-compute-api-version 2.30 --host`) of the instance with the volume; reachable afterwards, marker intact |

`base` and `smoke` are prerequisites: narrow a run with `--skip-tags`, not `--tags`. A task error inside the phases
is recorded as an `aborted` FAIL and cleanup still runs. Any FAIL fails the play at the end.

## Rules and gotchas
- The first run pings the whole pool from the test leg before the external network exists: anything answering stops
  the run. Never shrink that check; pick another pool.
- A leftover project `rhoso-verify` (keep=true, interrupted run) stops `smoke`: run `--tags cleanup`.
- The `gateway` INFO is the evidence for the open physnet question: the masters' `datacentre` NIC is an access port
  group (VLAN 418 untagged) while the computes carry 418 tagged on `br-ex`. A gateway bound to a master with failing
  FIPs means the external VLAN can't work there.
- OpenStack calls go through `k8s_exec` in pod `openstackclient` (no SDK in the toolbox); instance checks use `raw`
  (CirrOS has no Python); `multipath -ll`/`iscsiadm -m session` are read-only commands on the compute.
- North-south here means jump box test leg → floating IP on the same L2. Routed reachability and instance SNAT to the
  outside need the external router (VyOS) and aren't covered.
