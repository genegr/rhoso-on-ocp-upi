# Accessing the OpenStack cloud

How to reach the RHOSO 18.0 cloud of an environment: the Horizon dashboard and the `openstack` CLI.
Placeholders: `<ocp_cluster>` and `<domain>` come from `envs/<env>.yaml` (`domain` = `<cluster>.<base domain>`),
`<AD DC>` = `ad.server`, `<ingress VIP>` = the second `jumpbox.extra_ips` entry (HAProxy for `*.apps`).

## 1. Name resolution
Every public endpoint is an OpenShift route `<service>-openstack.apps.<domain>` on the ingress VIP, and only the AD DC
serves the cluster zone. A machine whose DNS servers don't forward that zone can't resolve them. Check with:

```powershell
Resolve-DnsName horizon-openstack.apps.<domain>                    # through this machine's DNS servers
Resolve-DnsName horizon-openstack.apps.<domain> -Server <AD DC>    # straight from the DC
```

If only the second answers, choose one fix:
- **Windows, preferred**: a Name Resolution Policy Table rule that sends just that zone to the DC (elevated
  PowerShell). Nothing else about the machine's DNS changes:
  ```powershell
  Add-DnsClientNrptRule -Namespace ".<domain>" -NameServers "<AD DC>"
  Clear-DnsClientCache
  # remove later: Get-DnsClientNrptRule | Where-Object Namespace -eq ".<domain>" | Remove-DnsClientNrptRule -Force
  ```
- **Any OS**: hosts-file entries, all pointing to `<ingress VIP>`. You need at least `horizon`, `keystone-public`, and
  for the CLI every service in the catalog: `oc -n openstack get routes` lists the names
  (`C:\Windows\System32\drivers\etc\hosts`, `/etc/hosts`).
- **Ask the network/AD team** for a conditional forwarder for `<domain>` to `<AD DC>` on the site DNS servers.

TCP 443 to `<ingress VIP>` must also be reachable (`Test-NetConnection <ingress VIP> -Port 443`).

## 2. Credentials
- User `admin`, domain `Default`, project `admin`.
- Password: key `AdminPassword` of the `osp-secret` Secret. It was generated once by the `controlplane` phase and is
  kept on the jump box in `~/rhoso/.state/<env>/osp-secret/AdminPassword`. From the OCP toolbox:
  ```bash
  oc -n openstack get secret osp-secret -o jsonpath='{.data.AdminPassword}' | base64 -d; echo
  ```
- `osp-secret` owns this password: **don't change it in Horizon or with `openstack user set`**, or the secret and
  Keystone stop matching. To choose it, set `vault_rhoso_admin_password` in `envs/vault.yml` and run
  `rhoso.yml --tags controlplane`. For people, create users and projects of your own (Identity → Users / Projects),
  or tenants with `tenant.yml` (standard password: `vault_tenant_password`).

## 3. TLS certificate (once per machine)
The public endpoints use certificates from RHOSO's own CA (`rootca-public`), not a public one, so browsers and the
CLI warn until that CA is trusted. Export it from the OCP toolbox:
```bash
oc -n openstack get secret rootca-public -o jsonpath='{.data.ca\.crt}' | base64 -d > rhoso-public-ca.crt
```
Copy it to the machine and trust it:
- Windows (current user, no admin needed): `Import-Certificate -FilePath .\rhoso-public-ca.crt -CertStoreLocation Cert:\CurrentUser\Root`
- RHEL/Fedora: copy to `/etc/pki/ca-trust/source/anchors/`, `update-ca-trust`. Ubuntu: `/usr/local/share/ca-certificates/` (`.crt`), `update-ca-certificates`.
- Firefox keeps its own store: Settings → Privacy & Security → Certificates → Import.

The CA is valid for 5 years from the deployment; if the control plane is ever rebuilt, export it again.

## 4. Horizon
Open `https://horizon-openstack.apps.<domain>/dashboard`, domain `Default`, user `admin`, the password from step 2.
Instance consoles (Compute → Instances → Console) are served by `nova-novncproxy-cell1-public-openstack.apps.<domain>`,
so that name must resolve too.

## 5. The `openstack` CLI

### a. In the cluster: the `openstackclient` pod (nothing to install)
The control plane runs a pod with the CLI already configured (`OS_CLOUD=default`, admin credentials, CA trusted, the
internal network path). From the OCP toolbox on the jump box (see the `rhoso-status` skill for the prefix):
```bash
oc -n openstack rsh openstackclient                                   # interactive shell, then: openstack server list
oc -n openstack exec -t openstackclient -- openstack compute service list   # one command
oc -n openstack cp ./image.qcow2 openstackclient:/home/cloud-admin/image.qcow2   # files for image create etc.
```
Files copied into the pod are lost when the pod is recreated; keep the originals elsewhere.

### b. From your own machine
Needs Python 3, steps 1 and 3, and the public endpoints only.
```bash
python3 -m venv ~/osc && . ~/osc/bin/activate            # Windows: py -m venv osc; .\osc\Scripts\Activate.ps1
pip install python-openstackclient==6.2.1                # the version in the openstackclient pod
```
`~/.config/openstack/clouds.yaml` (Windows: `%USERPROFILE%\.config\openstack\clouds.yaml`):
```yaml
clouds:
  rhoso:
    auth:
      auth_url: https://keystone-public-openstack.apps.<domain>
      username: admin
      project_name: admin
      user_domain_name: Default
      project_domain_name: Default
    region_name: regionOne
    interface: public
    identity_api_version: 3
    cacert: /path/to/rhoso-public-ca.crt
```
Keep the password out of that file: put it in `secure.yaml` next to it (same layout, only `auth.password`, file
readable by you only), or let the CLI ask for it. Then:
```bash
export OS_CLOUD=rhoso          # PowerShell: $env:OS_CLOUD = "rhoso"
openstack token issue
openstack catalog list
```

## 6. Reaching the instances (floating IPs)
Floating IPs live on the external network (`networks.external`), behind the VyOS router (`playbooks/router.yml`).
The router lets only `router.allowed_sources` (the lab LAN) open connections to the instances, and hides the
instances behind its own address for everything else (internet access). Your machine needs **its own static route**
for the external network via the router's lab address (`router.mgmt.ip`); nobody adds it for you, except on the jump
box:
- Linux: `ip route add <external cidr> via <router.mgmt.ip>`, made permanent in netplan (`routes:`) or NetworkManager
  (`nmcli connection modify <conn> +ipv4.routes "<external cidr> <router.mgmt.ip>"`).
- Windows (elevated): `route -p add <external network> mask <netmask> <router.mgmt.ip>`.

Then `ssh <user>@<floating IP>` works directly (security groups permitting). The instances see your real address.

## Troubleshooting
| Symptom | Cause |
|---|---|
| `DNS name does not exist` / `Name or service not known` | step 1 |
| Browser: "not secure"; CLI: `SSL: CERTIFICATE_VERIFY_FAILED` | step 3, or `cacert:` path wrong |
| CLI hangs on an `*.openstack.svc` URL | `interface: public` missing: internal endpoints only work inside the cluster |
| Horizon login "Invalid credentials" | wrong domain (`Default`) or a stale password copied before a rebuild |
| Horizon 503 / route not answering | `oc -n openstack get pods \| grep horizon`, then the `rhoso-status` skill |
