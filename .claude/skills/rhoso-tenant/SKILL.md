---
name: rhoso-tenant
description: Give users access to the RHOSO 18.0 cloud - public Glance images from envs/<env>.yaml images (downloaded once, checksum verified, stored on Pure through Glance on Cinder; playbooks/images.yml) and tenant onboarding (projects, member users with generated passwords, quotas, optional starter network with a router to the external network and SSH/ICMP rules; playbooks/tenant.yml, --tags check for the tenant user's view). Use whenever the user wants a new project or user, an image (Ubuntu, RHEL, CirrOS) uploaded, quotas changed, a tenant's network, or to check what a tenant user can do.
when_to_use: Spoken prompts such as "add a tenant", "create a project for <name>", "upload the Ubuntu image", "check the demo user".
---

# Images and tenants

```bash
ansible-playbook playbooks/images.yml -e env=<name>
ansible-playbook playbooks/tenant.yml -e env=<name> [-e tenant=<name>]
ansible-playbook playbooks/tenant.yml -e env=<name> [-e tenant=<name>] --tags check
```
- **Images**: `images:` in the env file. Each entry has `{name, url, checksum: sha256:<hex>, min_disk, min_ram,
  properties}`. Pin a release by its `SHA256SUMS` (a dated release, at least two weeks old; ask the user about a newer
  one). Each image is downloaded once into `.state/<env>/images`, copied into the `openstackclient` pod, created if
  missing, then removed from the pod. Big images take minutes, because Glance writes them to a Cinder volume.
- **Tenants**: `tenants:` in the env file. Each user's password is generated once into
  `.state/<env>/tenants/<user>.password`. It never goes into chat or git, and the user hands it out out of band. The
  user names and the projects are the user's to choose: never invent them.
- The starter network uses Neutron's default DNS (the AD DC, through the router's masquerade) and tenant MTU 1500.
- `--tags check` logs in as the tenant user and confirms:
  - admin calls are refused;
  - an instance gets a floating IP and can be reached through the router;
  - DNS and the internet work inside the instance;
  - a volume can be created and attached.

  Its objects are removed afterwards.
- `tenant.yml` has no dry run, because `k8s_exec` ignores `--check`, and it refuses one. Read the env file's
  `tenants:` back to the user before a first run.
- Access for people (Horizon URL, CLI): `docs/access.md`.
