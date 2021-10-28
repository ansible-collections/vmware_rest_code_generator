#!/bin/bash
version=${1:-version_no_set}
# avoid PYLINTHOME is now '/home/goneri/.cache/pylint' but obsolescent '/home/goneri/.pylint.d' is found; you can safely remove the latter
rm -r ~/.pylint.d ~/.cache/pylint
# Use this script to commit an update of the vmare_rest collection
source ~/.ansible/collections/ansible_collections/vmware/vmware_rest/tests/integration/targets/init.sh
set -eux
cd ~/.ansible/collections/ansible_collections/vmware/vmware_rest
pip install pylint pycodestyle==2.7.0 pyvmomi requests voluptuous yamllint antsibull-changelog aiohttp
tox -e refresh_modules -- --next-version ${version}
mkdir -p logs
(
    rm -rf manual/source/vmware_rest_scenarios/task_outputs
    mkdir -p manual/source/vmware_rest_scenarios/task_outputs
    cd ~/.ansible/collections/ansible_collections/vmware/vmware_rest/tests/integration/targets/vcenter_vm_scenario1
    ./refresh_RETURN_block.sh
     cd ~/.ansible/collections/ansible_collections/vmware/vmware_rest/tests/integration/targets/appliance
    ./refresh_RETURN_block.sh
)
(
    cd ~/.ansible/collections/ansible_collections/goneri/utils
    ./scripts/inject_RETURN.py ~/.ansible/collections/ansible_collections/vmware/vmware_rest/manual/source/vmware_rest_scenarios/task_outputs/ ~/git_repos/ansible-collections/vmware_rest/ --config-file config/inject_RETURN.yaml
)
tox -e black
tox -e add_docs

# See: https://github.com/ansible-network/collection_prep/pull/66
git checkout -- docs/docsite/

tox -e build_manual

find docs/docsite/rst/ -name '*.rst' -exec sed -i 's,’,",g' '{}' \;

ansible-test sanity --local --python $(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")') -vvv
rm -r docs/docsite/rst/.doctrees
rm -r tests/output/.tmp
tox -e linters
git add README.md dev.md plugins docs tests/sanity/ignore-*.txt
tox -e antsibull-changelog -- release --verbose --version ${version}
git add changelogs
git commit -S -F commit_message
