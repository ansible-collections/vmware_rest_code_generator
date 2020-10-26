#!/usr/bin/env python3

import argparse
import ast
import collections
import io
import json
import re
import pathlib
import shutil
import subprocess
from ruamel.yaml import YAML


def normalize_parameter_name(name):
    # the in-query filter.* parameters are not valid Python variable names.
    # We replace the . with a _ to avoid proble,
    return name.replace("filter.", "filter_")


class Description:
    @classmethod
    def normalize(cls, string_list):
        if not isinstance(string_list, list):
            raise TypeError

        with_no_line_break = []
        for l in string_list:
            if "\n" in l:
                with_no_line_break += l.split("\n")
            else:
                with_no_line_break.append(l)

        with_no_line_break = [cls.write_M(i) for i in with_no_line_break]
        with_no_line_break = [cls.write_I(i) for i in with_no_line_break]
        with_no_line_break = [cls.clean_up(i) for i in with_no_line_break]
        return with_no_line_break

    @classmethod
    def clean_up(cls, my_string):
        my_string = my_string.replace(" {@term enumerated type}", "")
        my_string = re.sub(r"{@name DayOfWeek}", "day of the week", my_string)
        my_string = re.sub(r": The\s\S+\senumerated type", ": This option", my_string)
        return my_string

    @classmethod
    def ref_to_parameter(cls, ref):
        splitted = ref.split(".")
        my_parameter = splitted[-1].replace("-", "_")
        return re.sub(r"(?<!^)(?=[A-Z])", "_", my_parameter).lower()

    @classmethod
    def write_I(cls, my_string):
        refs = {
            cls.ref_to_parameter(i): i
            for i in re.findall(r"[A-Z][\w+]+\.[A-Z][\w+\.-]+", my_string)
        }
        for parameter_name in sorted(refs.keys(), key=len, reverse=True):
            ref = refs[parameter_name]
            my_string = my_string.replace(ref, f"I({parameter_name})")
        return my_string

    @classmethod
    def write_M(cls, my_string):
        my_string = re.sub(r"When operations return.*\.($|\s)", "", my_string)

        m = re.search(r"resource type:\s([a-zA-Z][\w\.]+[a-z])", my_string)
        mapping = {
            "ClusterComputeResource": "vcenter_cluster_info",
            "Datacenter": "vcenter_datacenter_info",
            "Datastore": "vcenter_datastore_info",
            "Folder": "vcenter_folder_info",
            "HostSystem": "vcenter_host_info",
            "Network": "vcenter_network_info",
            "ResourcePool": "vcenter_resourcepool_info",
            "vcenter.StoragePolicy": "vcenter_storage_policies",
            "vcenter.vm.hardware.Cdrom": "vcenter_vm_hardware_cdrom",
            "vcenter.vm.hardware.Disk": "vcenter_vm_hardware_disk",
            "vcenter.vm.hardware.Ethernet": "vcenter_vm_hardware_ethernet",
            "vcenter.vm.hardware.Floppy": "vcenter_vm_hardware_floppy",
            "vcenter.vm.hardware.ParallelPort": "vcenter_vm_hardware_parallel",
            "vcenter.vm.hardware.SataAdapter": "vcenter_vm_hardware_adapter_sata",
            "vcenter.vm.hardware.ScsiAdapter": "vcenter_vm_hardware_adapter_scsi",
            "vcenter.vm.hardware.SerialPort": "vcenter_vm_hardware_serial",
            "VirtualMachine": "vcenter_vm_info",
        }

        if m:
            resource_name = m.group(1)
            try:
                module_name = mapping[resource_name]
            except KeyError:
                print(f"No mapping for {resource_name}")
                raise

            if (
                f"must be an identifier for the resource type: {resource_name}"
                in my_string
            ):
                return my_string.replace(
                    f"must be an identifier for the resource type: {resource_name}",
                    f"must be the id of a resource returned by M({module_name})",
                )
            elif f"identifiers for the resource type: {resource_name}" in my_string:
                return my_string.replace(
                    f"identifiers for the resource type: {resource_name}",
                    f"the id of resources returned by M({module_name})",
                )
        else:
            return my_string


def python_type(value):
    TYPE_MAPPING = {
        "array": "list",
        "boolean": "bool",
        "integer": "int",
        "object": "dict",
        "string": "str",
    }
    return TYPE_MAPPING.get(value, value)


