#!/usr/bin/env python3

import argparse
import collections
import io
import pathlib
import ruamel.yaml
import yaml


def _task_to_string(task):
    a = io.StringIO()
    _yaml = ruamel.yaml.YAML()
    _yaml.dump([task], a)
    a.seek(0)
    return a.read().rstrip()


def get_tasks(target_dir, play="main.yaml"):
    tasks = []
    current_file = target_dir / play
    _yaml = ruamel.yaml.YAML()
    _yaml.indent(sequence=4, offset=2)
    for task in _yaml.load(current_file.open()):
        if "include_tasks" in task:
            tasks += get_tasks(target_dir, play=task["include_tasks"])
        elif "import_tasks" in task:
            tasks += get_tasks(target_dir, play=task["import_tasks"])
        else:
            tasks.append(task)
    return tasks


def naive_variable_from_jinja2(raw):
    jinja2_string = raw.strip(" }{}")
    if "lookup(" in jinja2_string:
        return None
    if jinja2_string.startswith("not "):
        jinja2_string = jinja2_string[4:]
    variable = jinja2_string.split(".")[0]
    if variable == "item":
        return None
    return variable


def list_dependencies(task):
    dependencies = []
    if isinstance(task, str):
        if task[0] != "{":
            return []
        variable = naive_variable_from_jinja2(task)
        if variable:
            return [variable]
    for k, v in task.items():
        if isinstance(v, dict):
            dependencies += list_dependencies(v)
        elif isinstance(v, list):
            for i in v:
                dependencies += list_dependencies(i)
        elif not isinstance(v, str):
            pass
        elif "{{" in v:
            variable = naive_variable_from_jinja2(v)
            if variable:
                dependencies.append(variable)
        elif k == "with_items":
            dependencies.append(v.split(".")[0])
    dependencies = [i for i in dependencies if not i.startswith("_")]
    return list(set(dependencies))


def extract(tasks, collection_name):
    by_modules = collections.defaultdict(dict)
    registers = {}

    for task in tasks:
        if "name" not in task:
            continue

        if task["name"].startswith("_"):
            print(f"Skip task {task['name']} because of the _")
            continue

        depends_on = []
        for r in list_dependencies(task):
            if r not in registers:
                print(
                    f"task: {task['name']}\nCannot find key '{r}' in the known variables: {registers.keys()}"
                )
                continue
            depends_on += registers[r]

        if "register" in task:
            if task["register"].startswith("_"):
                print(f"Hiding register {task['register']} because of the _ prefix.")
                del task["register"]
            else:
                registers[task["register"]] = depends_on + [task]

        if "set_fact" in task:
            for fact_name in task["set_fact"]:
                registers[fact_name] = depends_on + [task]

        module_fqcn = None
        for key in list(task.keys()):
            if key.startswith(collection_name):
                module_fqcn = key
                break
        if not module_fqcn:
            continue

        if module_fqcn not in by_modules:
            by_modules[module_fqcn] = {
                "blocks": [],
            }
        by_modules[module_fqcn]["blocks"] += depends_on + [task]

    return by_modules


def flatten_module_examples(module_examples):
    result = ""
    blocks = module_examples["blocks"]
    seen = []

    for block in blocks:
        if block in seen:
            continue
        seen.append(block)
        result += "\n" + _task_to_string(block) + "\n"
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
            if l == 'EXAMPLES = r"""':
                in_examples_block = True
                new_content += l + "\n" + examples_section_to_inject.lstrip("\n")
            elif in_examples_block and l == '"""':
                in_examples_block = False
                new_content += l + "\n"
            elif in_examples_block:
                continue
            else:
                new_content += l + "\n"
        new_content = new_content.rstrip("\n") + "\n"
        print(f"Updating {module_name}")
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
    tasks = []
    for scenario in (
        "prepare_lab",
        "vcenter_vm_scenario1",
        "appliance",
    ):
        task_dir = (
            args.target_dir / "tests" / "integration" / "targets" / scenario / "tasks"
        )
        tasks += get_tasks(task_dir)
    extracted_examples = extract(tasks, collection_name)
    inject(args.target_dir, extracted_examples)


if __name__ == "__main__":
    main()
