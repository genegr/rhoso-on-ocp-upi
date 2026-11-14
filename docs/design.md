# Design

How this repository deploys RHOSO 18.0 and why. It's the design sign-off of the README flow (step 4): the choices
below are what the playbooks implement, and each one points at the code that owns it. The requirements behind them,
with their sources, are in [network-requirements.md](network-requirements.md) (IDs such as N4 refer to it).
Environment values are never written here. The real ones live in `envs/<env>.yaml`, and the examples use RFC 5737
addresses.

## 1. Overview

```
                 lab LAN (management) ──────────────────────────────────────────┬──────────── users
                        │                         │                             │
                   ┌────┴─────┐        ┌──────────┴──────────┐         ┌────────┴────────┐
                   │ jump box │        │ OpenShift, compact  │         │  VyOS router    │
                   │ toolbox  │        │ 3 masters (vSphere) │         │ (vSphere VM)    │
                   │ HAProxy  │        │ RHOSO control plane │         └────────┬────────┘
                   └──────────┘        └──┬───┬───┬───┬───┬──┘                  │ external VLAN
                                ctlplane  │   │   │   │   │ storage A/B         │ (floating IPs)
                             internalapi ─┘   │   │   │   └──────────┐          │
                                     tenant ──┘   │   └─ external    │          │
                                                  │      (unmapped)  │          │
                   ┌──────────────────────────────┴───────────────┐  │  ┌───────┴───────┐
                   │ bare-metal computes (pre-provisioned RHEL 9) ├──┴──┤  FlashArray   │
                   │ OVN gateways, Nova/libvirt, iscsid/multipath │     │ iSCSI A and B │
                   └──────────────────────────────────────────────┘     └───────────────┘
```

| Layer | What | Owner |
|---|---|---|
| Jump box | Ubuntu VM with Docker. It runs the pinned toolbox, HAProxy for the cluster VIPs and the netcheck probe | `jumpbox/`, OCP repo `infra.yml` |
| OpenShift | Compact 3-node UPI cluster on vSphere VMs (OCP 4.20), DNS zone in Active Directory, PX-CSI on the FlashArray | `../ocp-upi-baremetal-vms` |
| Control plane | `OpenStackControlPlane` in namespace `openstack` on the masters | `rhoso.yml --tags operators,networks,flasharray,controlplane` |
| Data plane | Pre-provisioned RHEL 9.6 (EUS) bare-metal computes, one node set per CPU group | `edpm_prep.yml`, `rhoso.yml --tags dataplane` |
| Storage | Cinder Pure iSCSI driver on the same FlashArray; Glance stores images in Cinder | `rhoso_flasharray`, `rhoso_controlplane` |
| External access | VyOS VM between the lab LAN and the external (floating-IP) VLAN | `router.yml` |
| Proof | `verify.yml` (functional), `tempest.yml` (Tempest and its plugins) | `rhoso_verify`, `rhoso_tempest` |

Versions: RHOSO 18.0.22 (OpenStack operator `v1.22.1`) on OCP 4.20 (V1), with computes on RHEL 9.6 EUS (V2). Every
operator is pinned to an exact CSV with Manual approval (`rhoso_operators/defaults`), as are the Pure cinder-volume
image tag (matching the RHOSO release, S1), the images and the toolbox.

## 2. OpenShift underneath

- **Compact cluster on VMs.** The three masters are schedulable and run the whole control plane. Red Hat states the
  minimum as a "3-node bare metal" cluster (V3). Running it on vSphere VMs is accepted for this proof of concept,
  whose scope is the FlashArray's performance with OpenStack, not control-plane behaviour under load. Section 11
  gives the path to bare metal.
- **NICs per master.** One NIC on the machine network for OpenShift, then one vNIC per RHOSO network: ctlplane,
  internalapi, tenant, external, and iSCSI A and B (N2). Each sits on its own port group. Interface names are
  matched by MAC, from the OCP cluster model, against each node's `NodeNetworkState`. They're also recorded in
  `.state/<env>/ocp-ifaces.json`, because a NIC handed to OVN disappears from `NodeNetworkState`.
