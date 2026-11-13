---
name: rhoso-status
description: Read-only health check of the RHOSO 18.0 deployment and the OpenShift cluster under it - OCP nodes, ClusterVersion and cluster operators, the RHOSO operators, OpenStackControlPlane / OpenStackVersion / node set / deployments status, and from the openstackclient pod the compute, volume and network agent services, hypervisors and volume types. Use whenever the user asks whether OpenStack/RHOSO is up or healthy, what was deployed, which computes are in nova, wants a sanity check before or after a change, or reports any OpenStack problem that needs first-line triage, even if they just say "the lab" or "openstack".
---

# RHOSO status (read-only)

There is no status playbook yet: use `oc` from the OCP repo's toolbox, which has the kubeconfig and the pinned `oc`.
Nothing here changes anything.

```bash
ssh <SYNC_HOST> 'cd ocp-upi && docker compose run --rm -T \
  -e KUBECONFIG=/work/.state/clusters/<ocp_cluster>/install/auth/kubeconfig \
  -e PATH=/work/.state/bin/<ocp version>:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin \
  toolbox bash -c "<commands>"'
```
(`<ocp version>` = `.state/clusters/<ocp_cluster>/ocp-version`.) For the OCP layers alone (DNS, HAProxy, VMs, CSRs)
use the `ocp-upi-status` skill.

## Checks, in order
1. OpenShift: `oc get nodes`, `oc get clusterversion`, `oc get co` (any not Available or Degraded),
   `oc get csv -A | grep -Ev Succeeded`.
2. RHOSO CRs: `oc -n openstack get openstackcontrolplane,openstackversion,openstackdataplanenodeset,openstackdataplanedeployment`.
   Expect control plane "Setup complete", target = deployed version, node set "NodeSet Ready".
3. Networks: `oc get nncp` (all Available), `oc -n openstack get net-attach-def`,
   `oc -n metallb-system get ipaddresspool,l2advertisement`.
4. OpenStack (`oc -n openstack exec openstackclient -- openstack …`): `compute service list` (every compute
   enabled/up), `hypervisor list`, `network agent list` (OVN controller gateway agents on masters and computes, metadata
   agents on computes, all alive), `volume service list` (`cinder-volume …@pure` up), `volume type list` (`pure`).
5. Pods not Running/Completed: `oc -n openstack get pods | grep -Ev "Running|Completed"`.

Report in plain words: usable or not, then only what's wrong and what it means.

## Reading the results
- A compute missing from `compute service list` but its deployment Ready: cell mapping not done, rerun the
  `dataplane` phase (it runs `discover_hosts`) or check `nova-cell0-conductor-0` logs.
- A compute `down`: SSH to its **ctlplane** address from the rhoso toolbox (`ssh -i .state/ssh/id_ed25519
  root@<ctlplane ip>`; sshd only allows `rhoso.dataplane.sshd_allowed_ranges`, so the management IP may not answer)
  and check `systemctl list-units 'edpm_*'` (nova_compute, ovn_controller containers), time sync, the ctlplane VLAN.
- `cinder-volume` down: the `cinder-volume-pure-secret` token (`flasharray` phase), the storage network NAD, and the
  array portals from the pod's node.
- Control plane not Ready: `rhoso-deploy` skill, "Not Ready".
- End-to-end functional verification (image upload to Glance on Cinder, volume create/attach with multipath, an
  instance with a floating IP, live migration) is the deployment's last phase and isn't automated yet.
