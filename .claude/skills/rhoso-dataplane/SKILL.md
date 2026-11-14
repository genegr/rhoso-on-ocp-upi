---
name: rhoso-dataplane
description: Deploy, extend or re-run the RHOSO 18.0 data plane on the pre-provisioned bare-metal compute hosts via playbooks/rhoso.yml --tags dataplane - data-plane secrets (Ansible SSH key, Nova migration key, libvirt, registry login), Pure multipath.conf and udev rules, Nova volume_use_multipath, the OpenStackDataPlaneNodeSet (os-net-config bond/br-ex/VLANs/iSCSI NICs), one-shot OpenStackDataPlaneDeployments (edpm-all, or edpm-<host> with dataplane_limit) and the nova-manage cell_v2 discover_hosts mapping. Use whenever the user wants to deploy compute nodes, add or redeploy a compute host, rerun a failed deployment, change the node set (networks, bond options, NTP, services), or asks why a compute isn't in nova or a deployment failed.
---

# RHOSO data plane

Prerequisites: control plane Ready (`rhoso-deploy`) and the hosts prepared (`rhoso-edpm-prep`: toolbox key for root,
ctlplane VLAN up, release lock/repos, distro-sync done). Toolbox prefix in `rhoso-jumpbox`.

```bash
ansible-playbook playbooks/rhoso.yml -e env=<name> --tags dataplane --check --diff
ansible-playbook playbooks/rhoso.yml -e env=<name> --tags dataplane -e dataplane_limit=<host>   # one host first
ansible-playbook playbooks/rhoso.yml -e env=<name> --tags dataplane                              # edpm-all
```
**It rewrites the hosts' networking** (os-net-config replaces the bond and the temporary ctlplane connection): first
real run on one host with `dataplane_limit`, with the user's go-ahead. Runs take long (up to 1 h): background with
`.state/rhoso-dataplane-<suffix>.log`.

## What it does
1. Secrets: `dataplane-ansible-ssh-private-key-secret` (toolbox key, trailing newline kept: OpenSSH rejects a key
   without it), `nova-migration-ssh-key` (generated once in `.state/<env>/dataplane/`), `libvirt-secret`,
   `redhat-registry` (registry.redhat.io login taken from the cluster pull secret).
2. ConfigMaps `edpm-multipath` (`multipath.conf.j2`, mounted for `edpm_multipathd`) and `nova-extra-config`
   (`volume_use_multipath = True`, picked up by the default nova service). Custom service `pure-storage-udev` (the Pure
   udev rules the OCP nodes use).
3. Node set `rhoso.dataplane.nodeset`, or with `rhoso.dataplane.cpu_groups` one node set per CPU group (hosts by
   model; ConfigMap `nova-cpu-<node set>` with `cpu_mode = custom` + `cpu_models`, service `nova-<node set>` = the
   live `nova` service plus that ConfigMap). Existing node sets are applied first: a host moving out is removed by JSON
   patch (merge apply keeps map keys), and the new node set waits for the host's IPSet to be released. Under `--check`
   a new node set whose hosts are still elsewhere is only announced (the webhook would say "already exists in another
   cluster"). The deployment covers all node sets (`ssh-known-hosts` runs across them, keeping cold migration between
   groups). Each node set is rendered to `.state/<env>/dataplane/nodeset-<name>.yaml`: management address and
   default route on `br-ex` over `bond0` (members from `rhoso.dataplane.models[<model>].bond_nics`), ctlplane/
   internalapi/tenant as VLANs on `br-ex`, `storage`/`storage2` on the host's `iscsi_nics`, fixed IPs =
   `<subnet>.<host number>`, `edpm_enable_chassis_gw` (floating IPs through the computes).
4. Deployment `edpm-<dataplane_limit|all>[-<dataplane_run>]` with `ansibleLimit`, waits for Ready, then
   `nova-manage cell_v2 discover_hosts` in `nova-cell0-conductor-0` (periodic discovery is off in RHOSO).

## Rules and gotchas
- A deployment is one-shot: a finished one (Ready or failed) is left as it is. To run again, pass
  `-e dataplane_run=<suffix>` for a new name. `-e dataplane_deploy=false` applies only the node set, to review the
  generated inventory. After a Nova config change, run only the Nova service, one node set per deployment
  (`servicesOverride` applies to every node set of a deployment):
  `-e dataplane_run=<suffix>-<node set> -e dataplane_nodesets=<node set> -e dataplane_services=nova-<node set>`.
- CPU groups set `skip_cpu_compare_on_dest = false` (RHOSO's 01-nova.conf sets it true for host-model, nova bug
  2039803): the destination pre-check then refuses a host of the other group and the conductor tries the next one.
- The operator webhook refuses any node-set patch while one of its deployments runs: the play then skips the node set
  and says so. Wait, then rerun.
- `Ready`/`InputReady` read Error for a while when cert-manager is still issuing per-node TLS certs; only
  `DeploymentReady` reason Error / BackoffLimitExceeded is a real failure.
- Failed deployment: `oc -n openstack get openstackdataplanedeployment <name> -o yaml`, then the failing job's pod log
  (`oc -n openstack get pods -l openstackdataplanedeployment=<name>`); the service name in the pod tells which step.
- New host: `edpm_hosts` + the `rhoso-discover`, `rhoso-netcheck` and `rhoso-edpm-prep` flows, then
  `-e dataplane_limit=<host>`. Afterwards `openstack compute service list` and `hypervisor list` show it
  (`rhoso-status`).