- **Port groups relaxed** (promiscuous mode, forged transmits, MAC changes). NADs are macvlan, so pods put extra MACs
  on the node's vNIC (N5). `plugins/modules/vmware_dvpg_security.py` sets only the security policy of an existing
  distributed port group. The port groups are shared infrastructure, so this runs `--check --diff` first.
- **Storage for the control plane** (Galera, OVN DBs, RabbitMQ, Glance staging): PVCs from PX-CSI on the same
  array (`rhoso.controlplane.storage_class`). PX-CSI runs in **array mode** (`storage.flasharray.realm: false` in the
  OCP repo), not in a realm. In realm mode PX-CSI creates the masters' array hosts inside the realm, and Cinder's
  Pure driver, which has no realm support, then can't attach Glance's image volumes to those masters. See the OCP
  repo CLAUDE.md.
- **One owner for `/etc/multipath.conf` on the masters** (S4): the OCP repo's `storage_node` MachineConfig. The
  masters' iSCSI NICs and addresses come from that repo's storage phase (`ocp_ip_owner: ocp-storage` here).
- **Prerequisites** (V5): NMState (from the OCP storage phase, only checked here), MetalLB, cert-manager, and
  OVN-Kubernetes `gatewayConfig.ipForwarding: Global`.

## 3. Networks

| Network | Carries | OCP masters | Computes | NAD / MetalLB | MTU |
|---|---|---|---|---|---|
| management | SSH, default route, the jump box | machine network | native VLAN of the bond, on `br-ex` | — | site |
| ctlplane | data-plane Ansible, dnsmasq | own vNIC | VLAN on `br-ex` | yes / yes | 1500 |
| internalapi | API endpoints, RabbitMQ, OVN DBs | own vNIC | VLAN on `br-ex` | yes / yes | 1500 |
| tenant | Geneve overlay | own vNIC | VLAN on `br-ex` | yes / yes | 9000 |
| storage, storage2 | iSCSI fabrics A and B | own vNICs (OCP repo) | one dedicated NIC each | storage only / storage only | 9000 |
| external | floating IPs, router gateways | vNIC, not mapped | VLAN on `br-ex` (physnet `datacentre`) | — | 1500 |

- **ctlplane on its own VLAN**, not the OpenShift machine network (N4). The data plane's documented examples use a
  dedicated ctlplane, and a separate VLAN keeps the NAD, MetalLB and NetConfig ranges out of a subnet the lab
  shares. The computes keep their management address and default route. ctlplane only carries RHOSO.
- **Same host number in every subnet.** Every RHOSO network is a /24 (asserted). A node gets the same last octet on
  each network: masters keep their machine-network number, computes their management number. The fixed ranges are
  `rhoso.ranges` (`nad`, `metallb`, `allocation`). `netcheck.yml` proved the planned ranges free before
  deployment.
- **The second iSCSI fabric** (N8) is a custom network `storage2`. It's in NetConfig, for the computes' fixed IPs,
  but has no NAD and no MetalLB pool. Cinder learns both fabrics through `pure_iscsi_cidr_list`.
- **Objects** (`rhoso_networks`): one NNCP per master for ctlplane, internalapi and tenant. It's applied only when
  the spec differs, because NMState stamps every update. Also a macvlan NAD with whereabouts per network, MetalLB L2
  pools and advertisements pinned to that network's interface, and the `NetConfig`.
- **Tenant MTU.** Tenant networks get 1500, which is what images and users expect. The tenant VLAN runs at 9000.
  Neutron gives Geneve networks `min(global_physnet_mtu, path_mtu) - 58`, so `global_physnet_mtu` = 9000 (the
  underlay) and `path_mtu` = 1558. Physnet `datacentre` stays at 1500.
- **Validation before deployment** (`netcheck.yml`): temporary `rhoso-test-*` interfaces on the jump box and the
  hosts. They prove L2 adjacency on every network, MTU 1500 and 9000 with DF set, iSCSI 3260 to every portal of each
  fabric, free ranges, registry reachability, DNS and time sync. The hosts are left exactly as found.

## 4. Control plane (`rhoso_controlplane`)

