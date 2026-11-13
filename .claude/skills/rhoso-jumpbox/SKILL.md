---
name: rhoso-jumpbox
description: Build, rebuild or check the Ubuntu 26.04 Docker jump box this RHOSO project runs from (Canonical cloud-image OVA, cloud-init user-data rendered from jumpbox/user-data.yaml.j2, pinned Docker Engine, the HAProxy VIPs), and keep the two repositories in sync onto it with tools/sync.sh. Use whenever the user wants a new or replacement jump box, to render or base64 the user-data, deploy the OVA in vCenter, fix SSH access to the jump box, build the toolbox image, set up the vault password files, or push local edits to the jump box ("sync", "copy to the jumpbox", "run it on the jumpbox"), even if they only say "the jumpbox".
---

# Jump box and sync

`jumpbox/README.md` is the runbook. It's the one manual step: nothing exists yet to automate it from.

## Layout
- **Authoring machine** (Windows, Git Bash): two checkouts side by side, `ocp-upi-baremetal-vms` and `rhoso`. Edit
  there only. Each has a gitignored `.sync.env` (`SYNC_HOST`, `SYNC_DIR`, optional `SYNC_SSH_OPTS`).
- **Jump box**: `~/ocp-upi` and `~/rhoso` side by side. rhoso's `compose.yaml` mounts `../ocp-upi` read-only at
  `/ocp` (generic roles, modules, the cluster's kubeconfig and `oc` binary).
- **Jump-box-only files**: `.state/` in both repos (vault-pass, SSH keys, kubeconfig, osp-secret, tokens, reports,
  logs), `envs/vault.yml` here and `clusters/vault.yml` in the OCP repo. Never overwrite, sync or delete them.

## Sync
```bash
bash tools/sync.sh                                  # in rhoso
bash ../ocp-upi-baremetal-vms/tools/sync.sh         # the OCP repo
```
tar never deletes: after removing or renaming a file locally, `rm` it on the jump box too. Sync before every run that
uses changed files. Before a sync after a long break, diff the jump box copy against the local tree
(`ssh <host> 'tar cf - --exclude=./.state -C rhoso .'`): edits made directly on the jump box would be overwritten.

## Running things
Every tool runs in the toolbox (image `ocp-upi-toolbox:1`, built in the OCP repo):
```bash
ssh <SYNC_HOST> 'cd rhoso && docker compose run --rm -T toolbox ansible-playbook playbooks/<p>.yml -e env=<name> ...'
```
`ansible.cfg` points at `.state/vault-pass`. Long runs go in the background with output to `.state/<name>.log`, then
`grep -E "fatal|PLAY RECAP" -A8` the log.

## (Re)building the jump box
1. Fill `jumpbox:` and `docker:` in `envs/<env>.yaml`: static IP, MAC set manually on the primary vNIC before first
   boot (netplan matches it), `extra_ips` = HAProxy VIPs, AD DNS server, public keys only, pinned Docker packages
   (releases at least two weeks old).
2. Render `jumpbox/user-data.yaml.j2` to `.state/jumpbox/user-data.yaml`, base64 it (PowerShell snippet in the README).
3. Download the pinned OVA and check it against `SHA256SUMS`.
4. vCenter *Deploy OVF Template*: routed LAN port group (same as the OCP machine network), *Encoded user-data* = the
   base64, empty password. Before powering on: 4 vCPU, 16 GB, disk 100 GB.
5. Check: `cloud-init status` = done, IP + both VIPs on the NIC, DNS through the AD DC,
   `docker version && docker compose version && docker buildx version`.
6. Sync both repos, build the toolbox in `~/ocp-upi` (`docker buildx bake -f compose.yaml --allow=network.host
   toolbox`), recreate the vault password files and vaults (`ansible-vault encrypt`, values over stdin, never on a
   command line).

## Access
- Workstation key: append the `.pub` to `~ocpadmin/.ssh/authorized_keys` (one-time password login if needed).
- Toolbox key (`.state/ssh/id_ed25519`, created by `env_model`): also in the jump box user's `authorized_keys`, and
  for root on the data-plane hosts through `edpm_ssh_key.yml` (`rhoso-edpm-prep` skill).
- The OCP cluster's HAProxy for this environment runs on the jump box (`~/containers/<cluster>/haproxy`, managed by
  the OCP repo's infra role: never edit it by hand).
