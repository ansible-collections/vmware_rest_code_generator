#!/usr/bin/env python3

import argparse
from typing import DefaultDict
import jinja2
import json
import os
import pathlib
import re
import shutil
import subprocess
import pkg_resources
from .content_library_data import content_library_static_ds
from pbr.version import VersionInfo
import baron
import redbaron
import yaml
from functools import lru_cache
from gouttelette.utils import (
    format_documentation,
    indent,
    get_module_from_config,
    python_type,
    UtilsBase,
    jinja2_renderer,
)


def normalize_parameter_name(name):
    # the in-query filter.* parameters are not valid Python variable names.
    # We replace the . with a _ to avoid problem,
    return name.replace("filter.", "filter_")  # < 7.0.2


def ansible_state(operationId, default_operationIds=None):
    mapping = {
        "update": "present",
        "delete": "absent",
        "create": "present",
    }
    # in this case, we don't want to see 'create' in the
    # "Required with" listi
    if (
        default_operationIds
        and operationId == "update"
        and "create" not in default_operationIds
    ):
        return
    if operationId in mapping:
        return mapping[operationId]
    else:
        return operationId


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
        def rewrite_name(matchobj):
            name = matchobj.group(1)
            snake_name = cls.to_snake(name)
            if snake_name[0] == "#":  # operationId:
                output = f"C({ansible_state(snake_name[1:])})"
            output = f"C({snake_name})"
            return output

        def rewrite_link(matchobj):
            name = matchobj.group(1)
            if "#" in name and name.split("#")[0]:
                output = name.split("#")[1]
            else:
                output = name
            return output

        my_string = my_string.replace(" {@term enumerated type}", "")
        my_string = my_string.replace(" {@term list}", "list")
        my_string = my_string.replace(" {@term operation}", "operation")
        my_string = re.sub(r"{@name DayOfWeek}", "day of the week", my_string)
        my_string = re.sub(r": The\s\S+\senumerated type", ": This option", my_string)
        my_string = re.sub(r" <p> ", " ", my_string)
        my_string = re.sub(r" See {@.*}.", "", my_string)
        my_string = re.sub(r"\({@.*?\)", "", my_string)
        my_string = re.sub(r"{@code true}", "C(True)", my_string)
        my_string = re.sub(r"{@code false}", "C(False)", my_string)
        my_string = re.sub(r"{@code\s+?(.*?)}", r"C(\1)", my_string)
        my_string = re.sub(r"{@param.name\s+?([^}]*)}", rewrite_name, my_string)
        my_string = re.sub(r"{@name\s+?([^}]*)}", rewrite_name, my_string)
        # NOTE: it's pretty much impossible to build something useful
        # automatically.
        # my_string = re.sub(r"{@link\s+?([^}]*)}", rewrite_link, my_string)
        for k in content_library_static_ds:
            my_string = re.sub(k, content_library_static_ds[k], my_string)
        return my_string

    @classmethod
    def to_snake(cls, camel_case):
        camel_case = camel_case.replace("DNS", "dns")
        return re.sub(r"(?<!^)(?=[A-Z])", "_", camel_case).lower()

    @classmethod
    def ref_to_parameter(cls, ref):
        splitted = ref.split(".")
        my_parameter = splitted[-1].replace("-", "_")
        return cls.to_snake(my_parameter)

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
            "infraprofile.profile": "appliance_infraprofile_configs",
            "appliance.vmon.Service": "appliance_vmon_service",
        }

        if not m:
            return my_string

        resource_name = m.group(1)
        try:
            module_name = mapping[resource_name]
        except KeyError:
            print(f"No mapping for {resource_name}")
            raise

        if f"must be an identifier for the resource type: {resource_name}" in my_string:
            return my_string.replace(
                f"must be an identifier for the resource type: {resource_name}",
                f"must be the id of a resource returned by M(vmware.vmware_rest.{module_name})",
            )
        if f"identifiers for the resource type: {resource_name}" in my_string:
            return my_string.replace(
                f"identifiers for the resource type: {resource_name}",
                f"the id of resources returned by M(vmware.vmware_rest.{module_name})",
            ).rstrip()