- **Services enabled:**
  - Keystone, Placement, Glance, Cinder, Nova, Neutron/OVN, Horizon, Barbican;
  - the infrastructure underneath: Galera (two instances, `openstack` and `openstack-cell1`), RabbitMQ (two
    clusters), Memcached, dnsmasq.
- **Disabled:** Heat, Octavia, Designate, Manila, Swift, Ironic, telemetry. Tempest leaves their plugins out
  automatically.
- **Replicas:** 3 for the APIs, Galera, RabbitMQ, Memcached and the OVN DBs. 1 for the schedulers, conductors,
  `cinder-volume` and Horizon. Nova has two cells: cell0, and cell1 holding the computes.
- **Endpoints.** Public endpoints are OpenShift routes `<service>-openstack.apps.<domain>` behind the cluster
  ingress. Internal endpoints share one MetalLB address on internalapi. dnsmasq sits on ctlplane, and each RabbitMQ
  cluster gets its own internalapi address.
- **TLS:** the operator defaults, with certificates from RHOSO's own CAs (`rootca-public` for the routes). Users trust
  that CA (`access.md`).
- **DNS.** dnsmasq forwards to `rhoso.controlplane.dns_forwarders` (N10). Instances get
  `instance_dns_servers` through OVN DHCP on subnets that set none (`[ovn] dns_servers`). The DC has no route back
  to the external network, so the router masquerades those queries.
- **OVN gateways only on the computes** (N9). The masters' external vNIC is an access port group (the VLAN arrives
  untagged), while the external network is a tagged VLAN, so a gateway that failed over to a master would break
  floating IPs. Neutron schedules gateways only on chassis with a bridge mapping for the external physnet. That's
  why the masters get no `datacentre` mapping: `nicMappings` is left out unless `ocp_nodes_gateway` is set.
- **`osp-secret`.** Each key is a random password, generated once into `.state/<env>/osp-secret/`. The admin password
  can be chosen (`vault_rhoso_admin_password`). It's set through the Keystone API first and written into the secret
  after (`admin_password.yml`). Changing it in the secret alone leaves Keystone on the old one. Service passwords
  aren't rotated after deployment, which Red Hat doesn't support.

## 5. Data plane (`edpm_prep.yml`, `rhoso_dataplane`)

- **Pre-provisioned hosts.** RHEL 9 is already installed and keeps its management address. `edpm_prep.yml`:
  - sets the release lock and the RHOSO EUS repositories;
  - runs a `dnf distro-sync`, previewed and opt-in;
  - aligns the package set to a reference host (optional);
  - installs the data-plane SSH key.

  `edpm_ctlplane.yml` puts the first ctlplane address on the hosts (N3).
- **Network config** (`edpm_network_config_template`):
  - `br-ex` sits over an active-backup bond, with the management address and the default route;
  - ctlplane, internalapi and tenant are VLAN ports on `br-ex`;
  - each iSCSI fabric has its own NIC, with no bond, because multipath does the redundancy;
  - the NIC names come per host model (`rhoso.dataplane.models`).
- **Services.** The standard set (bootstrap through libvirt), plus:
  - `pure-storage-udev`: the Pure udev rules, the same as the OCP nodes';
  - `nova-<node set>`: Nova with multipath on (`volume_use_multipath`) and the guest CPU model of the node set.

  The Pure `multipath.conf` reaches `edpm_multipathd` through a ConfigMap.
- **CPU groups** (`rhoso.dataplane.cpu_groups`). Nova's default `host-model` shows each guest its host's exact CPU,
  so live migration fails between hosts of different CPU generations ("missing features"). Each group is a node
  set with its own Nova service and `cpu_mode custom` with `cpu_models`. The model is picked with
  `virsh hypervisor-cpu-compare` inside `nova_compute`, as the newest one every host of the group runs. With custom
  models the destination CPU check is turned back on (`skip_cpu_compare_on_dest = false`). It's what keeps a live
  migration off a host of another group, so the conductor tries the next host instead of letting libvirt abort the
  migration. Live migration works within a group. Between CPU vendors there's no common model, and that migration isn't supported,
  while cold migration works. Without `cpu_groups` there is one node set with `host-model`.
