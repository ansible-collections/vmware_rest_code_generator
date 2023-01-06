import ast
import pytest
import types

from unittest.mock import patch


import gouttelette.cmd.refresh_modules as rm

my_parameters = [
    {"name": "aaa", "type": "boolean", "description": "a second parameter"},
    {
        "name": "aaa",
        "type": "integer",
        "required": True,
        "description": "a second parameter. the field must contain identifiers for the resource type: vcenter.vm.hardware.Disk.",
        "subkeys": {
            "a_subkey": {
                "type": "ccc",
                "name": "a_subkey",
                "description": "more blabla",
                "required": True,
                "_operationIds": ["get", "list"],
                "_required_with_operations": ["list"],
            }
        },
    },
    {
        "name": "ccc",
        "type": "str",
        "description": "3rd parameter is ':' enum,\n\nand this string is long and comes with a ' on purpose. This way, we can use it to ensure format_documentation() can break it up.",
        "enum": ["a", "c", "b"],
    },
]


documentation_data_input = {
    "author": ["Goneri Le Bouder (@goneri) <goneri@lebouder.net>"],
    "description": "bar",
    "module": "foo",
    "notes": ["Tested on vSphere 7.0.2"],
    "options": {
        "aaa": {
            "description": [
                "a second parameter. the field must "
                "contain the id of resources returned by "
                "M(vcenter_vm_hardware_disk).",
                "Valid attributes are:",
                " - C(a_subkey) (ccc): more blabla",
            ],
            "required": True,
            "type": "int",
        },
        "ccc": {
            "choices": ["a", "b", "c"],
            "description": [
                "3rd parameter is ':' enum,",
                "",
                "and this string is long and comes with a "
                "' on purpose. This way, we can use it to "
                "ensure format_documentation() can break "
                "it up.",
            ],
            "type": "str",
        },
        "vcenter_hostname": {
            "description": [
                "The hostname or IP address " "of the vSphere vCenter",
                "If the value is not "
                "specified in the task, the "
                "value of environment "
                "variable C(VMWARE_HOST) "
                "will be used instead.",
            ],
            "required": True,
            "type": "str",
        },
        "vcenter_password": {
            "description": [
                "The vSphere vCenter " "password",
                "If the value is not "
                "specified in the task, the "
                "value of environment "
                "variable C(VMWARE_PASSWORD) "
                "will be used instead.",
            ],
            "required": True,
            "type": "str",
        },
    },
    "requirements": ["python >= 3.6", "aiohttp"],
    "short_description": "bar",
    "version_added": "1.0.0",
}

my_raw_paths_data = {
    "/rest/vcenter/vm/{vm}": {
        "get": {
            "operationId": "get",
            "parameters": [
                {
                    "description": "Id of the VM",
                    "in": "path",
                    "name": "vm",
                    "required": True,
                    "type": "string",
                }
            ],
            "summary": "",
            "responses": {
                "200": {
                    "description": "Information about the VM.",
                    "schema": {"$ref": "#/definitions/vcenter.VM_resp"},
                },
                "400": {
                    "description": "things went bad.",
                    "schema": {
                        "$ref": "#/definitions/vapi.std.errors.resource_inaccessible_error"
                    },
                },
            },
        }
    },
    "/rest/vcenter/vm": {
        "get": {
            "operationId": "list",
            "parameters": [
                {
                    "collectionFormat": "multi",
                    "description": "desc of multi",
                    "in": "query",
                    "items": {"type": "string"},
                    "name": "filter.vms",
                    "type": "array",
                }
            ],
            "summary": "",
            "responses": {
                "200": {
                    "description": "A list",
                    "schema": {"$ref": "#/definitions/vcenter.VM.list_resp"},
                },
                "400": {
                    "description": "my 400 error",
                    "schema": {
                        "$ref": "#/definitions/vapi.std.errors.unable_to_allocate_resource_error"
                    },
                },
            },
        }
    },
}