def gen_documentation(
    name, target_dir: pathlib.Path, description, parameters, added_ins, next_version
):

    short_description = description.split(". ")[0]
    documentation = {
        "author": ["Ansible Cloud Team (@ansible-collections)"],
        "description": description,
        "module": name,
        "notes": ["Tested on vSphere 7.0.2"],
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
                    "The vSphere vCenter password",
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
            "session_timeout": {
                "description": [
                    "Timeout settings for client session. ",
                    "The maximal number of seconds for the whole operation including connection establishment, request sending and response. ",
                    "The default value is 300s.",
                ],
                "type": "float",
                "version_added": "2.1.0",
            },
        },
        "requirements": ["vSphere 7.0.2 or greater", "python >= 3.6", "aiohttp"],
        "short_description": short_description,
        "version_added": next_version,
    }

    # Note: this series of if block is overcomplicated and should
    # be refactorized.
    for parameter in parameters:
        if parameter["name"] == "action":
            continue
        normalized_name = normalize_parameter_name(parameter["name"])
        description = []
        option = {}
        if parameter.get("required"):
            option["required"] = True
        if parameter.get("aliases"):
            option["aliases"] = parameter.get("aliases")
        if parameter.get("description"):
            description.append(parameter["description"])
        if parameter.get("subkeys"):
            description.append("Valid attributes are:")
            for sub_k, sub_v in parameter.get("subkeys").items():
                sub_v["type"] = python_type(sub_v["type"])
                states = sorted(set([ansible_state(o) for o in sub_v["_operationIds"]]))
                required_with_operations = sorted(
                    set([ansible_state(o) for o in sub_v["_required_with_operations"]])
                )
                description.append(
                    " - C({name}) ({type}): {description} ({states})".format(
                        **sub_v, states=states
                    )
                )
                if required_with_operations:
                    description.append(
                        f"   This key is required with {required_with_operations}."
                    )
                if "enum" in sub_v:
                    description.append("   - Accepted values:")
                    for i in sorted(sub_v["enum"]):
                        description.append(f"     - {i}")
                if "properties" in sub_v:
                    description.append("   - Accepted keys:")
                    for i, v in sub_v["properties"].items():
                        description.append(
                            f"     - {i} ({v['type']}): {v['description']}"
                        )
                        if v.get("enum"):
                            description.append("Accepted value for this field:")
                            for val in sorted(v.get("enum")):
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
        parameter["added_in"] = next_version

    module_from_config = get_module_from_config(name, target_dir)
    if module_from_config and "documentation" in module_from_config:
        for k, v in module_from_config["documentation"].items():
            documentation[k] = v
    return documentation


def path_to_name(path: str):
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

    # workaround for vcenter_vm_power and appliance_services, appliance_shutdown, appliance_system_storage
    if elements[-1] in (
        "stop",
        "start",
        "restart",
        "suspend",
        "reset",
        "cancel",
        "poweroff",
        "reboot",
        "resize",
    ):
        elements = elements[:-1]
    if elements[0:2] == ["rest", "appliance"]:
        elements = elements[1:]
    elif elements[0:2] == ["rest", "vcenter"]:
        elements = elements[1:]
    elif elements[0:2] == ["rest", "api"]:
        elements = elements[2:]
    elif elements[:1] == ["api"]:
        elements = elements[1:]

    module_name = "_".join(elements)
    return module_name.replace("-", "")


def gen_arguments_py(parameters, list_index=None):
    result = ""
    for parameter in parameters:
        name = normalize_parameter_name(parameter["name"])
        values = []

        if name in ["user_name", "username", "encryption_key", "client_token"]:
            values.append("'no_log': True")
        elif "password" in name:
            values.append("'no_log': True")

        if parameter.get("required"):
            values.append("'required': True")

        aliases = parameter.get("aliases")
        if aliases:
            values.append(f"'aliases': {aliases}")

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


def flatten_ref(tree, definitions):
    if isinstance(tree, str):
        if tree.startswith("#/definitions/"):
            raise Exception("TODO")
        return definitions.get(tree)
    if isinstance(tree, list):
        return [flatten_ref(i, definitions) for i in tree]
    if tree is None:
        return {}
    for k in tree:
        v = tree[k]
        if k == "$ref":
            dotted = v.split("/")[2]
            if dotted in ["vapi.std.localization_param", "VapiStdLocalizationParam"]:
                # to avoid an endless loop with
                # vapi.std.nested_localizable_message
                return {"go_to": "vapi.std.localization_param"}
            definition = definitions.get(dotted)
            data = flatten_ref(definition, definitions)
            if "description" not in data and "description" in tree:
                data["description"] = tree["description"]
            return data
        elif isinstance(v, dict):
            tree[k] = flatten_ref(v, definitions)
        else:
            pass
    return tree


