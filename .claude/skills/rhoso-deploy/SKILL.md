---
name: rhoso-deploy
description: Deploy or update the RHOSO 18.0 control plane on the OpenShift cluster built by ocp-upi-baremetal-vms, phase by phase via playbooks/rhoso.yml in the toolbox - operators (NMState check, MetalLB, cert-manager, OVN-K ipForwarding Global, openstack-operator pinned to an exact CSV + OpenStack CR), networks (NNCP per OCP node, macvlan/whereabouts NADs, MetalLB pools and L2Advertisements, NetConfig), flasharray (dedicated array user and token for Cinder), controlplane (osp-secret, Pure back end secret, OpenStackVersion with the certified Pure cinder-volume image, OpenStackControlPlane, the pure volume type). Use whenever the user wants to install or upgrade RHOSO operators, change isolated networks or IP ranges, change OpenStack services, Cinder/Glance on the FlashArray, rotate the Cinder array token, or asks why the control plane isn't Ready.
---

# RHOSO control plane (`playbooks/rhoso.yml`)

Read `CLAUDE.md` first. Run from the toolbox (prefix in `rhoso-jumpbox`), always `-e env=<name>` and the phase tag:
```bash
ansible-playbook playbooks/rhoso.yml -e env=<name> --tags <phase> [--check --diff]
```
The kubeconfig is the OCP repo's (`/ocp/.state/clusters/<ocp_cluster>/install/auth/kubeconfig`, read-only). Order:
`operators` → `networks` → `flasharray` → `controlplane` → `dataplane` (`rhoso-dataplane` skill). `--check --diff`
first; every phase must rerun with `changed=0`. Log long runs to `.state/rhoso-<phase>.log`.

Prerequisites from the OCP repo (`ocp-upi-*` skills): compact cluster on 4.20, masters schedulable, RHOSO port-group
NICs on the VMs, NMState operator + instance and the masters' iSCSI NICs + Pure multipath/udev MachineConfig from its
storage phase, a default RWO StorageClass (`rhoso.controlplane.storage_class`).

## Phases
| Tag | Does | Notes |
|---|---|---|
| `operators` | MetalLB, cert-manager, openstack-operator through the OCP repo's `olm_operator` (exact CSV, Manual approval), MetalLB and OpenStack CRs, namespace `openstack` (privileged PSA), `ipForwarding: Global` | pins in `roles/rhoso_operators/defaults`, overrides in `rhoso.operators.<key>`. Waits for speakers, cert-manager, OpenStack CR Ready, network CO not Progressing. Upgrade = bump the CSV (releases ≥ 2 weeks old) |
| `networks` | per node NNCP `rhoso-<node>` (address `<subnet>.<node host number>` on ctlplane/internalapi/tenant), NADs, MetalLB pools + L2Advertisements, NetConfig `openstacknetconfig` | every network a /24; ranges from `rhoso.ranges` (`nad`, `metallb`, `allocation`). Interface names come from the OCP cluster model MACs + NodeNetworkState, recorded in `.state/<env>/ocp-ifaces.json` (a NIC handed to OVN disappears from NNS). NNCP applied only when the spec differs |
| `flasharray` | array user `rhoso.cinder.flasharray.user`, member of the built-in policy (storage_admin), its own API token in `.state/<env>/flasharray-<user>.token` | **shared array**: `--check` and the user's go-ahead. Array-admin token (`vault_flasharray_api_token`) used only here. `-e flasharray_rotate_token=true` replaces the token (then rerun `controlplane`) |
| `controlplane` | `osp-secret` (passwords generated once into `.state/<env>/osp-secret/`), `cinder-volume-pure-secret`, OpenStackVersion `controlplane` (target = the operator's `OPENSTACK_RELEASE_VERSION`, Pure image via `customContainerImages`), OpenStackControlPlane rendered to `.state/<env>/openstackcontrolplane.yaml` then applied, waits Ready (up to 1 h), volume type `pure` | the Pure image tag must match the release (`rhoso.cinder.image`; checked). Cinder PureISCSIDriver on `storage`, `pure_iscsi_cidr_list` = the iSCSI networks, Glance on Cinder with multipath, OVN `datacentre` on `ovn_datacentre_portgroup`'s NIC |

## Rules and gotchas
- Never regenerate `osp-secret` files: they are the live service passwords. `.state/` is never synced or committed.
- `olm_operator` loops over `item` itself: loop it with another `loop_var`.
- The OpenStack CLI isn't in the toolbox: `kubernetes.core.k8s_exec` into pod `openstackclient` (read first, then
  create/set), as the docs do.
- Review the rendered `openstackcontrolplane.yaml` (no secrets in it) before a real run that changes it.
- Not Ready: `oc -n openstack get openstackcontrolplane controlplane -o yaml` conditions name the failing service;
  then that service's pods/events. A NAD/NNCP problem shows as pods stuck ContainerCreating on network attachment.
