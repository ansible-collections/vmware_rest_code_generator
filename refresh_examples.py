#!/usr/bin/env python3

import argparse
import collections
import io
import pathlib
import ruamel.yaml
import yaml


def _task_to_string(task):
    a = io.StringIO()
    yaml = ruamel.yaml.YAML()
    yaml.dump([task], a)
    a.seek(0)
    return a.read().rstrip()


def get_tasks(target_dir, *scenarios):
    tasks = []
    for scenario in scenarios:
        task_dir = target_dir / "tests" / "integration" / "targets" / scenario / "tasks"
        for _file in task_dir.glob("*"):
            yaml = ruamel.yaml.YAML()
            yaml.indent(sequence=4, offset=2)
            tasks += yaml.load(_file.open())
    return tasks


def extract(tasks, collection_name):
    by_modules = collections.defaultdict(dict)
    registers = {}

    for task in sorted(tasks, key=lambda item: (item.get("name", "")),):
        if "name" not in task:
            continue

        if task["name"].startswith("_"):
            print(f"Skip task {task['name']} because of the _")
            continue

        if "register" in task:
            if task["register"].startswith("_"):
                print(f"Hiding register {task['register']} because of the _ prefix.")
                del task["register"]
            else:
                if "name" in task:
                    registers[task["register"]] = task
                print("Task register: %s" % task["register"])

        if "set_fact" in task:
            for fact_name in task["set_fact"]:
                registers[fact_name] = task

        use_registers = []

        if "with_items" in task and "{{" in task["with_items"]:
            variable_name = task["with_items"].strip(" }{")
            use_registers.append(variable_name.split(".")[0])

        module_fqcn = None
        for key in list(task.keys()):
            if key.startswith(collection_name):
                module_fqcn = key
                break
        if not module_fqcn:
            continue

        if task[module_fqcn]:
            for value in task[module_fqcn].values():
                if not isinstance(value, str):
                    continue
                if "{" not in value:
                    continue
                variable_name = value.strip(" }{")
                use_registers.append(variable_name.split(".")[0])

        if module_fqcn not in by_modules:
            by_modules[module_fqcn] = {
                "blocks": [],
                "depends_on": [],
                "use_registers": [],
            }
        by_modules[module_fqcn]["blocks"] += [task]
        by_modules[module_fqcn]["use_registers"] += use_registers

    for module_fqcn in by_modules:
        for r in sorted(list(set(by_modules[module_fqcn]["use_registers"]))):
            if r in ["item"]:
                continue
            try:
                by_modules[module_fqcn]["depends_on"].append(registers[r])
            except KeyError:
                print(f"Cannot find definition of '{r}', ensure:")
                print("  - the variable is properly defined")
                print("  - the task that define the name has a name")
                exit(1)

    return by_modules


def flatten_module_examples(module_examples):
    result = ""
    blocks = module_examples["blocks"]
    block_names = [b["name"] for b in blocks]
    depends_on = [
        d for d in module_examples["depends_on"] if d["name"] not in block_names
    ]
    for block in depends_on + blocks:
        result += _task_to_string(block) + "\n"
    return result


def inject(target_dir, extracted_examples):
    module_dir = target_dir / "plugins" / "modules"
    for module_fqcn in extracted_examples:
        module_name = module_fqcn.split(".")[-1]
        module_path = module_dir / (module_name + ".py")
        if module_path.is_symlink():
            continue

        examples_section_to_inject = flatten_module_examples(
            extracted_examples[module_fqcn]
        )
        new_content = ""
        in_examples_block = False
        for l in module_path.read_text().split("\n"):
            if l == 'EXAMPLES = """':
                in_examples_block = True
                new_content += l + "\n" + examples_section_to_inject
            elif in_examples_block and l == '"""':
                in_examples_block = False
                new_content += l + "\n"
            elif in_examples_block:
                continue
            else:
                new_content += l + "\n"
        print(f"Updating {module_name}")
        new_content.rstrip("\n")
        module_path.write_text(new_content)


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
    galaxy_file = args.target_dir / "galaxy.yml"
    galaxy = yaml.load(galaxy_file.open())
    collection_name = f"{galaxy['namespace']}.{galaxy['name']}"
    tasks = get_tasks(args.target_dir, "vcenter_vm_scenario1", "prepare_lab")
    extracted_examples = extract(tasks, collection_name)
    inject(args.target_dir, extracted_examples)


if __name__ == "__main__":
    main()