def gen_documentation(name, description, parameters):

    documentation = {
        "author": ["Goneri Le Bouder (@goneri) <goneri@lebouder.net>"],
        "description": description,
        "module": name,
        "notes": ["Tested on vSphere 7.0"],
        "options": {
            "vcenter_hostname": {
                "description": [
                    "The hostname or IP address of the vSphere vCenter",
                    "If the value is not specified in the task, the value of environment variable C(VMWARE_HOST) will be used instead.",
                ],
                "type": "str",
                "required": True,
            },
            "vcenter_username": {
                "description": [
                    "The vSphere vCenter username",
                    "If the value is not specified in the task, the value of environment variable C(VMWARE_USER) will be used instead.",
                ],
                "type": "str",
                "required": True,
            },
            "vcenter_password": {
                "description": [
                    "The vSphere vCenter username",
                    "If the value is not specified in the task, the value of environment variable C(VMWARE_PASSWORD) will be used instead.",
                ],
                "type": "str",
                "required": True,
            },
            "vcenter_validate_certs": {
                "description": [
                    "Allows connection when SSL certificates are not valid. Set to C(false) when certificates are not trusted.",
                    "If the value is not specified in the task, the value of environment variable C(VMWARE_VALIDATE_CERTS) will be used instead.",
                ],
                "type": "bool",
                "default": True,
            },
            "vcenter_rest_log_file": {
                "description": [
                    "You can use this optional parameter to set the location of a log file. ",
                    "This file will be used to record the HTTP REST interaction. ",
                    "The file will be stored on the host that run the module. ",
                    "If the value is not specified in the task, the value of ",
                    "environment variable C(VMWARE_REST_LOG_FILE) will be used instead.",
                ],
                "type": "str",
            },
        },
        "requirements": ["python >= 3.6", "aiohttp"],
        "short_description": description,
        "version_added": "1.0.0",
    }

    # Note: this series of if block is overcomplicated and should
    # be refactorized.
    for parameter in parameters:
        normalized_name = normalize_parameter_name(parameter["name"])
        description = []
        option = {}
        if parameter.get("required"):
            option["required"] = True
        if parameter.get("description"):
            description.append(parameter["description"])
        if parameter.get("subkeys"):
            description.append("Valide attributes are:")
            for subkey in parameter.get("subkeys"):
                subkey["type"] = python_type(subkey["type"])
                description.append(
                    " - C({name}) ({type}): {description}".format(**subkey)
                )
                if "enum" in subkey:
                    description.append("   - Accepted values:")
                    for i in subkey["enum"]:
                        description.append(f"     - {i}")
                if "properties" in subkey:
                    description.append("   - Accepted keys:")
                    for i, v in subkey["properties"].items():
                        description.append(
                            f"     - {i} ({v['type']}): {v['description']}"
                        )
                        if v.get("enum"):
                            description.append("Accepted value for this field:")
                            for val in v.get("enum"):
                                description.append(f"       - C({val})")

        option["description"] = list(Description.normalize(description))
        option["type"] = python_type(parameter["type"])
        if "enum" in parameter:
            option["choices"] = sorted(parameter["enum"])
        if parameter["type"] == "array":
            option["elements"] = python_type(parameter["elements"])
        if parameter.get("default"):
            option["default"] = parameter.get("default")

        documentation["options"][normalized_name] = option
    return documentation


def format_documentation(documentation):
    import yaml

    def _sanitize(input):
        if isinstance(input, str):
            return input.replace("':'", ":")
        elif isinstance(input, list):
            return [l.replace("':'", ":") for l in input]
        elif isinstance(input, dict):
            return {k: _sanitize(v) for k, v in input.items()}
        elif isinstance(input, bool):
            return input
        else:
            raise TypeError

    keys = [
        "module",
        "short_description",
        "description",
        "options",
        "author",
        "version_added",
        "requirements",
    ]
    final = "'''\n"
    for i in keys:
        final += yaml.dump({i: _sanitize(documentation[i])}, indent=2)
    final += "'''"
    return final


def path_to_name(path):
    _path = path.lstrip("/").split("?")[0]
    elements = []
    keys = []
    for i in _path.split("/"):
        if "{" in i:
            keys.append(i)
        elif len(keys) > 1:
            # action for a submodule, we gather these end-points in the main module
            continue
        else:
            elements.append(i)

    # workaround for vcenter_vm_power
    if elements[-1] in ("stop", "start", "suspend", "reset"):
        elements = elements[:-1]
    if elements[0:3] == ["rest", "com", "vmware"]:
        elements = elements[3:]
    elif elements[0:2] == ["rest", "hvc"]:
        elements = elements[1:]
    elif elements[0:2] == ["rest", "appliance"]:
        elements = elements[1:]
    elif elements[0:2] == ["rest", "vcenter"]:
        elements = elements[1:]
    elif elements[:1] == ["api"]:
        elements = elements[1:]

    module_name = "_".join(elements)
    return module_name.replace("-", "")


def gen_arguments_py(parameters, list_index=None):
    result = ""
    for parameter in parameters:
        name = normalize_parameter_name(parameter["name"])
        values = []

        if name in ["user_name", "username", "password"]:
            values.append("'no_log': True")

        if parameter.get("required"):
            if list_index != parameter["name"]:
                values.append("'required': True")

        _type = python_type(parameter["type"])
        values.append(f"'type': '{_type}'")
        if "enum" in parameter:
            choices = ", ".join([f"'{i}'" for i in sorted(parameter["enum"])])
            values.append(f"'choices': [{choices}]")
        if python_type(parameter["type"]) == "list":
            _elements = python_type(parameter["elements"])
            values.append(f"'elements': '{_elements}'")

        # "bus" option defaulting on 0
        if name == "bus":
            values.append("'default': 0")
        elif "default" in parameter:
            default = parameter["default"]
            values.append(f"'default': '{default}'")

        result += f"\nargument_spec['{name}'] = "
        result += "{" + ", ".join(values) + "}"
    return result


