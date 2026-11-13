#!/usr/bin/python
# -*- coding: utf-8 -*-
# Set only the security policy (promiscuous / forged transmits / MAC changes) of an existing distributed port group.
#
# Why a module: community.vmware.vmware_dvs_portgroup rebuilds the whole port group config from its own arguments
# (teaming policy, failure criteria, port policies, inherited flags) on every update, so on a port group made in the
# vSphere UI it would also reset settings it doesn't model (e.g. a non-inherited beacon-probing failure criterion).
# This module sends a DVPortgroupConfigSpec that carries only defaultPortConfig.macManagementPolicy; everything that
# is unset in the spec stays as it is.

DOCUMENTATION = r'''
module: vmware_dvpg_security
short_description: Set only the security policy of an existing distributed port group
options:
  switch: {description: Distributed switch name, required: true, type: str}
  portgroup: {description: Port group name, required: true, type: str}
  promiscuous: {description: Allow promiscuous mode, required: true, type: bool}
  forged_transmits: {description: Allow forged transmits, required: true, type: bool}
  mac_changes: {description: Allow MAC address changes, required: true, type: bool}
extends_documentation_fragment: [community.vmware.vmware.documentation]
'''

from ansible.module_utils.basic import AnsibleModule

try:
    from pyVmomi import vim
except ImportError:
    pass

from ansible_collections.community.vmware.plugins.module_utils.vmware import (
    PyVmomi, find_dvs_by_name, find_dvspg_by_name, vmware_argument_spec, wait_for_task)


def current_policy(pg):
    mm = pg.config.defaultPortConfig.macManagementPolicy
    return {'inherited': bool(mm.inherited), 'promiscuous': bool(mm.allowPromiscuous),
            'forged_transmits': bool(mm.forgedTransmits), 'mac_changes': bool(mm.macChanges)}


def main():
    spec = vmware_argument_spec()
    spec.update(switch=dict(type='str', required=True), portgroup=dict(type='str', required=True),
                promiscuous=dict(type='bool', required=True), forged_transmits=dict(type='bool', required=True),
                mac_changes=dict(type='bool', required=True))
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    p = module.params
    pv = PyVmomi(module)

    dvs = find_dvs_by_name(pv.content, p['switch'])
    if dvs is None:
        module.fail_json(msg="distributed switch %s not found" % p['switch'])
    pg = find_dvspg_by_name(dvs, p['portgroup'])
    if pg is None:
        module.fail_json(msg="port group %s not found on %s (this module never creates one)" % (p['portgroup'], p['switch']))

    before = current_policy(pg)
    after = {'inherited': False, 'promiscuous': p['promiscuous'], 'forged_transmits': p['forged_transmits'],
             'mac_changes': p['mac_changes']}
    changed = before != after
    result = dict(changed=changed, diff={'before': before, 'after': after})

    if changed and not module.check_mode:
        mm = vim.dvs.VmwareDistributedVirtualSwitch.MacManagementPolicy()
        mm.inherited = False
        mm.allowPromiscuous = p['promiscuous']
        mm.forgedTransmits = p['forged_transmits']
        mm.macChanges = p['mac_changes']
        port = vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy()
        port.macManagementPolicy = mm
        cfg = vim.dvs.DistributedVirtualPortgroup.ConfigSpec()
        cfg.configVersion = pg.config.configVersion
        cfg.defaultPortConfig = port
        try:
            wait_for_task(pg.ReconfigureDVPortgroup_Task(cfg))
        except Exception as exc:  # report the vSphere fault as is
            module.fail_json(msg="reconfigure of %s failed: %s" % (p['portgroup'], exc), **result)
        result['diff']['after'] = current_policy(find_dvspg_by_name(dvs, p['portgroup']))

    module.exit_json(**result)


if __name__ == '__main__':
    main()