my_raw_paths_data_with_param_in_path = {
    "/rest/vcenter/vm-template/library-items/{template_library_item}/check-outs": {
        "post": {
            "consumes": ["application/json"],
            "operationId": "check_out",
            "parameters": [
                {
                    "description": "Identifier of the content library item containing the source virtual machine template to be checked out.",
                    "in": "path",
                    "name": "template_library_item",
                    "required": True,
                    "type": "string",
                },
                {
                    "in": "body",
                    "name": "request_body",
                    "schema": {
                        "$ref": "#/definitions/vcenter.vm_template.library_items.check_outs_check_out"
                    },
                },
                {
                    "description": "action=check-out",
                    "enum": ["check-out"],
                    "in": "query",
                    "name": "action",
                    "required": True,
                    "type": "string",
                },
            ],
            "summary": "",
            "responses": {
                "200": {
                    "description": "Identifier of the virtual machine that was checked out of the library item.",
                    "schema": {
                        "$ref": "#/definitions/vcenter.vm_template.library_items.check_outs.check_out_resp"
                    },
                }
            },
        }
    },
    "/rest/vcenter/vm-template/library-items/{template_library_item}/check-outs/{vm}": {
        "post": {
            "consumes": ["application/json"],
            "operationId": "check_in",
            "parameters": [
                {
                    "description": "Identifier of the content library item in which the virtual machine is checked in.",
                    "in": "path",
                    "name": "template_library_item",
                    "required": True,
                    "type": "string",
                },
                {
                    "description": "Identifier of the virtual machine to check into the library item.",
                    "in": "path",
                    "name": "vm",
                    "required": True,
                    "type": "string",
                },
                {
                    "in": "body",
                    "name": "request_body",
                    "schema": {
                        "$ref": "#/definitions/vcenter.vm_template.library_items.check_outs_check_in"
                    },
                },
                {
                    "description": "action=check-in",
                    "enum": ["check-in"],
                    "in": "query",
                    "name": "action",
                    "required": True,
                    "type": "string",
                },
            ],
            "summary": "",
            "responses": {
                "200": {
                    "description": "The new version of the library item.",
                    "schema": {
                        "$ref": "#/definitions/vcenter.vm_template.library_items.check_outs.check_in_resp"
                    },
                },
            },
        }
    },
}


my_definitions = {
    "vcenter.VM.list_resp": {
        "properties": {
            "value": {
                "items": {"$ref": "#/definitions/vcenter.VM.summary"},
                "type": "array",
            }
        },
        "required": ["value"],
        "type": "object",
    },
    # vm_template related definitions
    "vcenter.vm_template.library_items.check_outs_check_in": {
        "properties": {
            "spec": {
                "$ref": "#/definitions/vcenter.vm_template.library_items.check_outs.check_in_spec",
                "description": "Specification used to check in the virtual machine into the library item.",
            }
        },
        "type": "object",
    },
    "vcenter.vm_template.library_items.check_outs_check_out": {
        "properties": {
            "spec": {
                "$ref": "#/definitions/vcenter.vm_template.library_items.check_outs.check_out_spec",
                "description": "Specification used to check out the source virtual machine template as a virtual machine.",
            }
        },
        "type": "object",
    },
    "vcenter.vm_template.library_items.check_outs.check_out_spec": {
        "properties": {
            "name": {
                "description": "Name of the virtual machine to check out of the library item.",
                "type": "string",
            },
            "placement": {
                "$ref": "#/definitions/vcenter.vm_template.library_items.check_outs.placement_spec",
                "description": "Information used to place the checked out virtual machine.",
            },
            "powered_on": {
                "description": "Specifies whether the virtual machine should be powered on after check out.",
                "type": "boolean",
            },
        },
        "type": "object",
    },
    "vcenter.vm_template.library_items.check_outs.placement_spec": {
        "properties": {
            "cluster": {
                "description": "Cluster onto which the virtual machine should be placed. If {@name #cluster} and {@name #resourcePool} are both specified, {@name #resourcePool} must belong to {@name #cluster}. If {@name #cluster} and {@name #host} are both specified, {@name #host} must be a member of {@name #cluster}.",
                "type": "string",
            },
            "folder": {
                "description": "Virtual machine folder into which the virtual machine should be placed.",
                "type": "string",
            },
            "host": {
                "description": "Host onto which the virtual machine should be placed. If {@name #host} and {@name #resourcePool} are both specified, {@name #resourcePool} must belong to {@name #host}. If {@name #host} and {@name #cluster} are both specified, {@name #host} must be a member of {@name #cluster}.",
                "type": "string",
            },
            "resource_pool": {
                "description": "Resource pool into which the virtual machine should be placed.",
                "type": "string",
            },
        },
        "type": "object",
    },
    "vcenter.vm_template.library_items.check_outs.check_in_spec": {
        "properties": {
            "message": {
                "description": "Message describing the changes made to the virtual machine.",
                "type": "string",
            }
        },
        "required": ["message"],
        "type": "object",
    },
}


