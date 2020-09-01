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