def _indent(text_block, indent=0):
    result = ""
    for l in text_block.split("\n"):
        result += " " * indent
        result += l
        result += "\n"
    return result


def flatten_ref(tree, definitions):
    if isinstance(tree, str):
        if tree.startswith("#/definitions/"):
            raise Exception("TODO")
        return definitions.get(tree)
    elif isinstance(tree, list):
        return [flatten_ref(i, definitions) for i in tree]
    elif tree is None:
        return {}
    for k in tree:
        v = tree[k]
        if k == "$ref":
            dotted = v.split("/")[2]
            if dotted == "vapi.std.localization_param":
                # to avoid an endless loop with
                # vapi.std.nested_localizable_message
                return {"go_to": "vapi.std.localization_param"}
            data = flatten_ref(definitions.get(dotted), definitions)
            if "description" not in data and "description" in tree:
                data["description"] = tree["description"]
            return data
        elif isinstance(v, dict):
            tree[k] = flatten_ref(v, definitions)
        else:
            # Note: should never happen,
            # corner case for appliance_infraprofile_configs_info
            pass
    return tree


class Resource:
    def __init__(self, name):
        self.name = name
        self.operations = {}


class AnsibleModuleBase:
    def __init__(self, resource, definitions):
        self.resource = resource
        self.definitions = definitions
        self.name = resource.name
        self.default_operationIds = None

    def description(self):
        m = re.match("vcenter_vm_hardware_adapter_(.*)_info", self.name)
        if m:
            vm_resource = m.group(1).upper()
            return f"Collect the {vm_resource} adapter information from a VM"

        m = re.match("vcenter_vm_hardware_adapter_(.*)", self.name)
        if m:
            vm_resource = m.group(1).upper()
            return f"Manage the {vm_resource} adapter of a VM"

        m = re.match("vcenter_vm_hardware_(.*)_info", self.name)
        if m:
            vm_resource = m.group(1).replace("_", " ")
            return f"Collect the {vm_resource} information from a VM"

        m = re.match("vcenter_vm_hardware_(.*)", self.name)
        if m:
            vm_resource = m.group(1).replace("_", " ")
            return f"Manage the {vm_resource} of a VM"

        m = re.match("vcenter_vm_(guest_.*)_info", self.name)
        if m:
            vm_resource = m.group(1).replace("_", " ")
            return f"Collect the {vm_resource} information"

        m = re.match("vcenter_vm_(guest_.*)", self.name)
        if m:
            vm_resource = m.group(1).replace("_", " ")
            return f"Manage the {vm_resource}"

        m = re.match("vcenter_vm_(.*)info", self.name)
        if m:
            vm_resource = m.group(1).replace("_", " ")
            return f"Collect the {vm_resource} information from a VM"

        m = re.match("vcenter_vm_(.*)", self.name)
        if m:
            vm_resource = m.group(1).replace("_", " ")
            return f"Manage the {vm_resource} of a VM"

        m = re.match("vcenter_(.*)_info", self.name)
        if m:
            vm_resource = m.group(1).replace("_", " ")
            return f"Collect the information associated with the vCenter {vm_resource}s"

        m = re.match("vcenter_(.*)", self.name)
        if m:
            vm_resource = m.group(1).replace("_", " ")
            return f"Manage the {vm_resource} of a vCenter"

        print(f"generic description: {self.name}")
        return f"Handle resource of type {self.name}"

    def is_trusted(self):
        trusted_module_allowlist = [
            "^vcenter_cluster_info$",
            "^vcenter_datacenter_info$",
            "^vcenter_datacenter$",
            "^vcenter_datastore_info$",
            "^vcenter_folder_info$",
            "^vcenter_host_info$",
            "^vcenter_host$",
            "^vcenter_network_info$",
            "^vcenter_vm($|_.+)",
            "^vcenter_storage_policies_info$",
            "^vcenter_resourcepool*",
        ]
        if self.name in [
            "vcenter_vm_guest_customization",
            "vcenter_vm_guest_power",
            "vcenter_vm_guest_power_info",
            "vcenter_vm_hardware_action_upgrade",  # vm_hardware already allow the version upgrade
            "vcenter_vm_tools_installer",  # does not work
            "vcenter_vm_tools_installer_info",
            "vcenter_vm_storage_policy_compliance",  # does not work, returns 404
        ]:
            return False

        regexes = [re.compile(i) for i in trusted_module_allowlist]
        if any([r.match(self.name) for r in regexes]):
            return True
        return False

    def list_index(self):
        for i in ["get", "update", "delete"]:
            if i not in self.resource.operations:
                continue
            path = self.resource.operations[i][1]
            break
        else:
            return

        m = re.search(r"{([-\w]+)}$", path)
        if m:
            return m.group(1)

    def payload(self):
        """"Return a structure that describe the format of the data to send back."""
        payload = {}
        for operationId in self.resource.operations:
            payload[operationId] = {"query": {}, "body": {}, "path": {}}
            payload_info = {}
            for parameter in AnsibleModule._property_to_parameter(
                self.resource.operations[operationId][2], self.definitions
            ):
                _in = parameter["in"] or "body"

                payload_info = parameter["_loc_in_payload"]
                payload[operationId][_in][parameter["name"]] = payload_info
        return payload

    def answer(self):
        try:
            raw_answer = flatten_ref(
                self.resource.operations["get"][3]["200"], self.definitions
            )
            fields = raw_answer["schema"]["properties"]["value"]["properties"]
        except KeyError:
            return

        return fields

    def parameters(self):
        def sort_operationsid(input):
            output = sorted(input)
            if "create" in output:
                output = ["create"] + output
            return output

        results = {}

        def ansible_state(operationids):
            mapping = {
                "update": "present",
                "delete": "absent",
                "create": "present",
            }
            final = []
            for o in operationids:
                # in this case, we don't want to see 'create' in the
                # "Required with" list
                if o == "update" and "create" not in operationids:
                    continue
                if o in mapping:
                    final.append(mapping[o])
                else:
                    final.append(o)
            return sorted(set(final))

        for operationId in sort_operationsid(self.default_operationIds):
            if operationId not in self.resource.operations:
                continue

            for parameter in AnsibleModule._property_to_parameter(
                self.resource.operations[operationId][2], self.definitions
            ):
                name = parameter["name"]
                if name not in results:
                    results[name] = parameter
                    results[name]["operationIds"] = []

                # Merging two parameters, for instance "action" in
                # /rest/vcenter/vm-template/library-items/{template_library_item}/check-outs
                # and
                # /rest/vcenter/vm-template/library-items/{template_library_item}/check-outs/{vm}
                if "description" not in parameter:
                    pass
                elif "description" not in results[name]:
                    results[name]["description"] = parameter.get("description")
                elif results[name]["description"] != parameter.get("description"):
                    # We can hardly merge two description strings and
                    # get magically something meaningful
                    if len(parameter["description"]) > len(
                        results[name]["description"]
                    ):
                        results[name]["description"] = parameter["description"]
                if "enum" in parameter:
                    results[name]["enum"] += parameter["enum"]

                results[name]["operationIds"].append(operationId)
                results[name]["operationIds"].sort()

        answer_fields = self.answer()
        # Note: If the final result comes with a "label" field, we expose a "label"
        # parameter. We will use the field to identify an existing resource.
        if answer_fields and "label" in answer_fields:
            results["label"] = {"type": "str", "name": "label"}

        for name, result in results.items():
            if result.get("enum"):
                result["enum"] = sorted(set(result["enum"]))
            if result.get("required"):
                if (
                    len(
                        set(self.default_operationIds)
                        - set(result["operationIds"])
                        - set(["list", "get"])
                    )
                    > 0
                ):
                    result["description"] += " Required with I(state={})".format(
                        ansible_state(result["operationIds"])
                    )
                del result["required"]
                result["required_if"] = ansible_state(result["operationIds"])

        states = []
        for operation in sorted(list(self.default_operationIds)):
            if operation in ["create", "update"]:
                states.append("present")
            elif operation == "delete":
                states.append("absent")
            else:
                states.append(operation)

        results["state"] = {
            "name": "state",
            "type": "str",
            "enum": sorted(set(states)),
        }
        if "present" in states:
            results["state"]["default"] = "present"
        elif "set" in states:
            results["state"]["default"] = "set"
        elif states:
            results["state"]["required"] = True

        return sorted(results.values(), key=lambda item: item["name"])

    def gen_url_func(self):
        first_operation = list(self.resource.operations.values())[0]
        path = first_operation[1]

        if not path.startswith("/rest"):  # Pre 7.0.0
            path = "/rest" + path

        return self.URL.format(path=path)

    @staticmethod
    def _property_to_parameter(prop_struct, definitions):
        properties = flatten_ref(prop_struct, definitions)

        def get_next(properties):
            for i, v in enumerate(properties):
                if "schema" in v:
                    if "properties" in v["schema"]:
                        properties[i] = v["schema"]["properties"]
                        if "required" in v["schema"]:
                            required_keys = v["schema"]["required"]
                    elif "additionalProperties" in v["schema"]:
                        properties[i] = v["schema"]["additionalProperties"][
                            "properties"
                        ]

            for i, v in enumerate(properties):
                # appliance_health_messages
                if isinstance(v, str):
                    yield v, {}, [], []

                elif "spec" in v and "properties" in v["spec"]:
                    required_keys = []
                    if "required" in v["spec"]:
                        required_keys = v["spec"]["required"]
                    for name, property in v["spec"]["properties"].items():
                        yield name, property, ["spec"], name in required_keys

                # appliance_networking_dns_hostname_info
                elif "name" in v and isinstance(v["name"], dict):
                    yield "name", v["name"], [], []
                elif "name" in v:
                    yield v["name"], v, [], v.get("required")
                elif isinstance(v, dict):
                    for k, data in v.items():
                        yield k, data, [], data.get("required")

        parameters = []

        for name, v, parent, required in get_next(properties):
            parameter = {
                "name": name,
                "type": v.get("type", "str"),  # 'str' by default, should be ok
                "description": v.get("description", ""),
                "required": required,
                "_loc_in_payload": "/".join(parent + [name]),
                "in": v.get("in"),
            }
            if "enum" in v:
                parameter["enum"] = v["enum"]

            sub_items = None
            if "properties" in v:
                sub_items = v["properties"]
            elif "items" in v and "properties" in v["items"]:
                sub_items = v["items"]["properties"]
            elif "items" in v and "name" not in v["items"]:
                parameter["elements"] = v["items"].get("type", "str")
            elif "items" in v and v["items"]["name"]:
                sub_items = v["items"]

            if sub_items:
                subkeys = []
                for sub_k, sub_v in sub_items.items():
                    subkey = {
                        "name": sub_k,
                        "type": sub_v["type"],
                        "description": sub_v.get("description", ""),
                    }
                    if "enum" in sub_v:
                        subkey["enum"] = sub_v["enum"]
                    if "properties" in sub_v:
                        subkey["properties"] = sub_v["properties"]
                    subkeys.append(subkey)
                parameter["subkeys"] = subkeys
                parameter["elements"] = "dict"
            parameters.append(parameter)

        return sorted(
            parameters, key=lambda item: (item["name"], item.get("description"))
        )

    def renderer(self, target_dir):
        DEFAULT_MODULE = """
#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# template: DEFAULT_MODULE

DOCUMENTATION = {documentation}

EXAMPLES = \"\"\"
\"\"\"

RETURN = \"\"\"
\"\"\"

# This structure describes the format of the data expected by the end-points
PAYLOAD_FORMAT = {payload_format}

import socket
import json
from ansible.module_utils.basic import env_fallback
try:
    from ansible_collections.cloud.common.plugins.module_utils.turbo.exceptions import EmbeddedModuleFailure
    from ansible_collections.cloud.common.plugins.module_utils.turbo.module import AnsibleTurboModule as AnsibleModule
except ImportError:
    from ansible.module_utils.basic import AnsibleModule
from ansible_collections.vmware.vmware_rest.plugins.module_utils.vmware_rest import (
    build_full_device_list,
    exists,
    gen_args,
    get_device_info,
    get_subdevice_type,
    list_devices,
    open_session,
    prepare_payload,
    update_changed_flag,
    )



def prepare_argument_spec():
    argument_spec = {{
        "vcenter_hostname": dict(
            type='str',
            required=True,
            fallback=(env_fallback, ['VMWARE_HOST']),
        ),
        "vcenter_username": dict(
            type='str',
            required=True,
            fallback=(env_fallback, ['VMWARE_USER']),
        ),
        "vcenter_password": dict(
            type='str',
            required=True,
            no_log=True,
            fallback=(env_fallback, ['VMWARE_PASSWORD']),
        ),
        "vcenter_validate_certs": dict(
            type='bool',
            required=False,
            default=True,
            fallback=(env_fallback, ['VMWARE_VALIDATE_CERTS']),
        ),
        "vcenter_rest_log_file": dict(
            type='str',
            required=False,
            fallback=(env_fallback, ['VMWARE_REST_LOG_FILE']),
        )
    }}

    {arguments}
    return argument_spec


async def main( ):
    module_args = prepare_argument_spec()
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)
    if not module.params['vcenter_hostname']:
        module.fail_json('vcenter_hostname cannot be empty')
    if not module.params['vcenter_username']:
        module.fail_json('vcenter_username cannot be empty')
    if not module.params['vcenter_password']:
        module.fail_json('vcenter_password cannot be empty')
    session = await open_session(
            vcenter_hostname=module.params['vcenter_hostname'],
            vcenter_username=module.params['vcenter_username'],
            vcenter_password=module.params['vcenter_password'],
            validate_certs=module.params['vcenter_validate_certs'],
            log_file=module.params['vcenter_rest_log_file'])
    result = await entry_point(module, session)
    module.exit_json(**result)


{url_func}

{entry_point_func}

if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

"""
        arguments = gen_arguments_py(self.parameters(), self.list_index())
        documentation = format_documentation(
            gen_documentation(self.name, self.description(), self.parameters())
        )
        url_func = self.gen_url_func()
        entry_point_func = self.gen_entry_point_func()

        module_content = DEFAULT_MODULE.format(
            name=self.name,
            documentation=documentation,
            url_func=_indent(url_func, 0),
            entry_point_func=_indent(entry_point_func, 0),
            arguments=_indent(arguments, 4),
            payload_format=self.payload(),
        )

        module_dir = target_dir / "plugins" / "modules"
        module_dir.mkdir(parents=True, exist_ok=True)
        module_py_file = module_dir / "{name}.py".format(name=self.name)
        with module_py_file.open("w") as fd:
            fd.write(module_content)