def test_description_normalize():
    assert rm.Description.normalize(["a", "b"]) == ["a", "b"]
    assert rm.Description.normalize(["{@name DayOfWeek}"]) == ["day of the week"]
    assert rm.Description.normalize([" {@term enumerated type}"]) == [""]
    assert rm.Description.normalize(
        ["increased if Cpu.Info.hot-add-enabled is true"]
    ) == ["increased if I(hot_add_enabled) is true"]
    assert rm.Description.normalize(["Aa.Rather Aa.RatherLonger Aa.RatherSmaller"]) == [
        "I(rather) I(rather_longer) I(rather_smaller)"
    ]


def test_description_ref_to_parameter():
    assert rm.Description.ref_to_parameter("Abb.Bccc.Ccc-aaa-eee") == "ccc_aaa_eee"


def test_python_type():
    assert rm.python_type("array") == "list"
    assert rm.python_type("list") == "list"
    assert rm.python_type("boolean") == "bool"
    assert rm.python_type("object") == "dict"
    assert rm.python_type("string") == "str"


def test_path_to_name():
    assert rm.path_to_name("/rest/cis/tasks") == "rest_cis_tasks"
    assert (
        rm.path_to_name("/rest/com/vmware/cis/tagging/category")
        == "cis_tagging_category"
    )
    assert (
        rm.path_to_name("/rest/com/vmware/cis/tagging/category/id:{category_id}")
        == "cis_tagging_category"
    )
    assert (
        rm.path_to_name(
            "/rest/com/vmware/cis/tagging/category/id:{category_id}?~action=add-to-used-by"
        )
        == "cis_tagging_category"
    )
    assert (
        rm.path_to_name("/rest/vcenter/vm/{vm}/hardware/ethernet/{nic}/disconnect")
        == "vcenter_vm_hardware_ethernet"
    )


@patch("gouttelette.cmd.refresh_modules.get_module_from_config")
def test_gen_documentation(m_get_module_from_config):
    m_get_module_from_config.return_value = {}
    added_ins = {"parameters": {}, "module": None}
    a = rm.gen_documentation("foo", "bar", my_parameters, added_ins, "1.2.3", ".")
    assert a["options"]["vcenter_password"]


def test_format_documentation():

    expectation = """r'''
module: foo
short_description: bar
description: bar
options:
    aaa:
        description:
        - a second parameter. the field must contain the id of resources returned
            by M(vcenter_vm_hardware_disk).
        - 'Valid attributes are:'
        - ' - C(a_subkey) (ccc): more blabla'
        required: true
        type: int
    ccc:
        choices:
        - a
        - b
        - c
        description:
        - 3rd parameter is ':' enum,
        - ''
        - and this string is long and comes with a ' on purpose. This way, we can
            use it to ensure format_documentation() can break it up.
        type: str
    vcenter_hostname:
        description:
        - The hostname or IP address of the vSphere vCenter
        - If the value is not specified in the task, the value of environment variable
            C(VMWARE_HOST) will be used instead.
        required: true
        type: str
    vcenter_password:
        description:
        - The vSphere vCenter password
        - If the value is not specified in the task, the value of environment variable
            C(VMWARE_PASSWORD) will be used instead.
        required: true
        type: str
author:
- Goneri Le Bouder (@goneri) <goneri@lebouder.net>
version_added: 1.0.0
requirements:
- python >= 3.6
- aiohttp
notes:
- Tested on vSphere 7.0.2
'''"""

    assert rm.format_documentation(documentation_data_input) == expectation


