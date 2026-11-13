# rhoso-on-ocp-upi

Red Hat OpenStack Services on OpenShift 18.0 on top of a compact OpenShift cluster built with
[ocp-upi-baremetal-vms](../ocp-upi-baremetal-vms), with pre-provisioned RHEL 9 bare-metal compute nodes.

## Flow
1. **Jump box**: Ubuntu 26.04 VM from the Canonical OVA with Docker ([jumpbox/README.md](jumpbox/README.md)).
2. **Discovery** (read-only): vSphere, AD DNS, bare-metal hosts.
3. **Network validation**: temporary Linux VLAN interfaces on the jump box and the bare-metal hosts prove the
   layout meets [docs/network-requirements.md](docs/network-requirements.md). This is a gate: nothing is deployed before it passes.
4. **Design sign-off**: [docs/design.md](docs/design.md).
5. **OpenShift**: compact cluster with the OCP repo, DNS in Active Directory, PX-CSI storage.
6. **RHOSO**: operators, networks, control plane, data plane (`playbooks/rhoso.yml`), then functional
   verification (`playbooks/verify.yml`: external network, image, flavors, one instance per compute with floating
   IPs, Pure volumes with multipath, live migration; report in `.state/<env>/verify-report.md`). Tempest comes after.

Access to Horizon and the `openstack` CLI: [docs/access.md](docs/access.md).

## Configuration
`envs/<env>.yaml` (see [envs/env.example.yaml](envs/env.example.yaml)) and `envs/vault.yml`
(see [envs/vault.yml.example](envs/vault.yml.example)), both gitignored.
