# RHOSO 18.0 requirements checklist

Each requirement this deployment relies on, with its source and the check that proves it before anything is deployed.
`netcheck` = `playbooks/netcheck.yml`, `discover` = `playbooks/discover.yml`. Environment values are never written here.

Sources (base `https://docs.redhat.com/en/documentation/red_hat_openstack_services_on_openshift/18.0/html/`):
- **PYD**: *Planning your deployment*. **DEP**: *Deploying Red Hat OpenStack Services on OpenShift*.
- **CPS**: *Configuring persistent storage*. **CNS**: *Configuring networking services*.
- **LC**: Red Hat OpenStack Platform Life Cycle (`access.redhat.com/support/policy/updates/openstack/platform`).
- **KCS 7125383**: how RHOSO versions map to OpenStack Operators and OpenStackVersion CRs.

> Source status (2026-11-06): LC, KCS 7125383, the certified-hypervisors article and the Red Hat catalog were read
> directly. docs.redhat.com pages were read only through search-index excerpts (the site refused automated fetches),
> so each **[recheck]** row must be confirmed in a browser before sign-off (Phase 4).

## Versions and platform
| ID | Requirement | Source | Check | Expected |
|---|---|---|---|---|
| V1 | RHOSO FR6 (18.0.21; 18.0.22 is a later bug-fix release on FR6) supports OCP 4.18 and 4.20. Greenfield: latest OCP in the table only, so **4.20** | LC, KCS 7125383 | cluster config pins 4.20.z | OCP 4.20 |
| V2 | Data-plane nodes: RHEL 9.4 or 9.6. Release locked, EUS repos (baseos/appstream/highavailability EUS, fast-datapath, rhoso-18.0) | LC; certified-hypervisors article; DEP node set example **[recheck]** | discover: OS version, subscription | 9.6, subscribed with EUS |
| V3 | Control plane on a compact or 3+3 OCP cluster; the stated minimum is a "3-node **bare metal**" cluster | PYD ch. 3 **[recheck]** | n/a | vSphere VMs: accepted for the proof of concept (design.md §11) |
| V4 | Per node in a compact cluster: ≥16 cores, ≥64 GB RAM, 120 GB SSD root + 250 GB, on top of OCP control-plane needs; a 150 GB PV pool; a default RWO StorageClass | PYD ch. 3 **[recheck]** | discover: ESXi CPU/RAM/datastore free | capacity for 3 × (≥16 vCPU, ≥64 GB) + bootstrap + jump box |
| V5 | Operators: NMState, MetalLB, cert-manager; OVN-K `gatewayConfig.ipForwarding: Global` | PYD ch. 3, DEP ch. 3 **[recheck]** | after OCP install | — |

## Networks
| ID | Requirement | Source | Check | Expected |
|---|---|---|---|---|
| N1 | Isolated networks ctlplane, internalapi, storage, tenant (+ external for floating IPs); each OCP node attaches to them (NNCP + NAD), MetalLB L2 pools on ctlplane and internalapi | DEP ch. 3, PYD ch. 5 **[recheck]** | netcheck: L2 adjacency jump box ↔ data-plane hosts on every network | all pairs reachable |
| N2 | Compact clusters: ≥2 NICs per node, one for OpenShift, one for the OpenStack networks | PYD ch. 3 **[recheck]** | design: OCP VMs get a trunk vNIC + storage vNICs | — |
| N3 | ctlplane IP pre-configured on pre-provisioned nodes and matching NetConfig (fixedIP, VLAN if tagged); Ansible over SSH reaches it | DEP node set prerequisites **[recheck]** | netcheck: SSH port 22 on every host's ctlplane IP | open |
| N4 | ctlplane sharing the OCP machine network: no explicit statement either way; examples use a dedicated NIC/bridge. If shared, the NAD is macvlan on `br-ex`, the NNCP must not touch `br-ex`, ranges are carved out of the shared subnet | PYD ch. 3/5 **[recheck]**; OCP secondary networks (macvlan on br-ex) | netcheck: macvlan child with a foreign MAC on the jump box's primary NIC, reachable from the hosts; planned ranges free | reachable; no address in the ranges answers |
| N5 | NADs are macvlan (+ whereabouts): pods use extra MACs on the node NIC. On vSphere this needs the port group security policy (forged transmits, MAC changes; promiscuous or MAC learning) | DEP ch. 3 **[recheck]**; OCP 4.x multiple networks (macvlan vs cloud security policies) | netcheck: macvlan on each trunk VLAN reachable from the hosts | reachable |
| N6 | MTU consistent end to end; 1500 in examples, jumbo (≤9000) where switches allow, mainly storage and tenant | DEP NetConfig examples, *Deploying RHOSO at scale* **[recheck]** | netcheck: DF pings 1472 and 8972 bytes per network | 1500 everywhere; 9000 recorded per network |
| N7 | Storage: cinder-volume (and Glance on Cinder) run on OCP nodes and need every storage network; iscsid/multipathd on OCP nodes (MachineConfig, `master` pool in compact clusters) and computes | CPS ch. 1/2, PYD ch. 7 **[recheck]** | netcheck: TCP 3260 to every array portal from both fabrics, from the jump box and the hosts | each fabric reaches its own portals |
| N8 | Second iSCSI fabric = custom network (e.g. `storage2`) in NetConfig/NNCP/NAD/node set (no documented procedure found) | — (design decision) | as N7 | — |
| N9 | External / floating IPs through OVN gateways on the computes (`edpm_enable_chassis_gw`, `br-ex` + physnet `datacentre`); control-plane gateways would need a dedicated NIC | CNS ch. 3 **[recheck]** | netcheck: floating-IP range free | no answer |
| N10 | DNS for data-plane nodes from RHOSO dnsmasq (ctlplane VIP) with an upstream server reachable from the pods | DEP ch. 4 **[recheck]** | discover/netcheck: upstream DNS resolves internal and external names | resolves |
| N11 | Registry access: registry.redhat.io (computes, OCP), registry.connect.redhat.com (Pure cinder-volume image), quay.io / mirror.openshift.com (OCP install) | DEP node set; *Integrating partner content* **[recheck]** | netcheck: HTTPS from the jump box and hosts | reachable |
| N12 | Time sync on all nodes | DEP node set example **[recheck]** | netcheck: chronyd running on the hosts | running |

## Storage back end
| ID | Requirement | Source | Check |
|---|---|---|---|
| S1 | Pure cinder-volume certified image `registry.connect.redhat.com/purestorage/openstack-cinder-volume-pure-18-0`, tag matching the RHOSO release (catalog shows 18.0.22) | Red Hat catalog | after OCP install: image pull |
| S2 | Driver `cinder.volume.drivers.pure.PureISCSIDriver`, `san_ip` + `pure_api_token` in a Secret (`customServiceConfigSecrets`) | Pure Storage RHOSO 18 docs (not Red Hat) | — |
| S3 | Glance on Cinder: `cinder_use_multipath`, Glance pods on the storage network(s); Nova `volume_use_multipath = True` (custom nova service) | CPS **[recheck]** | — |
| S4 | One owner for `/etc/multipath.conf` on OCP nodes: merge Cinder's iscsid/multipathd needs into the existing PX-CSI `storage_node` MachineConfig | design decision | — |