- **Deployments** are created once per `dataplane_run` and never edited, because a spec change would rerun the
  services. A node set locked by a running deployment is left alone. Computes are mapped to cell1 afterwards.

## 6. Storage

- **Cinder.** One back end `pure` (`PureISCSIDriver`), which is also the default volume type. `cinder-volume` runs
  on the masters with the storage NAD, `use_multipath_for_image_xfer`, and the array token in
  `cinder-volume-pure-secret` (S2).
- **The array user** is dedicated to Cinder: `rhoso.cinder.flasharray.user`, in the built-in `storage_admin` policy,
  created by `rhoso_flasharray`. Its API token is shown by the array only at creation, so it's stored in
  `.state/<env>/` and checked by logging in. The admin token stays in the vault.
- **iSCSI only.** Both fabrics on every compute and every master, with multipath on both sides (N7, S3).
  `verify.yml` checks the paths.
- **iSCSI belongs to OpenStack** on the computes. A record left by a hand-made login with the host's newer
  `iscsiadm` makes `nova_compute`'s `iscsiadm` fail on that target, and with it every attach and every live
  migration with a volume. `verify.yml` checks for such records.
- **Glance on Cinder.** Each image is a volume in project `service`, of a private **multiattach** type
  (`glance_volume_type`). With a plain type, concurrent downloads of one image, such as the same image booting on
  several computes, fail on "attaching". The Cinder quota of project `service` is unlimited (`glance_service_quota`),
  because its default of 10 volumes caps the number of images.
- **Not deployed:** Cinder backup, Manila, Swift, and NVMe for Cinder.

## 7. External access (`router.yml`)

- A VyOS VM, built as an OVA in the sibling `vyos-vsphere-image` repo. `eth0` is on the lab LAN, and `eth1` is the
  external network's gateway. It's configured only with `vyos.vyos` modules. Its cloud-init seed applies once.
- **Floating IPs** come from `rhoso.verify.external.pool` on network `public` (physnet `datacentre`, the external
  VLAN). Routers' gateways are on the computes, with distributed floating IPs.
- **Filtering.** Instances are source-NATed except toward `allowed_sources`, and only `allowed_sources` may open
  connections to them. Each machine that needs the instances adds a static route for the external network via the
  router's LAN address. The jump box gets it from us; other machines' owners add it themselves. Nothing changes on
  the lab's own routers.

## 8. Secrets and access

- **Secrets in the vault.** `envs/vault.yml` (Ansible Vault) holds:
  - the vCenter and AD credentials;
  - the array admin token;
  - the computes' root password, used once to install the data-plane SSH key;
  - the optional admin and tenant passwords.

  The hosts pull from the Red Hat registry with the cluster's pull secret. Generated values (osp-secret keys, SSH
  keys, the Cinder user's token, tenant passwords) are kept in `.state/<env>/` on the jump box only. Tasks carrying
  any of them use `no_log`. Nothing secret goes on a command line.
- **Users.** People get projects from `tenant.yml`: member role, quotas, an optional starter network, and SSH/ICMP
  in the default group. Passwords come from `vault_tenant_password` when it's set, or are generated otherwise. A
  rerun puts the configured password back on a user that can't log in with it.
- **Admin access to nodes.** The data-plane SSH key is at `.state/ssh/` (root on the computes). The masters are
  reached with `oc debug node/<name>` or SSH as `core`.

## 9. Operations

- **Order:** the phases follow the README flow. Each one is a playbook or tag, and the end-to-end runbook with its
  gates is the `rhoso-lab` skill.
- **Idempotence:** every phase reports `changed=0` on a second run.
  - CRs that an operator would act on again are created once: the deployments, the Tempest runs.
  - Objects that a webhook or the operator's defaulting rewrites are compared before applying: the NNCPs, the dns
    options.
- **`--check`:** `k8s_exec` ignores check mode, so every changing exec is skipped under `--check`. Playbooks that
  can't preview refuse it.
