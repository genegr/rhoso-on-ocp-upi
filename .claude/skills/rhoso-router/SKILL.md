---
name: rhoso-router
description: Deploy or change the VyOS router VM between the lab LAN and the RHOSO external (floating IP) network via playbooks/router.yml - created once from the OVA the vyos-vsphere-image repo builds (cloud-init seed at first boot), then configured only with vyos.vyos modules - source NAT for the instances except toward the allowed sources, a forward filter that lets only the allowed sources open connections to floating IPs, SSH to the router from the allowed sources only, and the static route on the jump box. Use whenever the user wants floating IPs reachable from the lab, instances to reach DNS or the internet, the router rebuilt, or asks why a floating IP doesn't answer from a lab machine.
when_to_use: Spoken prompts such as "deploy the router", "the floating IPs don't answer", "instances have no internet". Dictation may write VyOS as "vi OS" or "vios".
---

# VyOS router (`playbooks/router.yml`)

```bash
ansible-playbook playbooks/router.yml -e env=<name> --check --diff    # then the user's go-ahead
ansible-playbook playbooks/router.yml -e env=<name>
```
- It changes vSphere (a new VM) and the jump box (a systemd-networkd route drop-in). **Gate**: `--check --diff`
  first, then the user's explicit yes.
- The OVA comes from the sibling repo `../vyos-vsphere-image` (built on the jump box, `.state/out/`). If it's
  missing, build it there first.
- Interfaces:
  - `eth0` = `router.mgmt` on the lab LAN, whose default route is the LAN gateway;
  - `eth1` = `rhoso.verify.external.gateway`.
- The cloud-init seed applies only at the first boot. After that `vyos_config` owns the configuration, and a second
  run reports `changed=0`.
- Every machine in `router.allowed_sources` that needs to reach the instances must have its own static route for
  `networks.external` via `router.mgmt.ip`. This playbook adds that route on the jump box only. Each other lab
  machine's owner adds it there.
- Floating IP unreachable:
  1. Check the route on the client.
  2. Check `show nat source rules` and `show firewall` on the router (through `vyos.vyos.vyos_command`).
  3. Check the instance's security group.
  4. Check the router gateway's chassis (`rhoso-verify` `gateway` INFO). Gateways sit only on the computes.