class Resource:
    def __init__(self, name):
        self.name = name
        self.operations = {}
        self.summary = {}


class AnsibleModuleBase(UtilsBase):
    def __init__(self, resource, definitions):
        self.resource = resource
        self.definitions = definitions
        self.name = resource.name
        self.default_operationIds = None

    def description(self):
        prefered_operationId = ["get", "list", "create", "get", "set"]
        for operationId in prefered_operationId:
            if operationId not in self.default_operationIds:
                continue
            if operationId in self.resource.summary:
                return self.resource.summary[operationId].split("\n")[0]

        for operationId in sorted(self.default_operationIds):
            if operationId in self.resource.summary:
                return self.resource.summary[operationId].split("\n")[0]

        print(f"generic description: {self.name}")
        return f"Handle resource of type {self.name}"

    def get_path(self):
        return list(self.resource.operations.values())[0][1]

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
        """ "Return a structure that describe the format of the data to send back."""
        payload = {}
        # for operationId in self.resource.operations:
        for operationId in self.default_operationIds:
            if operationId not in self.resource.operations:
                continue
            payload[operationId] = {"query": {}, "body": {}, "path": {}}
            payload_info = {}
            for parameter in AnsibleModule._property_to_parameter(
                self.resource.operations[operationId][2], self.definitions, operationId
            ):
                _in = parameter["in"] or "body"

                payload_info = parameter["_loc_in_payload"]
                payload[operationId][_in][parameter["name"]] = payload_info
        return payload

    def answer(self):
        # This is arguably not super elegant. The list outputs just include a summary of the resources,
        # with this little transformation, we get access to the full item
        output_format = None
        for i in ["list", "get"]:
            if i in self.resource.operations:
                output_format = self.resource.operations[i][3]["200"]
        if not output_format:
            return

        if "items" in output_format["schema"]:
            ref = (
                output_format["schema"]["items"]
                .get("$ref", "")
                .replace("Summary", "Info")
            )
        elif "schema" in output_format:
            ref = output_format["schema"].get("$ref")
        else:
            ref = output_format.get("$ref")

        if not ref:
            return
        try:
            raw_answer = flatten_ref({"$ref": ref}, self.definitions)
        except KeyError:
            return
        if "properties" in raw_answer:
            return raw_answer["properties"].keys()

    def parameters(self):
        def sort_operationsid(input):
            output = sorted(input)
            if "create" in output:
                output = ["create"] + output
            return output

        results = {}
        for operationId in sort_operationsid(self.default_operationIds):
            if operationId not in self.resource.operations:
                continue

            for parameter in AnsibleModule._property_to_parameter(
                self.resource.operations[operationId][2], self.definitions, operationId
            ):
                name = parameter["name"]
                if name not in results:
                    results[name] = parameter
                    results[name]["operationIds"] = []
                    results[name]["_required_with_operations"] = []

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
                    results[name]["enum"] = sorted(set(results[name]["enum"]))

                results[name]["operationIds"].append(operationId)
                results[name]["operationIds"].sort()
                if "subkeys" in parameter:
                    if "subkeys" not in results[name]:
                        results[name]["subkeys"] = {}
                    for sub_k, sub_v in parameter["subkeys"].items():
                        if sub_k in results[name]["subkeys"]:
                            results[name]["subkeys"][sub_k][
                                "_required_with_operations"
                            ] += sub_v["_required_with_operations"]
                            results[name]["subkeys"][sub_k]["_operationIds"] += sub_v[
                                "_operationIds"
                            ]
                            results[name]["subkeys"][sub_k]["description"] = sub_v[
                                "description"
                            ]
                        else:
                            results[name]["subkeys"][sub_k] = sub_v

                if parameter.get("required"):
                    results[name]["_required_with_operations"].append(operationId)

        answer_fields = self.answer()
        # Note: If the final result comes with a "label" field, we expose a "label"
        # parameter. We will use the field to identify an existing resource.
        if answer_fields and "label" in answer_fields:
            results["label"] = {
                "type": "str",
                "name": "label",
                "description": "The name of the item",
            }

        for name, result in results.items():
            if result.get("enum"):
                result["enum"] = sorted(set(result["enum"]))
            if result.get("required"):
                if (
                    len(set(self.default_operationIds) - set(result["operationIds"]))
                    > 0
                ):

                    required_with = []
                    for i in result["operationIds"]:
                        state = ansible_state(i, self.default_operationIds)
                        if state:
                            required_with.append(state)
                    result["description"] += " Required with I(state={})".format(
                        sorted(set(required_with))
                    )
                    del result["required"]
                else:
                    result["description"] += " This parameter is mandatory."

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

        # There is just one possible operation, we remove the "state" parameter
        if len(self.resource.operations) == 1:
            del results["state"]

        # Suppport pre 7.0.2 filters
        if "list" in self.default_operationIds or "get" in self.default_operationIds:
            for i in ["datacenters", "folders", "names"]:
                if i in results and results[i]["type"] == "array":
                    results[i]["aliases"] = [f"filter_{i}"]
            if "type" in results and results["type"]["type"] == "string":
                results["type"]["aliases"] = ["filter_type"]
            if "types" in results and results["types"]["type"] == "array":
                results["types"]["aliases"] = ["filter_types"]

        return sorted(results.values(), key=lambda item: item["name"])

    def gen_required_if(self, parameters):
        by_states = DefaultDict(list)
        for parameter in parameters:
            for operation in parameter.get("_required_with_operations", []):
                by_states[ansible_state(operation)].append(parameter["name"])
        entries = []
        for operation, fields in by_states.items():
            state = ansible_state(operation)
            if "state" in entries:
                entries.append(["state", state, sorted(set(fields)), True])
        return entries

    @staticmethod
    def _property_to_parameter(prop_struct, definitions, operationId):
        properties = flatten_ref(prop_struct, definitions)

        def get_next(properties):
            required_keys = []
            for i, v in enumerate(properties):
                required = v.get("required")
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
                    required_keys = required_keys or []
                    if "required" in v["spec"]:
                        required_keys = v["spec"]["required"]
                    for name, property in v["spec"]["properties"].items():
                        yield name, property, ["spec"], name in required_keys

                elif isinstance(v, dict):
                    if not isinstance(v, dict):
                        continue
                    # {'type': 'string', 'required': True, 'in': 'path', 'name': 'datacenter', 'description': 'Identifier of the datacenter.'}
                    if "name" in v and "in" in v and v.get("in") in ["path", "query"]:
                        yield v["name"], v, [], v.get("required")
                    # elif "name" in v and isinstance(v["name", dict]):
                    #    yield v["name"], v, [], v.get("required")
                    else:
                        for k, data in v.items():
                            if isinstance(data, dict):
                                yield k, data, [], k in required_keys or data.get(
                                    "required"
                                )

        parameters = []

        for name, v, parent, required in get_next(properties):
            if name == "request_body":
                raise ValueError()
            parameter = {
                "name": name,
                "type": v.get("type", "str"),  # 'str' by default, should be ok
                "description": v.get("description", ""),
                "required": required,
                "_loc_in_payload": "/".join(parent + [name]),
                "in": v.get("in"),
            }
            if "enum" in v:
                parameter["enum"] = sorted(set(v["enum"]))

            sub_items = None
            required_subkeys = v.get("required", [])

            if "properties" in v:
                sub_items = v["properties"]
                if "required" in v["properties"]:  # NOTE: do we still need these
                    required_subkeys = v["properties"]["required"]
            elif "items" in v and "properties" in v["items"]:
                sub_items = v["items"]["properties"]
                if "required" in v["items"]:  # NOTE: do we still need these
                    required_subkeys = v["items"]["required"]
            elif "items" in v and "name" not in v["items"]:
                parameter["elements"] = v["items"].get("type", "str")
            elif "items" in v and v["items"]["name"]:
                sub_items = v["items"]

            if sub_items:
                subkeys = {}
                for sub_k, sub_v in sub_items.items():
                    subkey = {
                        "name": sub_k,
                        "type": sub_v["type"],
                        "description": sub_v.get("description", ""),
                        "_required_with_operations": [operationId]
                        if sub_k in required_subkeys
                        else [],
                        "_operationIds": [operationId],
                    }
                    if "enum" in sub_v:
                        subkey["enum"] = sub_v["enum"]
                    if "properties" in sub_v:
                        subkey["properties"] = sub_v["properties"]
                    subkeys[sub_k] = subkey
                parameter["subkeys"] = subkeys
                parameter["elements"] = "dict"
            parameters.append(parameter)

        return sorted(
            parameters, key=lambda item: (item["name"], item.get("description"))
        )

    def list_path(self):
        list_path = None
        if "list" in self.resource.operations:
            list_path = self.resource.operations["list"][1]

        return list_path

    def renderer(self, target_dir, next_version):

        added_ins = {}  # get_module_added_ins(self.name, git_dir=target_dir / ".git")
        arguments = gen_arguments_py(self.parameters(), self.list_index())
        documentation = format_documentation(
            gen_documentation(
                self.name,
                target_dir,
                self.description(),
                self.parameters(),
                added_ins,
                next_version,
            )
        )
        required_if = self.gen_required_if(self.parameters())

        content = jinja2_renderer(
            self.template_file,
            target_dir=target_dir,
            arguments=indent(arguments, 4),
            documentation=documentation,
            list_index=self.list_index(),
            list_path=self.list_path(),
            name=self.name,
            operations=self.resource.operations,
            path=self.get_path(),
            payload_format=self.payload(),
            required_if=required_if,
        )

        self.write_module(target_dir, content)


