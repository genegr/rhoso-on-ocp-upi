---
name: rhoso-lab
description: End-to-end runbook for the whole lab - the OpenShift cluster (sibling repo ocp-upi-baremetal-vms), then RHOSO 18.0 on it, the bare-metal computes, verification, users and Tempest - in order, with every gate, timing and the skill that owns each step. The entry point for short or spoken (dictated) requests. Use whenever the user wants to deploy, rebuild, redeploy, resume or continue the lab, OpenShift plus OpenStack, "everything", "the whole thing", "from scratch", asks where the deployment stands or what comes next, or names a step without its playbook.
when_to_use: Spoken prompts such as "deploy the lab", "deploy OCP and RHOSO", "deploy OpenStack", "rebuild everything", "continue the deployment", "where are we", "what's next". Dictation may write RHOSO as "rose so", "row so", "R H O S O", "Red Hat OpenStack"; OCP as "O C P" or "OpenShift"; Tempest as "temp est"; EDPM as "E D P M" or "the computes".
---

# The whole lab, start to finish

Read both `CLAUDE.md` files first (this repo's and `../ocp-upi-baremetal-vms/CLAUDE.md`). Their hard rules apply to
every step. Each step below names the skill that owns it. When that skill isn't loaded (the sibling repo's skills load
only with `claude --add-dir`), read its `SKILL.md` from the path given and follow it the same way.

## 1. Pin down the target before anything runs
- **Env**: the only `envs/*.yaml` other than `env.example.yaml`. **Cluster**: its `ocp_cluster:`, which must exist as
  `../ocp-upi-baremetal-vms/clusters/<cluster>.yaml`. If there are several envs or clusters, ask which one; never guess.
- Say the target back in the first line of the reply, e.g. "Env X, OCP cluster Y: starting at step 4 (OCP storage)".
- **Where are we**: find the first unfinished step with read-only checks, never by rerunning phases blind.
  - Does the jump box answer (`ssh <SYNC_HOST> true`)?
  - Is the OCP cluster up? Use the `ocp-upi-status` skill.
  - Is RHOSO up? Use the `rhoso-status` skill.
  - What did the last runs say? Check the newest `.state/*.log` on the jump box.
  - Then state the plan in one line: which steps, roughly how long, and which steps will stop for a yes.

## 2. The steps
"Gate" = stop and get the user's explicit yes in a reply, after showing the `--check --diff` result. A voice prompt
that asked for the deployment is not that yes.

| # | Step | How (skill → playbook) | Time | Gate |
|---|------|------------------------|------|------|
| 1 | Jump box | `rhoso-jumpbox` (OVA + cloud-init, toolbox build, `tools/sync.sh` for both repos) | 30 min | vCenter |
| 2 | Discovery, host audit | `rhoso-discover` (read-only) | 5 min | — |
| 3 | Network validation | `rhoso-netcheck`: `netcheck_vsphere.yml`, then `netcheck.yml`. **Nothing is deployed until it passes** | 10 min | port groups |
| 4 | OpenShift cluster | `../ocp-upi-baremetal-vms/.claude/skills/ocp-upi-full/SKILL.md` (deploy, AD DNS, storage, operators, users) | 1.5–2 h | AD DNS, FlashArray |
| 5 | EDPM host prep | `rhoso-edpm-prep`: `edpm_ssh_key.yml`, `edpm_ctlplane.yml`, `edpm_prep.yml` (distro-sync + reboot) | 30 min | host networking |
| 6 | RHOSO operators, networks | `rhoso-deploy`: `rhoso.yml --tags operators`, then `--tags networks` | 15 min | — |
| 7 | Cinder array user | `rhoso-deploy`: `rhoso.yml --tags flasharray` | 1 min | FlashArray |
| 8 | Control plane | `rhoso-deploy`: `rhoso.yml --tags controlplane` (waits Ready, up to 1 h) | 30–60 min | — |
| 9 | Data plane | `rhoso-dataplane`: `rhoso.yml --tags dataplane`, first one host (`-e dataplane_limit=<host>`), then all | 1 h | host networking |
| 10 | Router | `rhoso-router`: `router.yml` (VyOS between the lab LAN and the external network) | 10 min | vSphere + jump box |
| 11 | Verification | `rhoso-verify`: `verify.yml` (PASS/FAIL report) | 15 min | — |
| 12 | Images, tenants | `rhoso-tenant`: `images.yml`, `tenant.yml`, `tenant.yml --tags check` | 15 min | — |
| 13 | Tempest | `rhoso-tempest`: smoke, then the full suite | smoke ~15 min, full ~6–10 h | — |

Steps 1–3 are needed only for a new jump box or new hosts or networks. A rebuild of an existing lab normally starts
at 4 (OpenShift from scratch) or 6 (RHOSO only). After a control-plane teardown (`rhoso-teardown`) it restarts at 8,
and step 9 needs a new `-e dataplane_run=<suffix>`.

## 3. How to run it
- Sync first (`bash tools/sync.sh` in each repo that changed), then every command through the toolbox on the jump box
  (prefix in `rhoso-jumpbox` / `ocp-upi-deploy`).
- Long steps (4, 8, 9, 13, OCP storage `nics`/`node`) run in the background, with output to `.state/<name>-<step>.log`.
  Then read the result with `grep -E "fatal|PLAY RECAP" -A8`.
- After every step: rerun it if the skill says so (the rerun must be `changed=0`), and give a one-line status:
  done, `changed`/`failed` counts, next step. Don't start the next gated step on your own.
- A failure: stop, read the log and the owning skill's gotchas and fix the cause. Rerun only that step. Never skip
  ahead.
- When done, run `rhoso-status` and report in a few plain sentences. Commit and push both repos only when the user
  asks (the authoring box can vanish, so offer it).

## 4. Words that are never enough on their own
"Clean up", "reset", "start over", "wipe", "redo", "from scratch": if the prompt could mean deleting a cluster, a
control plane, realm or volumes, say exactly what would be destroyed and ask. `destroy.yml`, `storage.yml --tags
teardown` and `rhoso_teardown.yml` need the user's explicit yes every time. Also ask when the dictated text is
garbled around a name, a host or a number.
