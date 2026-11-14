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
  The VyOS router (`router.yml`) is configured only with `vyos.vyos` modules over `network_cli` (libssh); its
  cloud-init seed applies once, at the VM's first boot.
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
- **`k8s_exec` ignores check mode**: under `--check` it runs the command for real (found 2026-11-14: a controlplane
  `--check` created a volume type and retyped volumes). Every changing `k8s_exec` task needs
  `when: not ansible_check_mode`, or its playbook refuses `--check` (`verify.yml` ends the play, `tenant.yml` asserts).
- **A "changed" with no spec change** (generation unchanged, the diff only moves our `managedFields` entry) means the
  operator puts back at admission something the template leaves out: we rewrite it, it restores it, every run. Found
  with `dns.template.options` (`local /openstack.svc/`). Compare the rendered CR with the live one and add the field.
- Computes with different CPUs: Nova's default `host-model` breaks live migration between them ("guest CPU doesn't
  match specification: missing features"). `rhoso.dataplane.cpu_groups` = one node set per CPU group, each with its
  own Nova service and `cpu_models` (pick with `virsh hypervisor-cpu-compare` inside `nova_compute`).

## Short and spoken prompts
Prompts are often dictated (`/voice`): short, with no flags or file names, and with words misheard.
- **Map the words**:
  - "rose so", "row so", "R H O S O", "Red Hat OpenStack", "OpenStack", "the cloud" → this repo.
  - "O C P", "open shift", "the cluster" → `../ocp-upi-baremetal-vms` (its own CLAUDE.md and skills; read them from
    there when they aren't loaded).
  - "E D P M", "the computes", "compute nodes", "bare-metal hosts" → the data plane.
  - "temp est" → Tempest.
  - "vi OS", "vios" → the VyOS router.
  - "jump box" → `SYNC_HOST`.
- **Entry points**:
  - "deploy / rebuild / continue the lab" (OpenShift + OpenStack, or either), "what's next", "where are we" →
    skill `rhoso-lab`.
  - "is it up?" → `rhoso-status`, which also covers OpenShift.
  - "does it work?" → `rhoso-verify`.
  - "run tempest" → `rhoso-tempest`.
  - "add a user / project / image" → `rhoso-tenant`.
- **Target**: with one non-example `envs/*.yaml`, use it and its `ocp_cluster`, and say both back in the first line.
  With several, ask.
- **Gates stay gates**: a dictated "deploy it" covers the steps, never consent. Shared infrastructure (above),
  `rhoso_teardown.yml`, OCP `destroy.yml` and storage teardown still need a yes in a reply to the shown plan. Treat
  "clean up", "reset", "wipe", "redo" and "start over" as possibly destructive: say what would be deleted and ask.
  Ask too when a name, a host or a number reads garbled.
- **Replies**: first a one-line plan (the steps, the time, where it will stop for a yes). Then a line per finished
  step. At the end a few plain sentences, without tables.

## Layout
```
compose.yaml, ansible.cfg, inventory/   toolbox service (image from ../ocp-upi), localhost inventory
jumpbox/                                cloud-init user-data template + runbook for the jump box VM
envs/                                   <env>.yaml, vault.yml (gitignored), examples
docs/                                   network-requirements.md (doc-sourced checklist), design.md
playbooks/, roles/                      discover, netcheck, edpm_*, then the RHOSO phases (rhoso.yml: tags
                                        operators, networks, flasharray, controlplane, dataplane), verify.yml,
                                        router.yml (VyOS, OVA from ../vyos-vsphere-image), images.yml, tenant.yml,
                                        tempest.yml, rhoso_teardown.yml
plugins/modules/                        vmware_dvpg_security
.claude/skills/                         rhoso-* skills: lab (end-to-end runbook, the entry point), jumpbox,
                                        discover, netcheck, edpm-prep, deploy, dataplane, router, verify, tenant,
                                        tempest, status, teardown
                                        (OCP skills load with: claude --add-dir ../ocp-upi-baremetal-vms)
.state/                                 ssh keys, rendered user-data, reports, logs
```