class AnsibleModule(AnsibleModuleBase):
    template_file = "default_module.j2"

    def __init__(self, resource, definitions):
        super().__init__(resource, definitions)
        # TODO: We can probably do better
        self.default_operationIds = set(list(self.resource.operations.keys())) - set(
            ["get", "list"]
        )


class AnsibleInfoModule(AnsibleModuleBase):
    def __init__(self, resource, definitions):
        super().__init__(resource, definitions)
        self.name = resource.name + "_info"
        self.default_operationIds = ["get", "list"]

    def parameters(self):
        return [i for i in list(super().parameters()) if i["name"] != "state"]


class AnsibleInfoNoListModule(AnsibleInfoModule):
    template_file = "info_no_list_module.j2"


class AnsibleInfoListOnlyModule(AnsibleInfoModule):
    template_file = "info_list_and_get_module.j2"


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

        try:
            definition = self.definitions[dotted]
        except KeyError:
            definition = self.definitions["com.vmware." + dotted]

        if definition is None:
            raise Exception("Cannot find ref for {ref}")

        return definition


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
    def __init__(self, raw_content):
        super().__init__()
        self.resources = {}
        json_content = json.loads(raw_content)
        self.definitions = Definitions(json_content["definitions"])
        self.paths = self.load_paths(json_content["paths"])

    @staticmethod
    def load_paths(paths):
        result = {}

        for path in [Path(p, v) for p, v in paths.items()]:
            if path.is_tech_preview():
                continue
            result[path.path] = path
            for verb, desc in path.value.items():
                operationId = desc["operationId"]
                if desc.get("deprecated"):
                    continue
                try:
                    parameters = desc["parameters"]
                except KeyError:
                    print(f"No parameters for {operationId} {path.path}")
                if path.path.startswith("/rest/vcenter/vm/{vm}/tools"):
                    if operationId == "upgrade":
                        print(f"Skipping {path.path} upgrade (broken)")
                        continue
                if path.path == "/api/appliance/infraprofile/configs":
                    if operationId == "validate$task":
                        print(f"Skipping {path.path} upgrade (broken)")
                        continue
                path.operations[operationId] = (
                    verb,
                    path.path,
                    parameters,
                    desc["responses"],
                )
        return result

    @staticmethod
    def init_resources(paths):
        resources = {}
        for path in paths:
            if "vmw-task=true" in path.path:
                continue

            name = path_to_name(path.path)
            if name == "esx_settings_clusters_software_drafts":
                continue
            if name not in resources:
                resources[name] = Resource(name)

            for operationId, v in path.operations.items():
                verb = v[0]
                resources[name].summary[operationId] = path.summary(verb)
                if operationId in resources[name].operations:
                    print(
                        f"Cannot create operationId ({operationId}) with path "
                        f"({verb}) {path.path}. already defined: "
                        f"{resources[name].operations[operationId]}"
                    )
                    continue
                operationId = operationId.replace(
                    "$task", ""
                )  # NOTE: Not sure if this is the right thing to do
                resources[name].operations[operationId] = v
        return resources