class AnsibleModule(AnsibleModuleBase):

    URL = """
# template: URL
def build_url(params):
    return (
        "https://{{vcenter_hostname}}"
        "{path}").format(**params)
"""

    def __init__(self, resource, definitions):
        super().__init__(resource, definitions)
        # TODO: We can probably do better
        self.default_operationIds = set(list(self.resource.operations.keys())) - set(
            ["get", "list"]
        )

    def gen_entry_point_func(self):
        main_content = """
# template: main_content
async def entry_point(module, session):
    if module.params['state'] == "present":
        if "_create" in globals():
            operation = "create"
        else:
            operation = "update"
    elif module.params['state'] == "absent":
        operation = "delete"
    else:
        operation = module.params['state']

    func = globals()["_" + operation]
    return await func(module.params, session)

"""

        for operation in sorted(self.default_operationIds):
            (verb, path, _, _) = self.resource.operations[operation]
            if not path.startswith("/rest"):  # TODO
                path = "/rest" + path
            if "$" in operation:
                print(
                    "skipping operation {operation} for {path}".format(
                        operation=operation, path=path
                    )
                )
                continue

            FUNC_WITH_DATA_TPL = """
# template: FUNC_WITH_DATA_TPL
async def _{operation}(params, session):
    _in_query_parameters = PAYLOAD_FORMAT["{operation}"]["query"].keys()
    payload = payload = prepare_payload(params, PAYLOAD_FORMAT["{operation}"])
    subdevice_type = get_subdevice_type("{path}")
    if subdevice_type and not params[subdevice_type]:
        _json = (await exists(params, session, build_url(params)))
        if _json:
            params[subdevice_type] = _json['id']
    _url = (
        "https://{{vcenter_hostname}}"
        "{path}").format(**params) + gen_args(params, _in_query_parameters)
    async with session.{verb}(_url, json=payload) as resp:
        try:
            if resp.headers["Content-Type"] == "application/json":
                _json = await resp.json()
        except KeyError:
            _json = {{}}
        return await update_changed_flag(_json, resp.status, "{operation}")
"""

            FUNC_WITH_DATA_DELETE_TPL = """
# template: FUNC_WITH_DATA_DELETE_TPL
async def _{operation}(params, session):
    _in_query_parameters = PAYLOAD_FORMAT["{operation}"]["query"].keys()
    payload = payload = prepare_payload(params, PAYLOAD_FORMAT["{operation}"])
    subdevice_type = get_subdevice_type("{path}")
    if subdevice_type and not params[subdevice_type]:
        _json = (await exists(params, session, build_url(params)))
        if _json:
            params[subdevice_type] = _json['id']
    _url = (
        "https://{{vcenter_hostname}}"
        "{path}").format(**params) + gen_args(params, _in_query_parameters)
    async with session.{verb}(_url, json=payload) as resp:
        try:
            if resp.headers["Content-Type"] == "application/json":
                _json = await resp.json()
        except KeyError:
            _json = {{}}
        return await update_changed_flag(_json, resp.status, "{operation}")
"""

            FUNC_WITH_DATA_UPDATE_TPL = """
# FUNC_WITH_DATA_UPDATE_TPL
async def _update(params, session):
    payload = payload = prepare_payload(params, PAYLOAD_FORMAT["{operation}"])
    _url = (
        "https://{{vcenter_hostname}}"
        "{path}").format(**params)
    async with session.get(_url) as resp:
        _json = await resp.json()
        for k, v in _json["value"].items():
            if k in payload and payload[k] == v:
                del payload[k]
            elif "spec" in payload:
                if k in payload["spec"] and payload["spec"][k] == v:
                    del payload["spec"][k]

        # NOTE: workaround for vcenter_vm_hardware, upgrade_version needs the upgrade_policy
        # option. So we ensure it's here.
        try:
            if payload["spec"]["upgrade_version"] and "upgrade_policy" not in payload["spec"]:
                payload["spec"]["upgrade_policy"] = _json["value"]["upgrade_policy"]
        except KeyError:
            pass

        if payload == {{}} or payload == {{"spec": {{}}}}:
            # Nothing has changed
            _json["id"] = params.get("{list_index}")
            return await update_changed_flag(_json, resp.status, "get")
    async with session.{verb}(_url, json=payload) as resp:
        try:
            if resp.headers["Content-Type"] == "application/json":
                _json = await resp.json()
        except KeyError:
            _json = {{}}
        _json["id"] = params.get("{list_index}")
        return await update_changed_flag(_json, resp.status, "{operation}")
"""

            FUNC_WITH_DATA_CREATE_TPL = """
# FUNC_WITH_DATA_CREATE_TPL
async def _create(params, session):
    if params["{list_index}"]:
        _json = await get_device_info(session, build_url(params), params["{list_index}"])
    else:
        _json = await exists(params, session, build_url(params), ["{list_index}"])
    if _json:
        if "_update" in globals():
            params["{list_index}"] = _json["id"]
            return (await globals()["_update"](params, session))
        else:
            return (await update_changed_flag(_json, 200, 'get'))

    payload = prepare_payload(params, PAYLOAD_FORMAT["{operation}"])
    _url = (
        "https://{{vcenter_hostname}}"
        "{path}").format(**params)
    async with session.{verb}(_url, json=payload) as resp:
        if resp.status == 500:
            raise EmbeddedModuleFailure(f"Request has failed: status={{resp.status}}, {{await resp.text()}}")
        try:
            if resp.headers["Content-Type"] == "application/json":
                _json = await resp.json()
        except KeyError:
            _json = {{}}
        # Update the value field with all the details
        if (resp.status in [200, 201]) and "value" in _json:
            if isinstance(_json["value"], dict):
                _id = list(_json["value"].values())[0]
            else:
                _id = _json["value"]
            _json = await get_device_info(session, _url, _id)

        return await update_changed_flag(_json, resp.status, "{operation}")
"""

            if operation == "delete":
                template = FUNC_WITH_DATA_DELETE_TPL
            elif operation == "create":
                template = FUNC_WITH_DATA_CREATE_TPL
            elif operation == "update":
                template = FUNC_WITH_DATA_UPDATE_TPL
            else:
                template = FUNC_WITH_DATA_TPL

            main_content += template.format(
                operation=operation, verb=verb, path=path, list_index=self.list_index(),
            )

        return main_content


