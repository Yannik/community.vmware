#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2017, Dag Wieers (@dagwieers) <dag@wieers.com>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
---
module: vsphere_file
short_description: Manage files on a vCenter datastore
description:
- Manage files on a vCenter datastore.
author:
- Dag Wieers (@dagwieers)
options:
  host:
    description:
    - The vCenter server on which the datastore is available.
    type: str
    required: true
    aliases: [ hostname ]
  username:
    description:
    - The user name to authenticate on the vCenter server.
    type: str
    required: true
  password:
    description:
    - The password to authenticate on the vCenter server.
    type: str
    required: true
  datacenter:
    description:
    - The datacenter on the vCenter server that holds the datastore.
    type: str
    required: true
  datastore:
    description:
    - The datastore on the vCenter server to push files to.
    type: str
    required: true
  path:
    description:
    - The file or directory on the datastore on the vCenter server.
    type: str
    required: true
    aliases: [ dest ]
  validate_certs:
    description:
    - If C(false), SSL certificates will not be validated. This should only be
      set to C(false) when no other option exists.
    type: bool
    default: true
  timeout:
    description:
    - The timeout in seconds for the upload to the datastore.
    type: int
    default: 10
  state:
    description:
    - The state of or the action on the provided path.
    - If C(absent), the file will be removed.
    - If C(directory), the directory will be created.
    - If C(file), more information of the (existing) file will be returned.
    - If C(touch), an empty file will be created if the path does not exist.
    type: str
    choices: [ absent, directory, file, touch ]
    default: file
notes:
- The vSphere folder API does not allow to remove directory objects.
'''

EXAMPLES = r'''
- name: Create an empty file on a datastore
  community.vmware.vsphere_file:
    host: '{{ vhost }}'
    username: '{{ vuser }}'
    password: '{{ vpass }}'
    datacenter: DC1 Someplace
    datastore: datastore1
    path: some/remote/file
    state: touch
  delegate_to: localhost

- name: Create a directory on a datastore
  community.vmware.vsphere_file:
    host: '{{ vhost }}'
    username: '{{ vuser }}'
    password: '{{ vpass }}'
    datacenter: DC2 Someplace
    datastore: datastore2
    path: other/remote/file
    state: directory
  delegate_to: localhost

- name: Query a file on a datastore
  community.vmware.vsphere_file:
    host: '{{ vhost }}'
    username: '{{ vuser }}'
    password: '{{ vpass }}'
    datacenter: DC1 Someplace
    datastore: datastore1
    path: some/remote/file
    state: file
  delegate_to: localhost
  ignore_errors: true

- name: Delete a file on a datastore
  community.vmware.vsphere_file:
    host: '{{ vhost }}'
    username: '{{ vuser }}'
    password: '{{ vpass }}'
    datacenter: DC2 Someplace
    datastore: datastore2
    path: other/remote/file
    state: absent
  delegate_to: localhost