def run_git(git_dir, *args):
    cmd = [
        "git",
        "--git-dir",
        git_dir,
    ]
    for arg in args:
        cmd.append(arg)
    r = subprocess.run(cmd, text=True, capture_output=True)
    return r.stdout.rstrip().split("\n")


@lru_cache(maxsize=None)
def file_by_tag(git_dir):
    tags = run_git(git_dir, "tag")

    files_by_tag = {}
    for tag in tags:
        files_by_tag[tag] = run_git(git_dir, "ls-tree", "-r", "--name-only", tag)

    return files_by_tag


def get_module_added_ins(module_name, git_dir):

    added_ins = {"module": None, "parameters": {}}

    parameters = {}
    for tag, files in file_by_tag(git_dir).items():
        if "rc" in tag:
            continue
        if f"plugins/modules/{module_name}.py" in files:
            if not added_ins["module"]:
                added_ins["module"] = tag
            content = "\n".join(
                run_git(
                    git_dir,
                    "cat-file",
                    "--textconv",
                    f"{tag}:plugins/modules/{module_name}.py",
                )
            )
            try:
                ast_file = redbaron.RedBaron(content)
            except baron.BaronError as e:
                print(f"Failed to parse {tag}:plugins/modules/{module_name}.py. {e}")
                continue
            doc_block = ast_file.find(
                "assignment", target=lambda x: x.dumps() == "DOCUMENTATION"
            )
            if not doc_block or not doc_block.value:
                print(f"Cannot find DOCUMENTATION bloc for module {module_name}")
            doc_content = yaml.safe_load(doc_block.value.to_python())
            for option in doc_content["options"]:
                if option not in added_ins["parameters"]:
                    added_ins["parameters"][option] = tag

    return added_ins