- **Proof:**
  - `verify.yml` checks:
    - the external network, the images and flavors;
    - one instance per compute with a floating IP and outbound access;
    - Pure volumes with multipath;
    - live migration within each CPU group;
    - the gateway placement;
    - the iSCSI records.

    Its report is `.state/<env>/verify-report.md`.
  - `tempest.yml` runs smoke, then the full suite of Tempest plus the plugins of the deployed services, through the
    test-operator. Exclusions are listed with their reasons in `rhoso_tempest/defaults`.
- **Teardown:** `rhoso_teardown.yml` removes the control plane and its persistent volumes, so every database is
  lost. It keeps the operators, the networks, the secrets, the node sets and the hosts. A rebuild is `controlplane`,
  then `dataplane` with a new `dataplane_run`. It needs a typed confirmation each time. Shared infrastructure (port
  groups, AD DNS, the array, host networking) is changed only after `--check --diff` and a yes.

## 10. Decisions

| Date | Decision | Instead of | Why |
|---|---|---|---|
| 2026-11-06 | OCP 4.20, RHOSO 18.0 FR6 (18.0.22) | 4.18 | Greenfield: the newest OCP the release supports (V1) |
| 2026-11-12 | ctlplane on its own VLAN | sharing the machine network (macvlan on `br-ex`) | Documented layout, ranges out of a shared subnet (N4) |
| 2026-11-12 | Second iSCSI fabric as custom network `storage2` | one fabric | Path redundancy; no documented procedure, so NetConfig only (N8) |
| 2026-11-12 | One dedicated array user for Cinder | the admin token | Least privilege, separate audit trail |
| 2026-11-13 | PX-CSI in array mode | a realm per cluster | Cinder can't attach to realm hosts (no realm support in its driver) |
| 2026-11-13 | OVN gateways only on the computes | gateways on the masters too | The masters' external vNIC is untagged; a failover would break floating IPs (N9) |
| 2026-11-13 | Tenant MTU 1500 over a 9000 underlay | 1442 | What images and users expect; no fragmentation |
| 2026-11-13 | Instance DNS = the lab DC, through the router | dnsmasq / VyOS forwarding | Lab and internet names resolve with no extra service |
| 2026-11-13 | Own VyOS router for floating IPs | the lab's routers | No change to shared routing; explicit filter |
| 2026-11-14 | One node set per CPU group, custom CPU models | `host-model` | Live migration within a group; vendors can't mix |
| 2026-11-14 | Glance image volumes multiattach, `service` quota unlimited | defaults | Concurrent boots of one image; more than 10 images |
| 2026-11-14 | Image signature verification not enforced in Nova | enforced | No signing workflow in the lab; Tempest is told so |
| 2026-11-14 | Standard admin and tenant passwords from the vault | generated passwords | Lab convenience; the admin password goes through the Keystone API |
| 2026-11-14 | Control plane on the compact cluster's VMs | bare-metal OCP nodes | Proof of concept of FlashArray performance; control plane under load out of scope (V3). If that changes: 3 compact nodes on bare metal |

## 11. Open items and limits

- **V3: the control plane runs on vSphere VMs, where Red Hat documents bare metal.** This is a known and accepted
  limit of the proof of concept. Under heavy provisioning (many instances or volumes created at once) the API
  services may respond more slowly than on bare metal. That's out of scope: the proof of concept measures the
  FlashArray data path, and Tempest doesn't test it. If such load tests become in scope, the cluster moves from 3
  compact nodes on VMs to 3 compact nodes on bare metal: the same layout, so quorum (Galera, RabbitMQ, OVN DBs, 3
  replicas each) and the RHOSO roles stay as they are. Each bare-metal node needs one NIC (or VLAN) per network the
  masters have today (section 2). The OCP repo's platform layer creates only vSphere VMs, so booting the
  self-installing ISOs on physical servers (through their BMC's virtual media) is new work there.
- The `[recheck]` rows of network-requirements.md still need a browser check against the Red Hat docs.
- **No live migration between CPU vendors.** Cold migration only.
- **Not deployed:** Octavia (load balancers), Designate, Heat, Manila, Swift, telemetry. Adding one means enabling it
  in the template, after which Tempest picks up its plugin.
- **No password rotation for the service users** after deployment.
- **One `cinder-volume` replica**, which is the driver's supported mode. Volume operations wait while it restarts;
  existing attachments don't.