class AnsibleInfoModule(AnsibleModuleBase):

    URL_WITH_LIST = """
# template: URL_WITH_LIST
def build_url(params):
    if params['{list_index}']:
        _in_query_parameters = PAYLOAD_FORMAT["get"]["query"].keys()
        return (
            "https://{{vcenter_hostname}}"
            "{path}").format(**params) + gen_args(params, _in_query_parameters)
    else:
        _in_query_parameters = PAYLOAD_FORMAT["list"]["query"].keys()
        return (
            "https://{{vcenter_hostname}}"
            "{list_path}").format(**params) + gen_args(params, _in_query_parameters)
"""

    URL_LIST_ONLY = """
# template: URL_LIST_ONLY
def build_url(params):
    _in_query_parameters = PAYLOAD_FORMAT["list"]["query"].keys()
    return (
        "https://{{vcenter_hostname}}"
        "{list_path}").format(**params) + gen_args(params, _in_query_parameters)
"""

    URL_WITH_ARGS = """
# template: URL_WITH_ARGS
def build_url(params):
    _in_query_parameters = PAYLOAD_FORMAT["get"]["query"].keys()
    return (
        "https://{{vcenter_hostname}}"
        "{path}").format(**params) + gen_args(params, _in_query_parameters)
"""

    def __init__(self, resource, definitions):
        super().__init__(resource, definitions)
        self.name = resource.name + "_info"
        self.default_operationIds = ["get", "list"]

    def parameters(self):
        return [i for i in list(super().parameters()) if i["name"] != "state"]

    def gen_url_func(self):
        path = None
        list_path = None
        if "get" in self.resource.operations:
            path = self.resource.operations["get"][1]
        if "list" in self.resource.operations:
            list_path = self.resource.operations["list"][1]

        if path and not path.startswith("/rest"):  # Pre 7.0.0
            path = "/rest" + path
        if list_path and not list_path.startswith("/rest"):  # Pre 7.0.0
            list_path = "/rest" + list_path

        if not path:
            return self.URL_LIST_ONLY.format(list_path=list_path)
        elif list_path and path.endswith("}"):
            return self.URL_WITH_LIST.format(
                path=path, list_path=list_path, list_index=self.list_index(),
            )
        else:
            return self.URL_WITH_ARGS.format(path=path)

    def gen_entry_point_func(self):
        FUNC = """
# template: FUNC
async def entry_point(module, session):
    url = build_url(module.params)
    async with session.get(url) as resp:
        _json = await resp.json()
        if module.params.get("{list_index}"):
            _json["id"] = module.params.get("{list_index}")
        elif module.params.get("label"):  # TODO extend the list of filter
            _json = await exists(module.params, session, url)
        else: # list context, retrieve the details of each entry
            try:
                if isinstance(_json["value"][0]["{list_index}"], str) and len(list(_json["value"][0].values())) == 1:
                    # this is a list of id, we fetch the details
                    full_device_list = await build_full_device_list(session, url, _json)
                    _json = {{"value": [i["value"] for i in full_device_list]}}
            except (TypeError, KeyError, IndexError):
                pass

        return await update_changed_flag(_json, resp.status, "get")
"""
        template = FUNC if self.list_index() else FUNC
        return template.format(name=self.name, list_index=self.list_index())


