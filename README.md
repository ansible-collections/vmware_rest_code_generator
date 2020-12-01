# vmware_rest code generator

We use this repository to generate the vmware_rest collection.

## Requirements

You need the following components on your system:

- python 3.6
- tox

## Usage

To build the modules: `tox -e refresh_modules`.

The modules will be generated in `vmware_rest` subdirectory by default. If
you want to target a specific directory:

- `tox -e refresh_modules --target-dir /somewhere/else`

You can also generate the EXAMPLES section of the modules with the
following command:

- `tox -e refresh_examples --target-dir /somewhere/else`

It will use the content of the tests/ directory to generate the examples.

## How to refresh the vmware.vmware_rest content

Install the original `vmware.vmware_rest` collection from git:

    mkdir -p ~/.ansible/collections/ansible_collections/vmware/vmware_rest
    git clone https://github.com/ansible-collections/vmware.vmware_rest ~/.ansible/collections/ansible_collections/vmware/vmware_rest

Refresh the content of the modules using this repository:

    tox -e refresh_modules,refresh_examples -- --target-dir ~/.ansible/collections/ansible_collections/vmware/vmware_rest

Refresh the `RETURN` of the modules using the test-suite:

    mkdir -p ~/.ansible/collections/ansible_collections/goneri/utils
    git clone https://github.com/goneri/ansible-collection-goneri.utils.git ~/.ansible/collections/ansible_collections/goneri/utils
    cd ~/.ansible/collections/ansible_collections/vmware/vmware_rest/tests/integration/targets/vcenter_vm_scenario1
    ./refresh_RETURN_block.sh
    cd ~/.ansible/collections/ansible_collections/goneri/utils
    ./scripts/inject_RETURN.py ~/.ansible/collections/ansible_collections/vmware/vmware_rest/manual/source/vmware_rest_scenarios/task_outputs ~/.ansible/collections/ansible_collections/vmware/vmware_rest --config-file config/inject_RETURN.yaml

Reformat the Python code of the modules using the black formatter:

    cd ~/.ansible/collections/ansible_collections/vmware/vmware_rest
    tox -e black

Refresh the content of the documentation.

    tox -e add_docs

Run `ansible-test` to validate the result:

    virtualenv -p python3.6 ~/tmp/venv-tmp-py36-vmware
    source ~/tmp/venv-tmp-py36-vmware/bin/activate
    pip install -r requirements.txt -r test-requirements.txt ansible
    ansible-test sanity --requirements --local --python 3.6 -vvv
