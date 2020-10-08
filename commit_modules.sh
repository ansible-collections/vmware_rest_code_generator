#!/bin/bash
# Use this script to commit an update of the vmare_rest collection
tox -e refresh_modules -- --target-dir ~/.ansible/collections/ansible_collections/vmware/vmware_rest
tox -e refresh_examples -- --target-dir ~/.ansible/collections/ansible_collections/vmware/vmware_rest
source ~/tmp/ansible_2.11/bin/activate
cd ~/.ansible/collections/ansible_collections/vmware/vmware_rest
set -eux
mkdir -p logs
(
    rm docs/source/vmware_rest_scenarios/task_outputs/*
    cd ~/.ansible/collections/ansible_collections/vmware/vmware_rest/tests/integration/targets/vcenter_vm_scenario1
    ./refresh_RETURN_block.sh
)
(
    cd ~/.ansible/collections/ansible_collections/goneri/utils
    ./scripts/inject_RETURN.py ~/.ansible/collections/ansible_collections/vmware/vmware_rest/manual/source/vmware_rest_scenarios/task_outputs/ ~/git_repos/ansible-collections/vmware_rest/ --config-file config/inject_RETURN.yaml
)
tox -e black
tox -e add_docs

(
    cd manual/source
    echo "****************************************
Manual of the vmware.vmware_rest modules
****************************************

.. toctree::
    :maxdepth: 1
" > docs.rst
    ln -s ../../docs .
    find docs/ -name '*.rst'|grep '/'|sort|sed 's,\(.*\).rst$,    \1,' >> docs.rst
    tox -e build_manual
    rm docs
)
ansible-test sanity --debug --requirements --local --skip-test future-import-boilerplate --skip-test metaclass-boilerplate --python 3.8 -vvv
git add README.md dev.md plugins docs manual tests/sanity/ignore-*.txt
git add changelogs
git commit -S -F commit_message
