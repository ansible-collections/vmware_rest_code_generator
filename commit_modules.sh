#!/bin/bash
# Use this script to commit an update of the vmare_rest collection
tox -e refresh_modules -- --target-dir ~/.ansible/collections/ansible_collections/vmware/vmware_rest
tox -e refresh_examples -- --target-dir ~/.ansible/collections/ansible_collections/vmware/vmware_rest
source ~/tmp/ansible_2.11/bin/activate
cd ~/.ansible/collections/ansible_collections/vmware/vmware_rest
set -eux
mkdir -p logs
(
    rm -rf manual/source/vmware_rest_scenarios/task_outputs
    mkdir -p manual/source/vmware_rest_scenarios/task_outputs
    cd ~/.ansible/collections/ansible_collections/vmware/vmware_rest/tests/integration/targets/vcenter_vm_scenario1
    ./refresh_RETURN_block.sh
)
tox -e build_manual
tox -e black
ansible-test sanity --debug --requirements --local --skip-test future-import-boilerplate --skip-test metaclass-boilerplate --python 3.8 -vvv
tox -e add_docs
git add README.md dev.md plugins docs tests/sanity/ignore-*.txt
git add changelogs
git commit -S -F commit_message
