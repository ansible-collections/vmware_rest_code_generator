#!/usr/bin/env python3

import argparse
import ast
import collections
import io
import json
import re
import pathlib
import subprocess
import astunparse
from ruamel.yaml import YAML


def normalize_description(string_list):
    def _transform(my_list):
        for i in my_list:
            if not i:
                continue
            i = i.replace(" {@term enumerated type}", "")
            i = re.sub(r"{@name DayOfWeek}", "day of the week", i)
            yield i

    if not isinstance(string_list, list):
        raise TypeError

    with_no_line_break = []
    for l in string_list:
        if "\n" in l:
            with_no_line_break += l.split("\n")
        else:
            with_no_line_break.append(l)

    return list(_transform(with_no_line_break))


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
        "author": ["Ansible VMware team"],
        "description": description,
        "module": name,
        "notes": ["Tested on vSphere 7.0"],
        "options": {},
        "requirements": ["python >= 3.6"],
        "short_description": description,
        "version_added": "1.0.0",
    }

    for parameter in parameters:
        description = []
        option = {
            "type": parameter["type"],
        }
        if parameter.get("required"):
            option["required"] = True
        if parameter.get("description"):
            description.append(parameter["description"])
        if parameter.get("subkeys"):
            description.append("Validate attributes are:")
            for subkey in parameter.get("subkeys"):
                subkey["type"] = python_type(subkey["type"])
                description.append(
                    " - C({name}) ({type}): {description}".format(**subkey)
                )
        option["description"] = list(normalize_description(description))
        option["type"] = python_type(option["type"])
        if "enum" in parameter:
            option["choices"] = sorted(parameter["enum"])

        documentation["options"][parameter["name"]] = option
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
    def is_element(i):
        if i and "{" not in i:
            return True
        else:
            return False

    _path = path.split("?")[0]

    elements = [i for i in _path.split("/") if is_element(i)]
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
    def _add_key(assign, key, value):
        k = [ast.Constant(value=key, kind=None)]
        v = [ast.Constant(value=value, kind=None)]
        assign.value.keys.append(k)
        assign.value.values.append(v)

    ARGUMENT_TPL = """argument_spec['{name}'] = {{}}"""

    result = ""
    for parameter in parameters:
        assign = ast.parse(ARGUMENT_TPL.format(name=parameter["name"])).body[0]

        # if None and list_index:
        #     assign = ast.parse(ARGUMENT_TPL.format(name=list_index)).body[0]
        #     _add_key(assign, "aliases", [parameter["name"]])
        #     parameter["name"] = list_index

        if parameter["name"] in ["user_name", "username", "password"]:
            _add_key(assign, "nolog", True)

        if parameter.get("required"):
            if list_index == parameter["name"]:
                pass
            else:
                _add_key(assign, "required", True)

        # "bus" option defaulting on 0
        if parameter["name"] == "bus":
            _add_key(assign, "default", 0)

        _add_key(assign, "type", python_type(parameter["type"]))
        if "enum" in parameter:
            _add_key(assign, "choices", sorted(parameter["enum"]))

        if "operationIds" in parameter:
            _add_key(assign, "operationIds", sorted(parameter["operationIds"]))

        result += astunparse.unparse(assign).rstrip("\n")
    return result


def filter_out_trusted_modules(modules):
    trusted_module_allowlist = [
        "vcenter_vm.*",
        "vcenter_folder_info",
        "vcenter_cluster_info",
        "vcenter_datacenter",
        "vcenter_datacenter_info",
        "vcenter_datastore_info",
        "vcenter_network_info",
    ]

    regexes = [re.compile(i) for i in trusted_module_allowlist]
    for m in modules:
        if any([r.match(m) for r in regexes]):
            continue
        yield m


def _indent(text_block, indent=0):
    result = ""
    for l in text_block.split("\n"):
        result += " " * indent
        result += l
        result += "\n"
    return result


class Resource:
    def __init__(self, name):
        self.name = name
        self.operations = {}


