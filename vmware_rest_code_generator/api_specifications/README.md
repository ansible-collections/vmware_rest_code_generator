# How to generate the OpenAPI3 description files

```bash
#!/bin/bash
set -eux
rm -rf ~/tmp/venv-vmware-openapi
python3 -m venv ~/tmp/venv-vmware-openapi
source ~/tmp/venv-vmware-openapi/bin/activate
pip install --upgrade git+https://github.com/vmware/vsphere-automation-sdk-python.git
git clone https://github.com/vmware/vmware-openapi-generator ~/tmp/vmware-openapi-generator
cd ~/tmp/vmware-openapi-generator
wget https://patch-diff.githubusercontent.com/raw/vmware/vmware-openapi-generator/pull/71.patch
git am 71.patch
rm 71.patch
mkdir -p ~/tmp/openapi/results
python vmsgen.py --insecure -vc vcenter.test -o ~/tmp/openapi/results
```
