# CLAUDE.md

RHOSO 18 (Red Hat OpenStack Services on OpenShift) on an OpenShift cluster built by the sibling repo
`ocp-upi-baremetal-vms` (compact 3-node UPI on vSphere), with pre-provisioned RHEL 9 bare-metal data-plane (EDPM)
nodes. Ansible drives every step from that repo's pinned toolbox container on the Docker jump box.
**Follow the RHOSO 18.0 and matching OCP documentation**; every requirement we rely on is listed with its source in
`docs/network-requirements.md`.

## Hard rules (same as ocp-upi-baremetal-vms)
- Everything runs in the toolbox (`docker compose run --rm toolbox …`) on the jump box. The workstation only edits
  and syncs (`tools/sync.sh`). New tools = pinned entries in the OCP repo's `docker/`.
- No shell scripts; Ansible modules only. Sanctioned `command` uses, guarded with `changed_when: false` or `creates:`:
  `ping` (no module sends ICMP), on the hosts, the jump box and inside the netcheck probe container;
  `dnf distro-sync` in `edpm_prep.yml` (no module does it; previewed with `--assumeno`, run only when the preview
  has a transaction and `-e distro_sync=true`);
  `tcpdump` in `lldp.yml` (receive-only capture of the switches' LLDP/CDP frames; no module reads them);
  `multipath -ll` and `iscsiadm -m session` on a compute in `verify.yml` (read-only; no module reports them);
  `raw` on the CirrOS test instances in `verify.yml` (no Python in the guest);
  `oc`/`openstack` CLIs only where no module exists (`openstack` through `k8s_exec` in pod `openstackclient`).
  `plugins/modules/vmware_dvpg_security.py` exists because `community.vmware.vmware_dvs_portgroup` rebuilds the whole
  port group config (teaming, failure criteria, inherited flags) on every update: it sets only the security policy of
  an existing distributed port group.
- Generic roles come from the OCP repo, mounted read-only at `/ocp` (`roles_path = roles:/ocp/roles`): `olm_operator`
  installs each operator pinned to an exact CSV with Manual approval. Loop over it with a `loop_var` other than `item`
  (the role loops over `item` itself, and role vars are evaluated lazily).
- The `env_model` role also needs `community.docker`, `community.general`, `community.vmware`, `ansible.windows`
  from the OCP repo's toolbox image; checks there: `ansible-playbook <each playbook> --syntax-check -e env=<name>`.
- Secrets in `envs/vault.yml` (Ansible Vault), never on a command line; tasks carrying them use `no_log: true`.
- Pin every version (operator CSVs, images, packages); releases at least two weeks old.
- Idempotent: a second run reports `changed=0`. `netcheck.yml` cleanup leaves hosts exactly as found.
- Published on GitHub: no environment values in tracked files. Real values only in `envs/*` (except examples) and
  `.state/`. Examples use RFC 5737 addresses and example.com. Check `git add -A --dry-run` before finishing.
- Never commit or sync `.state/` or `envs/vault.yml`.

## Working rules
- Every playbook takes `-e env=<name>` (`envs/<name>.yaml`); always pass it explicitly.
- Changes to shared infrastructure (vSphere port groups, AD DNS, bare-metal host networking, the FlashArray):
  `--check --diff` first and the user's explicit go-ahead before a real run.
- `netcheck.yml` creates only `rhoso-test-*` interfaces and never touches existing connections.

## Layout
```
compose.yaml, ansible.cfg, inventory/   toolbox service (image from ../ocp-upi), localhost inventory
jumpbox/                                cloud-init user-data template + runbook for the jump box VM
envs/                                   <env>.yaml, vault.yml (gitignored), examples
docs/                                   network-requirements.md (doc-sourced checklist), design.md
playbooks/, roles/                      discover, netcheck, edpm_*, then the RHOSO phases (rhoso.yml: tags
                                        operators, networks, flasharray, controlplane, dataplane), verify.yml
plugins/modules/                        vmware_dvpg_security
.claude/skills/                         rhoso-* skills: jumpbox, discover, netcheck, edpm-prep, deploy, dataplane,
                                        verify, status
.state/                                 ssh keys, rendered user-data, reports, logs
```