class Definitions:
    def __init__(self, data):
        super().__init__()
        self.definitions = data

    def get(self, ref):
        if isinstance(ref, dict):
            # TODO: standardize the input to avoid this step
            dotted = ref["$ref"].split("/")[2]
        else:
            dotted = ref

        if dotted == "appliance.networking_change_task":
            dotted = "appliance.networking_change$task"

        try:
            definition = self.definitions[dotted]
        except KeyError:
            definition = self.definitions["com.vmware." + dotted]

        if definition is None:
            raise Exception("Cannot find ref for {ref}")

        return flatten_ref(definition, self.definitions)


class Path:
    def __init__(self, path, value):
        super().__init__()
        self.path = path
        self.operations = {}
        self.verb = {}
        self.value = value

    def summary(self, verb):
        return self.value[verb]["summary"]

    def is_tech_preview(self):
        for verb in self.value.keys():
            if "Technology Preview" in self.summary(verb):
                return True
        return False


class SwaggerFile:
    def __init__(self, file_path):
        super().__init__()
        self.resources = {}
        with file_path.open() as fd:
            json_content = json.load(fd)
            self.definitions = Definitions(json_content["definitions"])
            self.paths = self.load_paths(json_content["paths"])

    @staticmethod
    def load_paths(paths):
        result = {}

        for path in [Path(p, v) for p, v in paths.items()]:
            if path.is_tech_preview():
                print(f"Skipping {path.path} (Technology Preview)")
                continue
            if path not in paths:
                result[path.path] = path
            for verb, desc in path.value.items():
                operationId = desc["operationId"]
                if path.path.startswith("/rest/vcenter/vm/{vm}/tools"):
                    if operationId == "upgrade":
                        print(f"Skipping {path.path} upgrade (broken)")
                        continue
                path.operations[operationId] = (
                    verb,
                    path.path,
                    desc["parameters"],
                    desc["responses"],
                )
        return result

    @staticmethod
    def init_resources(paths):
        resources = {}
        for path in paths:
            name = path_to_name(path.path)
            if name == "esx_settings_clusters_software_drafts":
                continue
            if name not in resources:
                resources[name] = Resource(name)
                resources[name].description = ""  # path.summary(verb)

            for k, v in path.operations.items():
                if k in resources[name].operations:
                    raise Exception(
                        "operationId already defined: %s vs %s"
                        % (resources[name].operations[k], v)
                    )
                k = k.replace(
                    "$task", ""
                )  # NOTE: Not sure if this is the right thing to do
                resources[name].operations[k] = v
        return resources