'''

RETURN = r'''
'''

import socket
import sys

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.six import PY2
from ansible.module_utils.six.moves.urllib.error import HTTPError
from ansible.module_utils.six.moves.urllib.parse import quote, urlencode
from ansible.module_utils.urls import open_url
from ansible.module_utils._text import to_native

#from pyVim.task import WaitForTask

from ansible_collections.community.vmware.plugins.module_utils.vmware import (
    PyVmomi,
    find_datacenter_by_name,
    vmware_argument_spec,
    wait_for_task)


def vmware_path(datastore, datacenter, path):
    ''' Constructs a URL path that VSphere accepts reliably '''
    path = '/folder/{path}'.format(path=quote(path.strip('/')))
    # Due to a software bug in vSphere, it fails to handle ampersand in datacenter names
    # The solution is to do what vSphere does (when browsing) and double-encode ampersands, maybe others ?
    datacenter = datacenter.replace('&', '%26')
    if not path.startswith('/'):
        path = '/' + path
    params = dict(dsName=datastore)
    if datacenter:
        params['dcPath'] = datacenter
    return '{0}?{1}'.format(path, urlencode(params))

def vmware_path2(datastore, path):
    return '[{datastore}] {path}'.format(datastore=datastore,path=quote(path.strip('/')))

class VMwareDatastore(PyVmomi):
    def __init__(self, module):
        super(VMwareDatastore, self).__init__(module)
        self.datacenter_name = module.params['datacenter']
        self.datastore_name = module.params['datastore']
        self.datacenter = find_datacenter_by_name(self.content, self.datacenter_name)

    def delete_file(self, path):
        wait_for_task(self.content.fileManager.DeleteFile(vmware_path2(self.datastore_name, path), self.datacenter))

    def create_directory(self, path):
        wait_for_task(self.content.fileManager.MakeDirectory(vmware_path2(self.datastore_name, path), self.datacenter, True))


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(type='str', required=True, aliases=['hostname']),
            username=dict(type='str', required=True),
            password=dict(type='str', required=True, no_log=True),
            datacenter=dict(type='str', required=True),
            datastore=dict(type='str', required=True),
            path=dict(type='str', required=True, aliases=['dest']),
            state=dict(type='str', default='file', choices=['absent', 'directory', 'file', 'touch']),
            timeout=dict(type='int', default=10),
            validate_certs=dict(type='bool', default=True),
        ),
        supports_check_mode=True,
    )

    host = module.params.get('host')
    username = module.params.get('username')
    password = module.params.get('password')
    datacenter = module.params.get('datacenter')
    datastore = module.params.get('datastore')
    path = module.params.get('path')
    validate_certs = module.params.get('validate_certs')
    timeout = module.params.get('timeout')
    state = module.params.get('state')

    remote_path = vmware_path(datastore, datacenter, path)
    url = 'https://%s%s' % (host, remote_path)

    result = dict(
        path=path,
        size=None,
        state=state,
        status=None,
        url=url,
    )

    vmware_datastore = VMwareDatastore(module)

    # Check if the file/directory exists
    try:
        r = open_url(url, method='HEAD', timeout=timeout,
                     url_username=username, url_password=password,
                     validate_certs=validate_certs, force_basic_auth=True)
    except HTTPError as e:
        r = e
    except socket.error as e:
        module.fail_json(msg=to_native(e), errno=e[0], reason=to_native(e), **result)
    except Exception as e:
        module.fail_json(msg=to_native(e), errno=dir(e), reason=to_native(e), **result)

    if PY2:
        sys.exc_clear()  # Avoid false positive traceback in fail_json() on Python 2

    status = r.getcode()
    if status == 200:
        exists = True
        result['size'] = int(r.headers.get('content-length', None))
    elif status == 404:
        exists = False
    else:
        result['reason'] = r.msg
        result['status'] = status
        module.fail_json(msg="Failed to query for file '%s'" % path, errno=None, headers=dict(r.headers), **result)

    if state == 'absent':
        if not exists:
            module.exit_json(changed=False, **result)

        if not module.check_mode:
            try:
                vmware_datastore.delete_file(path)
            except Exception as e:
                module.fail_json(msg=to_native(e), errno=e[0], reason=to_native(e), **result)

        module.exit_json(changed=True, **result)

    elif state == 'directory':
        if exists:
            module.exit_json(changed=False, **result)

        if not module.check_mode:
            try:
                vmware_datastore.create_directory(path)
            except Exception as e:
                module.fail_json(msg=to_native(e), errno=e[0], reason=to_native(e), **result)

        module.exit_json(changed=True, **result)

    elif state == 'file':

        if not exists:
            result['state'] = 'absent'
            result['status'] = status
            module.fail_json(msg="File '%s' is absent, cannot continue" % path, **result)

        result['status'] = status
        module.exit_json(changed=False, **result)

    elif state == 'touch':
        if exists:
            result['state'] = 'file'
            module.exit_json(changed=False, **result)

        if module.check_mode:
            result['reason'] = 'Created'
            result['status'] = 201
        else:
            try:
                r = open_url(url, method='PUT', timeout=timeout,
                             url_username=username, url_password=password,
                             validate_certs=validate_certs, force_basic_auth=True)
            except HTTPError as e:
                r = e
            except socket.error as e:
                module.fail_json(msg=to_native(e), errno=e[0], reason=to_native(e), **result)
            except Exception as e:
                module.fail_json(msg=to_native(e), errno=e[0], reason=to_native(e), **result)

            if PY2:
                sys.exc_clear()  # Avoid false positive traceback in fail_json() on Python 2

            result['reason'] = r.msg
            result['status'] = r.getcode()
            if result['status'] != 201:
                module.fail_json(msg="Failed to touch '%s'" % path, errno=None, headers=dict(r.headers), **result)

        result['size'] = 0
        result['state'] = 'file'
        module.exit_json(changed=True, **result)


if __name__ == '__main__':
    main()