def test_format_documentation_quote():
    documentation = {
        "module": "a",
        "short_description": "a",
        "description": "':'",
        "options": "a",
        "author": "a",
        "version_added": "a",
        "requirements": "a",
    }
    expectation = """r\'\'\'
module: a
short_description: a
description: ':'
options: a
author: a
version_added: a
requirements: a
\'\'\'"""

    assert rm.format_documentation(documentation) == expectation


def test_gen_arguments_py(monkeypatch):
    assert isinstance(rm.gen_arguments_py([]), str)
    ret = rm.gen_arguments_py(my_parameters)
    assert (
        ret
        == """
argument_spec['aaa'] = {'type': 'bool'}
argument_spec['aaa'] = {'required': True, 'type': 'int'}
argument_spec['ccc'] = {'type': 'str', 'choices': ['a', 'b', 'c']}"""
    )


def test_SwaggerFile_load_paths():
    paths = rm.SwaggerFile.load_paths(my_raw_paths_data)
    assert paths["/rest/vcenter/vm"].operations == {
        "list": (
            "get",
            "/rest/vcenter/vm",
            [
                {
                    "collectionFormat": "multi",
                    "description": "desc of multi",
                    "in": "query",
                    "items": {"type": "string"},
                    "name": "filter.vms",
                    "type": "array",
                }
            ],
            {
                "200": {
                    "description": "A list",
                    "schema": {"$ref": "#/definitions/vcenter.VM.list_resp"},
                },
                "400": {
                    "description": "my 400 error",
                    "schema": {
                        "$ref": "#/definitions/vapi.std.errors.unable_to_allocate_resource_error"
                    },
                },
            },
        ),
    }


def test_SwaggerFile_init_resources():
    paths = rm.SwaggerFile.load_paths(my_raw_paths_data)
    resources = rm.SwaggerFile.init_resources(paths.values())

    assert resources["vcenter_vm"].name == "vcenter_vm"
    assert resources["vcenter_vm"].operations == {
        "get": (
            "get",
            "/rest/vcenter/vm/{vm}",
            [
                {
                    "description": "Id of the VM",
                    "in": "path",
                    "name": "vm",
                    "required": True,
                    "type": "string",
                }
            ],
            {
                "200": {
                    "description": "Information about the VM.",
                    "schema": {"$ref": "#/definitions/vcenter.VM_resp"},
                },
                "400": {
                    "description": "things went bad.",
                    "schema": {
                        "$ref": "#/definitions/vapi.std.errors.resource_inaccessible_error"
                    },
                },
            },
        ),
        "list": (
            "get",
            "/rest/vcenter/vm",
            [
                {
                    "collectionFormat": "multi",
                    "description": "desc of multi",
                    "in": "query",
                    "items": {"type": "string"},
                    "name": "filter.vms",
                    "type": "array",
                }
            ],
            {
                "200": {
                    "description": "A list",
                    "schema": {"$ref": "#/definitions/vcenter.VM.list_resp"},
                },
                "400": {
                    "description": "my 400 error",
                    "schema": {
                        "$ref": "#/definitions/vapi.std.errors.unable_to_allocate_resource_error"
                    },
                },
            },
        ),
    }


# AnsibleModuleBaseVmware
def test_AnsibleModuleBaseVmware():
    paths = rm.SwaggerFile.load_paths(my_raw_paths_data)
    resources = rm.SwaggerFile.init_resources(paths.values())
    definitions = rm.Definitions(my_definitions)
    module = rm.AnsibleModuleBaseVmware(resources["vcenter_vm"], definitions)
    assert module.name == "vcenter_vm"


# AnsibleInfoModule
# AnsibleInfoModule
def test_payload():
    paths = rm.SwaggerFile.load_paths(my_raw_paths_data)
    resources = rm.SwaggerFile.init_resources(paths.values())
    definitions = rm.Definitions(my_definitions)
    module = rm.AnsibleModuleBaseVmware(resources["vcenter_vm"], definitions)
    assert module.payload() == {}
    module = rm.AnsibleInfoModule(resources["vcenter_vm"], definitions)
    assert module.payload() == {
        "get": {"body": {}, "path": {"vm": "vm"}, "query": {}},
        "list": {"body": {}, "path": {}, "query": {"filter.vms": "filter.vms"}},
    }
    paths = rm.SwaggerFile.load_paths(my_raw_paths_data_with_param_in_path)
    resources = rm.SwaggerFile.init_resources(paths.values())
    definitions = rm.Definitions(my_definitions)
    module = rm.AnsibleInfoModule(
        resources["vcenter_vmtemplate_libraryitems_checkouts"], definitions
    )
    assert module.payload() == {}