class AnsibleModuleBase:
    def __init__(self, resource, definitions):
        self.resource = resource
        self.definitions = definitions
        self.name = resource.name
        self.description = "Handle resource of type {name}".format(name=resource.name)
        self.default_operationIds = None

    def list_index(self):
        return None

    def parameters(self):
        def itera(operationId):
            for parameter in AnsibleModule._flatten_parameter(
                self.resource.operations[operationId][2], self.definitions
            ):
                name = parameter["name"]
                if name == "spec":
                    for i in parameter["subkeys"]:
                        yield i
                else:
                    yield parameter

        results = {}
        for operationId in self.default_operationIds:
            if operationId not in self.resource.operations:
                continue

            for parameter in sorted(
                itera(operationId),
                key=lambda item: (item["name"], item.get("description")),
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

        for name, result in results.items():
            if result.get("enum"):
                result["enum"] = sorted(set(result["enum"]))
            if result.get("required"):
                if (
                    len(set(self.default_operationIds) - set(result["operationIds"]))
                    > 0
                ):
                    result["description"] += " Required with I(state={})".format(
                        sorted(set(result["operationIds"]))
                    )
                del result["required"]
                result["required_if"] = sorted(set(result["operationIds"]))

        results["state"] = {
            "name": "state",
            "default": "present",
            "type": "str",
            "enum": sorted(list(self.default_operationIds)),
        }

        return sorted(results.values(), key=lambda item: item["name"])

    def gen_url_func(self):
        first_operation = list(self.resource.operations.values())[0]
        path = first_operation[1]

        if not path.startswith("/rest"):  # Pre 7.0.0
            path = "/rest" + path

        return self.URL.format(path=path)

    @staticmethod
    def _property_to_parameter(prop_struct, definitions):

        required_keys = prop_struct.get("required", [])
        try:
            properties = prop_struct["properties"]
        except KeyError:
            return prop_struct

        for name, v in properties.items():
            parameter = {
                "name": name,
                "type": v.get("type", "str"),  # 'str' by default, should be ok
                "description": v.get("description", ""),
                "required": True if name in required_keys else False,
            }

            if "$ref" in v:
                ref = definitions.get(v)
                if "properties" in ref:
                    unsorted_subkeys = AnsibleModule._property_to_parameter(
                        definitions.get(v), definitions
                    )
                    parameter["type"] = "dict"
                    subkeys = sorted(unsorted_subkeys, key=lambda item: item["name"])
                    parameter["subkeys"] = list(subkeys)
                else:
                    for k, v in ref.items():
                        parameter[k] = v

            yield parameter

    @staticmethod
    def _flatten_parameter(parameter_structure, definitions):
        for i in parameter_structure:
            if "schema" in i:
                schema = definitions.get(i["schema"])
                for j in AnsibleModule._property_to_parameter(schema, definitions):
                    yield j
            else:
                yield i

    def in_query_parameters(self):
        return [p["name"] for p in self.parameters() if p.get("in") == "query"]

    def renderer(self, target_dir):
        DEFAULT_MODULE = """
#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

DOCUMENTATION = {documentation}

IN_QUERY_PARAMETER = {in_query_parameters}

import socket
import json
from ansible.module_utils.basic import env_fallback
try:
    from ansible_module.turbo.module import AnsibleTurboModule as AnsibleModule
except ImportError:
    from ansible.module_utils.basic import AnsibleModule
from ansible_collections.vmware.vmware_rest.plugins.module_utils.vmware_rest import (
    gen_args,
    open_session,
    update_changed_flag)



def prepare_argument_spec():
    argument_spec = {{
        "vcenter_hostname": dict(
            type='str',
            required=False,
            fallback=(env_fallback, ['VMWARE_HOST']),
        ),
        "vcenter_username": dict(
            type='str',
            required=False,
            fallback=(env_fallback, ['VMWARE_USER']),
        ),
        "vcenter_password": dict(
            type='str',
            required=False,
            no_log=True,
            fallback=(env_fallback, ['VMWARE_PASSWORD']),
        ),
        "vcenter_certs": dict(
            type='bool',
            required=False,
            no_log=True,
            fallback=(env_fallback, ['VMWARE_VALIDATE_CERTS']),
        )
    }}

    {arguments}
    return argument_spec

async def get_device_info(params, session, _url, _key):
    async with session.get(_url + '/' + _key) as resp:
        _json = (await resp.json())
        entry = _json['value']
        entry['_key'] = _key
        return entry



async def list_devices(params, session):
    existing_entries = []
    _url = url(params)
    async with session.get(_url) as resp:
        _json = (await resp.json())
        devices = _json['value']
    for device in devices:
        _id = list(device.values())[0]
        existing_entries.append((await get_device_info(params, session, _url, _id)))
    return existing_entries


async def exists(params, session):
    unicity_keys = ["bus", "pci_slot_number"]
    devices = await list_devices(params, session)
    for device in devices:
        for k in unicity_keys:
            if params.get(k) is not None and device.get(k) != params.get(k):
                break
        else:
            return device



async def main( ):
    module_args = prepare_argument_spec()
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)
    session = await open_session(vcenter_hostname=module.params['vcenter_hostname'], vcenter_username=module.params['vcenter_username'], vcenter_password=module.params['vcenter_password'])
    result = await entry_point(module, session)
    module.exit_json(**result)

def url(params):
{url_func}

{entry_point_func}

if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

"""
        arguments = gen_arguments_py(self.parameters(), self.list_index())
        documentation = format_documentation(
            gen_documentation(self.name, self.description, self.parameters())
        )
        url_func = self.gen_url_func()
        entry_point_func = self.gen_entry_point_func()

        in_query_parameters = self.in_query_parameters()

        module_content = DEFAULT_MODULE.format(
            name=self.name,
            documentation=documentation,
            in_query_parameters=in_query_parameters,
            url_func=_indent(url_func, 4),
            entry_point_func=_indent(entry_point_func, 0),
            arguments=_indent(arguments, 4),
        )

        module_dir = target_dir / "plugins" / "modules"
        module_dir.mkdir(parents=True, exist_ok=True)
        module_py_file = module_dir / "{name}.py".format(name=self.name)
        with module_py_file.open("w") as fd:
            fd.write(module_content)


class AnsibleModule(AnsibleModuleBase):

    URL = """
return "https://{{vcenter_hostname}}{path}".format(**params)
"""

    def __init__(self, resource, definitions):
        super().__init__(resource, definitions)
        # TODO: We can probably do better
        self.default_operationIds = set(list(self.resource.operations.keys())) - set(
            ["get", "list"]
        )

    def gen_entry_point_func(self):
        MAIN_FUNC = """
async def entry_point(module, session):
    func = globals()["_" + module.params['state']]
    return await func(module.params, session)
"""
        main_func = ast.parse(MAIN_FUNC.format(name=self.name))

        for operation in sorted(self.default_operationIds):
            (verb, path, _) = self.resource.operations[operation]
            if not path.startswith("/rest"):  # TODO
                path = "/rest" + path
            if "$" in operation:
                print(
                    "skipping operation {operation} for {path}".format(
                        operation=operation, path=path
                    )
                )
                continue

            FUNC_NO_DATA_TPL = """
async def _{operation}(params, session):
    _url = "https://{{vcenter_hostname}}{path}".format(**params) + gen_args(params, IN_QUERY_PARAMETER)
    async with session.{verb}(_url) as resp:
        try:
            if resp.headers["Content-Type"] == "application/json":
                _json = await resp.json()
        except KeyError:
            _json = {{}}
        return await update_changed_flag(_json, resp.status, "{operation}")
"""
            FUNC_WITH_DATA_TPL = """
async def _{operation}(params, session):
    accepted_fields = []

    if "{operation}" == "create":
        _exists = await exists(params, session)
        if _exists:
            return (await update_changed_flag({{"value": _exists}}, 200, 'get'))

    spec = {{}}
    for i in accepted_fields:
        if params[i]:
            spec[i] = params[i]
    _url = "https://{{vcenter_hostname}}{path}".format(**params)
    async with session.{verb}(_url, json={{'spec': spec}}) as resp:
        try:
            if resp.headers["Content-Type"] == "application/json":
                _json = await resp.json()
        except KeyError:
            _json = {{}}
        # Update the value field with all the details
        if "{operation}" == "create" and (resp.status in [200, 201]) and "value" in _json:
            if isinstance(_json["value"], dict):
                _id = list(_json["value"].values())[0]
            else:
                _id = _json["value"]
            _json = {{"value": await get_device_info(params, session, _url, _id)}}

        return await update_changed_flag(_json, resp.status, "{operation}")
"""

            data_accepted_fields = []
            for p in self.parameters():
                if "operationIds" in p:
                    if operation in p["operationIds"]:
                        if not p.get("in") in ["path", "query"]:
                            data_accepted_fields.append(p["name"])

            if data_accepted_fields:
                func = ast.parse(
                    FUNC_WITH_DATA_TPL.format(operation=operation, verb=verb, path=path)
                ).body[0]
                func.body[0].value.elts = [
                    ast.Constant(value=i, kind=None)
                    for i in sorted(data_accepted_fields)
                ]
            else:
                func = ast.parse(
                    FUNC_NO_DATA_TPL.format(operation=operation, verb=verb, path=path,)
                ).body[0]

            main_func.body.append(func)

        return astunparse.unparse(main_func.body)


class AnsibleInfoModule(AnsibleModuleBase):

    URL_WITH_LIST = """
if params['{list_index}']:
    return "https://{{vcenter_hostname}}{path}".format(**params) + gen_args(params, IN_QUERY_PARAMETER)
else:
    return "https://{{vcenter_hostname}}{list_path}".format(**params) + gen_args(params, IN_QUERY_PARAMETER)
"""

    URL_LIST_ONLY = """
return "https://{{vcenter_hostname}}{list_path}".format(**params) + gen_args(params, IN_QUERY_PARAMETER)
"""

    URL = """
return "https://{{vcenter_hostname}}{path}".format(**params) + gen_args(params, IN_QUERY_PARAMETER)
"""

    def __init__(self, resource, definitions):
        super().__init__(resource, definitions)
        self.name = resource.name + "_info"
        self.default_operationIds = ["get", "list"]

    def list_index(self):
        if "get" not in self.resource.operations:
            return
        path = self.resource.operations["get"][1]
        m = re.search(r"{([-\w]+)}$", path)
        if m:
            return m.group(1)

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
            return self.URL.format(path=path)

    def gen_entry_point_func(self):
        FUNC = """
async def entry_point(module, session):
    async with session.get(url(module.params)) as resp:
        _json = await resp.json()
        return await update_changed_flag(_json, resp.status, "get")
"""
        return FUNC.format(name=self.name)


class Definitions:
    def __init__(self, data):
        super().__init__()
        self.definitions = data

    # e.g: #/definitions/com.vmware.vcenter.inventory.datastore_find
    @staticmethod
    def _ref_to_dotted(ref):
        return ref["$ref"].split("/")[2]

    def get(self, ref):
        dotted = self._ref_to_dotted(ref)
        v = self.definitions[dotted]
        return v


class Path:
    def __init__(self, path, value):
        super().__init__()
        self.path = path
        self.operations = {}
        self.verb = {}
        self.value = value

    def summary(self, verb):
        return self.value[verb]["summary"]


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
            if path not in paths:
                result[path.path] = path
            for verb, desc in path.value.items():
                operationId = desc["operationId"]
                path.operations[operationId] = (
                    verb,
                    path.path,
                    desc["parameters"],
                )
        return result

    @staticmethod
    def init_resources(paths):
        resources = {}
        for path in paths:
            name = path_to_name(path.path)
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
    for json_file in p.glob("*.json"):
        if str(json_file) == "7.0.0/appliance.json":
            continue
        if str(json_file) == "7.0.0/api.json":
            continue
        print("Generating modules from {}".format(json_file))
        swagger_file = SwaggerFile(json_file)
        resources = swagger_file.init_resources(swagger_file.paths.values())

        for resource in resources.values():
            if "get" in resource.operations or "list" in resource.operations:
                module = AnsibleInfoModule(
                    resource, definitions=swagger_file.definitions
                )
                if len(module.default_operationIds) > 0:
                    module.renderer(target_dir=args.target_dir)
                    module_list.append(module.name)
            module = AnsibleModule(resource, definitions=swagger_file.definitions)
            if len(module.default_operationIds) > 0:
                module.renderer(target_dir=args.target_dir)
                module_list.append(module.name)

    for module_path in [
        "{target_dir}/plugins/modules/{module}.py".format(
            target_dir=args.target_dir, module=m
        )
        for m in module_list
    ]:
        subprocess.check_call(["black", module_path])

    yaml = YAML()
    my_galaxy = args.target_dir / "galaxy.yml"
    galaxy_contents = yaml.load(my_galaxy.open("r"))
    paths_of_untrusted_modules = [
        "plugins/modules/{}.py".format(m)
        for m in filter_out_trusted_modules(module_list)
    ]
    galaxy_contents["build_ignore"] = paths_of_untrusted_modules
    with my_galaxy.open("w") as fd:
        yaml.dump(galaxy_contents, fd)


if __name__ == "__main__":
    main()
