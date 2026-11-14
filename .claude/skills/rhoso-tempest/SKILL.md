---
name: rhoso-tempest
description: Run, rerun, retry or analyse Tempest against the deployed RHOSO 18.0 cloud through the test-operator (Tempest CRs) via playbooks/tempest.yml - smoke, then the full suite (Tempest + the plugins of the services in the catalog, undeployed services' plugins left out), with python-tempestconf discovery, a macvlan leg on the external network for the test pod, logs and totals in .state/<env>/tempest/. Use whenever the user wants Tempest, smoke tests, the full suite, a retry of only the failed tests, or asks why a Tempest test failed or whether Tempest finished.
when_to_use: Spoken prompts such as "run tempest", "run the smoke tests", "did tempest finish", "retry the failed tests". Dictation may write Tempest as "temp est" or "tempests".
---

# Tempest (`playbooks/tempest.yml`)

Prerequisites: `rhoso-verify` passed (it creates the external network `public`, the flavors and the image Tempest
uses), and the test-operator is present (installed with the openstack-operator).

```bash
ansible-playbook playbooks/tempest.yml -e env=<name>                          # every run in tempest_runs not done yet
ansible-playbook playbooks/tempest.yml -e env=<name> -e tempest_rerun=true    # delete the CRs, run them again
ansible-playbook playbooks/tempest.yml -e env=<name> -e tempest_retry=<run>   # only the tests that failed in <run>
```
Always run it in the background, with output to `.state/rhoso-tempest.log` on the jump box. Smoke takes about
15 minutes and the full suite 6–10 hours (concurrency 4). Then read the totals:
`grep -A40 "totals\]" .state/rhoso-tempest.log`. Each run's pod log is kept in `.state/<env>/tempest/<run>.log`.
Move old logs to `.state/<env>/tempest/run<N>/` before a rerun if they're worth keeping.

## How it is built (`roles/rhoso_tempest`)
- `tempest_runs`: `tempest-smoke`, then `tempest-full` with `include: auto`. `auto` means `tempest\.` plus every
  plugin in `tempest_plugins` whose service type is in the catalog (`openstack service list`). The plugins left out
  are printed with the totals.
- `tempest_exclude`: tests that fail because of the design, not a fault. Each has a comment saying why.
- `tempest_deployer_input` (INI, values may hold spaces): `volume.vendor_name = Pure Storage`, iSCSI.
- `tempest_overrides` (space-separated, so no spaces in values):
  - live migration on;
  - `can_migrate_between_any_hosts false`, because of the CPU groups;
  - `service_available.load_balancer false`.
- The end of a run is the pod phase (label `instanceName=<run>`) reaching `Succeeded` or `Failed`, not the CR. A
  run with failures leaves the CR reading "NetworkAttachments error".
- A finished run is left as it is. A second run of the playbook only collects its log again.

## Analysing failures
Look at the `... FAILED` lines and the traceback for each. Then group the failures by cause before proposing fixes:
- something in the environment (quota, a deleted shared image, a concurrent admin action);
- a missing feature flag (fix with an override or the deployer input);
- a real fault (find it in the service logs: `oc -n openstack logs <pod>`, or on a compute
  `podman logs nova_compute`).

Things found so far:
- Glance image downloads failing with HTTP 500 "attaching": the Glance image volumes must use the multiattach type
  (`glance_volume_type` in `rhoso_controlplane`).
- Rebuild tests failing: someone deleted `cirros-..._alt` in Horizon during the run.
- Live block migration failing with "missing features": Intel and AMD hosts were in one CPU group (`cpu_groups`).
- Octavia setUpClass failing: Octavia isn't deployed, so `load_balancer false`.

Leftovers of a killed run show up in `openstack server list --all-projects` and `image list` as `tempest-*` objects.
Delete them, and keep the base objects `verify.yml` made.