def main():

    parser = argparse.ArgumentParser(description="Build the vmware_rest modules.")
    parser.add_argument(
        "--target-dir",
        dest="target_dir",
        type=pathlib.Path,
        default=pathlib.Path("vmware_rest"),
        help="location of the target repository (default: ./vmware_rest)",
    )
    parser.add_argument(
        "--next-version",
        type=str,
        default="TODO",
        help="the next major version",
    )
    args = parser.parse_args()

    module_list = []
    for json_file in ["vcenter.json", "content.json", "appliance.json"]:
        print("Generating modules from {}".format(json_file))
        raw_content = pkg_resources.resource_string(
            "vmware_rest_code_generator", f"api_specifications/7.0.2/{json_file}"
        )
        swagger_file = SwaggerFile(raw_content)
        resources = swagger_file.init_resources(swagger_file.paths.values())

        for resource in resources.values():
            if resource.name == "appliance_logging_forwarding":
                continue
            if resource.name.startswith("vcenter_trustedinfrastructure"):
                continue
            if "list" in resource.operations:
                module = AnsibleInfoListOnlyModule(
                    resource, definitions=swagger_file.definitions
                )
                if (
                    module.is_trusted(target_dir=args.target_dir)
                    and len(module.default_operationIds) > 0
                ):
                    module.renderer(
                        target_dir=args.target_dir, next_version=args.next_version
                    )
                    module_list.append(module.name)
            elif "get" in resource.operations:
                module = AnsibleInfoNoListModule(
                    resource, definitions=swagger_file.definitions
                )
                if (
                    module.is_trusted(target_dir=args.target_dir)
                    and len(module.default_operationIds) > 0
                ):
                    module.renderer(
                        target_dir=args.target_dir, next_version=args.next_version
                    )
                    module_list.append(module.name)

            module = AnsibleModule(resource, definitions=swagger_file.definitions)

            if (
                module.is_trusted(target_dir=args.target_dir)
                and len(module.default_operationIds) > 0
            ):
                module.renderer(
                    target_dir=args.target_dir, next_version=args.next_version
                )
                module_list.append(module.name)

    info = VersionInfo("vmware_rest_code_generator")
    dev_md = args.target_dir / "dev.md"
    dev_md.write_text(
        (
            "The modules are autogenerated by:\n"
            "https://github.com/ansible-collections/vmware_rest_code_generator\n"
            ""
            f"version: {info.version_string()}\n"
        )
    )
    dev_md = args.target_dir / "commit_message"
    dev_md.write_text(
        (
            "bump auto-generated modules\n"
            "\n"
            "The modules are autogenerated by:\n"
            "https://github.com/ansible-collections/vmware_rest_code_generator\n"
            ""
            f"version: {info.version_string()}\n"
        )
    )

    module_utils_dir = args.target_dir / "plugins" / "module_utils"
    module_utils_dir.mkdir(exist_ok=True)
    vmware_rest_dest = module_utils_dir / "vmware_rest.py"
    vmware_rest_dest.write_bytes(
        pkg_resources.resource_string(
            "vmware_rest_code_generator", "module_utils/vmware_rest.py"
        )
    )


if __name__ == "__main__":
    main()
