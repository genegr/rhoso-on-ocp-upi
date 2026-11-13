# Jump box (Ubuntu 26.04, Canonical cloud image OVA)

The one manual step of the project: nothing exists yet to automate it from. The VM gets Docker Engine (pinned,
Compose v2, buildx) and nothing else; every tool runs in the toolbox container.

## 1. Render the user-data
Fill `envs/<env>.yaml` (`jumpbox:` and `docker:` blocks) and render `jumpbox/user-data.yaml.j2` into
`.state/jumpbox/user-data.yaml` (gitignored), then base64-encode it:

```powershell
$p = ".state\jumpbox"
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$p\user-data.yaml")) | Set-Content -NoNewline "$p\user-data.b64"
```

## 2. Get the pinned image
Pinned release: `https://cloud-images.ubuntu.com/releases/26.04/release-20261016/ubuntu-26.04-server-cloudimg-amd64.ova`.
Download it and check it against `SHA256SUMS` in the same directory:

```powershell
(Get-FileHash .\ubuntu-26.04-server-cloudimg-amd64.ova -Algorithm SHA256).Hash
```

## 3. Deploy in vCenter
*Deploy OVF Template* → Local file (the checked OVA):
- name `jumpbox`, the target ESXi host, the datastore, thin provisioning;
- network: the port group of the routed LAN VLAN (the same one the OCP machine network uses);
- **Customize template**: *Encoded user-data* = content of `.state/jumpbox/user-data.b64`; leave password empty
  (SSH key only), hostname `jumpbox`.

Before powering on: 4 vCPU, 16 GB RAM, grow the disk to 100 GB (cloud-init grows the filesystem).
Power on. First boot takes a few minutes (apt update + Docker).

## 4. Check
```sh
ssh -i .state/ssh/workstation_ed25519 ocpadmin@<jumpbox ip> 'docker version && docker compose version && docker buildx version'
```
Expect `cloud-init status` = `done`, the static IP plus the two VIPs on the NIC, DNS resolving through the AD DC.

## 5. Bring the repositories over
From the workstation (Git Bash), once per change:
```sh
SYNC_HOST=ocpadmin@<jumpbox ip> SYNC_DIR=ocp-upi SYNC_SSH_OPTS="-i .state/ssh/workstation_ed25519" bash ../ocp-upi-baremetal-vms/tools/sync.sh
SYNC_HOST=ocpadmin@<jumpbox ip> SYNC_DIR=rhoso SYNC_SSH_OPTS="-i .state/ssh/workstation_ed25519" bash tools/sync.sh
```
Directories on the jump box: `~/ocp-upi` and `~/rhoso` side by side (this repo's `compose.yaml` mounts `../ocp-upi`).
Then on the jump box: build the toolbox in `~/ocp-upi`
(`docker buildx bake -f compose.yaml --allow=network.host toolbox`), create the vault password files and vaults
(`clusters/vault.yml` there, `envs/vault.yml` here).