def test_AnsibleInfoModule_parameters():
    paths = rm.SwaggerFile.load_paths(my_raw_paths_data)
    resources = rm.SwaggerFile.init_resources(paths.values())
    definitions = rm.Definitions(my_definitions)
    module = rm.AnsibleInfoModule(resources["vcenter_vm"], definitions)
    assert module.name == "vcenter_vm_info"
    assert module.parameters() == [
        {
            "_loc_in_payload": "filter.vms",
            "_required_with_operations": [],
            "description": "desc of multi",
            "elements": "string",
            "in": "query",
            "name": "filter.vms",
            "operationIds": ["list"],
            "required": None,
            "type": "array",
        },
        {
            "_loc_in_payload": "vm",
            "_required_with_operations": ["get"],
            "description": "Id of the VM Required with I(state=['get'])",
            "in": "path",
            "name": "vm",
            "operationIds": ["get"],
            "type": "string",
        },
    ]


# AnsibleModuleBaseVmware
def test_AnsibleModule_parameters():
    paths = rm.SwaggerFile.load_paths(my_raw_paths_data)
    resources = rm.SwaggerFile.init_resources(paths.values())
    definitions = rm.Definitions(my_definitions)
    module = rm.AnsibleModuleBaseVmware(resources["vcenter_vm"], definitions)
    assert module.name == "vcenter_vm"
    assert module.parameters() == [{"enum": [], "name": "state", "type": "str"}]


# AnsibleModuleBaseVmware - with complex URL
def test_AnsibleModule_parameters_complex():
    paths = rm.SwaggerFile.load_paths(my_raw_paths_data_with_param_in_path)
    resources = rm.SwaggerFile.init_resources(paths.values())
    definitions = rm.Definitions(my_definitions)
    module = rm.AnsibleModuleBaseVmware(
        resources["vcenter_vmtemplate_libraryitems_checkouts"], definitions
    )
    assert module.name == "vcenter_vmtemplate_libraryitems_checkouts"
    assert module.parameters() == [
        {
            "_loc_in_payload": "action",
            "_required_with_operations": ["check_in", "check_out"],
            "description": "action=check-out This parameter is mandatory.",
            "enum": ["check-in", "check-out"],
            "in": "query",
            "name": "action",
            "operationIds": ["check_in", "check_out"],
            "required": True,
            "type": "string",
        },
        {
            "_loc_in_payload": "spec/message",
            "_required_with_operations": ["check_in"],
            "description": "Message describing the changes made to the virtual machine. "
            "Required with I(state=['check_in'])",
            "in": None,
            "name": "message",
            "operationIds": ["check_in"],
            "type": "string",
        },
        {
            "_loc_in_payload": "spec/name",
            "_required_with_operations": [],
            "description": "Name of the virtual machine to check out of the library "
            "item.",
            "in": None,
            "name": "name",
            "operationIds": ["check_out"],
            "required": False,
            "type": "string",
        },
        {
            "_loc_in_payload": "spec/placement",
            "_required_with_operations": [],
            "description": "Information used to place the checked out virtual machine.",
            "elements": "dict",
            "in": None,
            "name": "placement",
            "operationIds": ["check_out"],
            "required": False,
            "subkeys": {
                "cluster": {
                    "_operationIds": ["check_out", "check_out"],
                    "_required_with_operations": [],
                    "description": "Cluster onto which the virtual machine should "
                    "be placed. If {@name #cluster} and {@name "
                    "#resourcePool} are both specified, {@name "
                    "#resourcePool} must belong to {@name #cluster}. "
                    "If {@name #cluster} and {@name #host} are both "
                    "specified, {@name #host} must be a member of "
                    "{@name #cluster}.",
                    "name": "cluster",
                    "type": "string",
                },
                "folder": {
                    "_operationIds": ["check_out", "check_out"],
                    "_required_with_operations": [],
                    "description": "Virtual machine folder into which the virtual "
                    "machine should be placed.",
                    "name": "folder",
                    "type": "string",
                },
                "host": {
                    "_operationIds": ["check_out", "check_out"],
                    "_required_with_operations": [],
                    "description": "Host onto which the virtual machine should be "
                    "placed. If {@name #host} and {@name "
                    "#resourcePool} are both specified, {@name "
                    "#resourcePool} must belong to {@name #host}. If "
                    "{@name #host} and {@name #cluster} are both "
                    "specified, {@name #host} must be a member of "
                    "{@name #cluster}.",
                    "name": "host",
                    "type": "string",
                },
                "resource_pool": {
                    "_operationIds": ["check_out", "check_out"],
                    "_required_with_operations": [],
                    "description": "Resource pool into which the virtual machine "
                    "should be placed.",
                    "name": "resource_pool",
                    "type": "string",
                },
            },
            "type": "object",
        },
        {
            "_loc_in_payload": "spec/powered_on",
            "_required_with_operations": [],
            "description": "Specifies whether the virtual machine should be powered on "
            "after check out.",
            "in": None,
            "name": "powered_on",
            "operationIds": ["check_out"],
            "required": False,
            "type": "boolean",
        },
        {
            "enum": ["check_in", "check_out"],
            "name": "state",
            "type": "str",
            "required": True,
        },
        {
            "_loc_in_payload": "template_library_item",
            "_required_with_operations": ["check_in", "check_out"],
            "description": "Identifier of the content library item containing the source "
            "virtual machine template to be checked out. This parameter is mandatory.",
            "in": "path",
            "name": "template_library_item",
            "operationIds": ["check_in", "check_out"],
            "required": True,
            "type": "string",
        },
        {
            "_loc_in_payload": "vm",
            "_required_with_operations": ["check_in"],
            "description": "Identifier of the virtual machine to check into the library "
            "item. Required with I(state=['check_in'])",
            "in": "path",
            "name": "vm",
            "operationIds": ["check_in"],
            "type": "string",
        },
    ]