def git_revision():
    raw_output = subprocess.check_output(
        ["git", "log", "--no-decorate", "-1", "--pretty=tformat:%H"],
        env={"PAGER": "cat"},
    )
    return raw_output.decode().rstrip("\n")


def main():

    parser = argparse.ArgumentParser(description="Build the vmware_rest modules.")
    parser.add_argument(
        "--target-dir",
        dest="target_dir",
        type=pathlib.Path,
        default=pathlib.Path("vmware_rest"),
        help="location of the target repository (default: ./vmware_rest)",
    )
    args = parser.parse_args()

    module_list = []
    p = pathlib.Path("7.0.0")
    # for json_file in p.glob("*.json"):
    #     if str(json_file) == "7.0.0/api.json":
    #         continue
    for json_file in p.glob("vcenter.json"):
        print("Generating modules from {}".format(json_file))
        swagger_file = SwaggerFile(json_file)
        resources = swagger_file.init_resources(swagger_file.paths.values())

        for resource in resources.values():
            # if resource.name != "vcenter_vm":
            #     continue
            if resource.name == "appliance_logging_forwarding":
                continue
            if resource.name.startswith("vcenter_trustedinfrastructure"):
                continue
            if "get" in resource.operations or "list" in resource.operations:
                module = AnsibleInfoModule(
                    resource, definitions=swagger_file.definitions
                )
                if module.is_trusted() and len(module.default_operationIds) > 0:
                    module.renderer(target_dir=args.target_dir)
                    module_list.append(module.name)
            module = AnsibleModule(resource, definitions=swagger_file.definitions)
            if module.is_trusted() and len(module.default_operationIds) > 0:
                module.renderer(target_dir=args.target_dir)
                module_list.append(module.name)

    ignore_dir = args.target_dir / "tests" / "sanity"
    ignore_dir.mkdir(parents=True, exist_ok=True)
    ignore_content = "plugins/module_utils/vmware_rest.py compile-2.6!skip\n"
    ignore_content += "plugins/module_utils/vmware_rest.py compile-2.7!skip\n"
    ignore_content += "plugins/module_utils/vmware_rest.py compile-3.5!skip\n"
    ignore_content += "plugins/module_utils/vmware_rest.py import-3.5!skip\n"
    ignore_content += "plugins/module_utils/vmware_rest.py metaclass-boilerplate!skip\n"
    ignore_content += (
        "plugins/module_utils/vmware_rest.py future-import-boilerplate!skip\n"
    )
    files = ["plugins/modules/{}.py".format(module) for module in module_list]
    for f in files:
        for test in [
            "compile-2.6!skip",  # Py3.6+
            "compile-2.7!skip",  # Py3.6+
            "compile-3.5!skip",  # Py3.6+
            "import-3.5!skip",  # Py3.6+
            "future-import-boilerplate!skip",  # Py2 only
            "metaclass-boilerplate!skip",  # Py2 only
            "validate-modules:missing-if-name-main",
            "validate-modules:missing-main-call",  # there is an async main()
        ]:
            ignore_content += f"{f} {test}\n"

    for version in ["2.9", "2.10"]:
        ignore_file = ignore_dir / f"ignore-{version}.txt"
        ignore_file.write_text(ignore_content)

    dev_md = args.target_dir / "dev.md"
    dev_md.write_text(
        (
            "The modules are autogenerated by:\n"
            "https://github.com/ansible-collections/vmware_rest_code_generator\n"
            ""
            "version: {git_revision}\n"
        ).format(git_revision=git_revision())
    )
    dev_md = args.target_dir / "commit_message"
    dev_md.write_text(
        (
            "bump auto-generated modules\n"
            "\n"
            "The modules are autogenerated by:\n"
            "https://github.com/ansible-collections/vmware_rest_code_generator\n"
            ""
            "version: {git_revision}\n"
        ).format(git_revision=git_revision())
    )

    shutil.copy(
        "module_utils/vmware_rest.py", str(args.target_dir / "plugins" / "module_utils")
    )


if __name__ == "__main__":
    main()
