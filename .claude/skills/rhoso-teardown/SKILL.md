---
name: rhoso-teardown
description: Remove the RHOSO 18.0 control plane and its persistent volumes via playbooks/rhoso_teardown.yml (irreversible - every OpenStack database, message queue and OVN database is lost), keeping the operators, networks, secrets, OpenStackVersion, the node set and the bare-metal hosts, then the path back (controlplane, then dataplane with a new run suffix). Use whenever the user wants to delete, tear down, wipe, reset or start over with OpenStack/RHOSO, or a rebuild needs fresh databases. For the OpenShift cluster itself use the OCP repo's ocp-upi-teardown.
when_to_use: Spoken prompts such as "tear down OpenStack", "wipe RHOSO", "start the control plane over". Treat "reset", "clean up" and "redo" as possibly destructive and ask.
---

# Tear down the RHOSO control plane

**Irreversible. It needs the user's explicit yes every time, in a reply to the plan.** A spoken "redeploy" or
"start over" isn't that yes.

1. Pin down the target: the env (`envs/<env>.yaml`) and its `ocp_cluster`. Say both back.
2. Show the plan: `ansible-playbook playbooks/rhoso_teardown.yml -e env=<name> --check`. It prints what it would
   delete and deletes nothing.
3. Tell the user, in plain words:
   - Lost: every instance, volume, image, network, project and user in OpenStack.
   - Kept: the operators, the networks (NNCP, NAD, MetalLB, NetConfig), `osp-secret` and the other secrets,
     OpenStackVersion, the node set, the hosts and the FlashArray user.
   - The Cinder volumes on the array aren't deleted by Cinder. Volumes left in the array pod or realm need a separate
     decision.
4. Only after the yes, run with `-e confirm=<env>` in the background (`.state/rhoso-teardown.log`).
5. The way back:
   - `rhoso.yml --tags controlplane`;
   - `rhoso.yml --tags dataplane -e dataplane_run=<new suffix>` (the computes are deployed and registered again);
   - then `verify.yml`, `images.yml` and `tenant.yml` (new passwords aren't generated: the files in `.state` stay).

The OpenShift cluster: `../ocp-upi-baremetal-vms` skill `ocp-upi-teardown` (`destroy.yml`), with its own consent.
Tearing down the cluster also takes RHOSO with it. Its storage realm or pod (`storage.yml --tags teardown`) needs a
separate yes.