@pytest.mark.parametrize(
    "path,name",
    [
        ("/api/vcenter/authentication/token", "vcenter_authentication_token"),
        (
            "/api/vcenter/certificate-management/vcenter/signing-certificate",
            "vcenter_certificatemanagement_vcenter_signingcertificate",
        ),
        (
            "/api/vcenter/certificate-management/vcenter/signing-certificate?action=refresh",
            "vcenter_certificatemanagement_vcenter_signingcertificate",
        ),
        ("/api/vcenter/compute/policies", "vcenter_compute_policies"),
        (
            "/api/vcenter/compute/policies/capabilities",
            "vcenter_compute_policies_capabilities",
        ),
        (
            "/api/vcenter/compute/policies/capabilities/{capability}",
            "vcenter_compute_policies_capabilities",
        ),
        (
            "/rest/vcenter/vm/{vm}/hardware/serial/{port}/disconnect",
            "vcenter_vm_hardware_serial",
        ),
        ("/rest/vcenter/vm/{vm}/library-item", "vcenter_vm_libraryitem"),
        ("/rest/vcenter/vm/{vm}/power", "vcenter_vm_power"),
        ("/rest/vcenter/vm/{vm}/power/reset", "vcenter_vm_power"),
        ("/rest/vcenter/vm/{vm}/power/start", "vcenter_vm_power"),
        ("/rest/vcenter/vm?action=instant-clone", "vcenter_vm"),
        ("/rest/vcenter/vm?action=register", "vcenter_vm"),
        ("/rest/appliance/system/version", "appliance_system_version"),
        ("/rest/appliance/timesync", "appliance_timesync"),
        ("/rest/appliance/update", "appliance_update"),
        ("/rest/appliance/update/pending", "appliance_update_pending"),
        ("/rest/appliance/update/pending/{version}", "appliance_update_pending"),
        (
            "/rest/appliance/update/pending/{version}?action=install",
            "appliance_update_pending",
        ),
        (
            "/rest/appliance/update/pending/{version}?action=precheck",
            "appliance_update_pending",
        ),
    ],
)
def test_path_to_name(path, name):
    assert rm.path_to_name(path) == name
