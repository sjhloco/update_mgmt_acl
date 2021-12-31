from typing import Any, Dict, List
import logging
import argparse
import yaml
from collections import defaultdict
import os
import sys

from nornir import InitNornir
from nornir.core.task import Task, Result
from nornir_jinja2.plugins.tasks import template_file
from nornir_utils.plugins.tasks.data import load_yaml
from nornir_netmiko.tasks import netmiko_send_command
from nornir_utils.plugins.functions import print_result

# Needed so can find modules when is import into another script
sys.path.insert(0, "nornir_validate")
from templates.actual_state import format_actual_state
from compliance_report import report

# ----------------------------------------------------------------------------
# Manually defined variables and user input
# ----------------------------------------------------------------------------
# Name of the input variable file (needs its full path)
input_file = "input_data.yml"
# Enter a directory location to save compliance report to file
report_directory = None

# ----------------------------------------------------------------------------
# Input Arguments
# ----------------------------------------------------------------------------
def _create_parser() -> Dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--directory",
        default=report_directory,
        help="Directory where to save the compliance report",
    )
    parser.add_argument(
        "-f",
        "--filename",
        default=input_file,
        help="Name (with full path) of the input Yaml file of validation variables",
    )
    return vars(parser.parse_args())


# ----------------------------------------------------------------------------
# 1. Import input vars creating host_var of desired state
# ----------------------------------------------------------------------------
def input_task(task: Task, input_file: str, template_task: str) -> str:
    desired_state: Dict[str, Any] = {}
    # Needed incase importing the module
    if "validation_builder" in os.getcwd():
        tmpl_path = os.path.join(os.path.dirname(os.getcwd()), "templates/")
    elif "nornir_validate" in os.getcwd():
        tmpl_path = "templates/"
    else:
        tmpl_path = "nornir_validate/templates/"

    # 1a. LOAD: Load the the input file
    input_vars = task.run(task=load_yaml, file=input_file)
    # 1b. TMPL: Create the desired_state for each feature to be validated (double 'if' to stop error if top level dict not exist)
    if input_vars.result.get("hosts") != None:
        if input_vars.result["hosts"].get(str(task.host)) != None:
            task.run(
                task=template_task,
                tmpl_path=tmpl_path,
                input_vars=input_vars.result["hosts"][str(task.host)],
                desired_state=desired_state,
            )
    if input_vars.result.get("groups") != None:
        if input_vars.result["groups"].get(str(task.host.groups[0])) != None:
            task.run(
                task=template_task,
                tmpl_path=tmpl_path,
                input_vars=input_vars.result["groups"][str(task.host.groups[0])],
                desired_state=desired_state,
            )
    if input_vars.result.get("all") != None:
        task.run(
            task=template_task,
            tmpl_path=tmpl_path,
            input_vars=input_vars.result["all"],
            desired_state=desired_state,
        )
    # 1c. VAR: Create host_var of combined desired states or exits if nothing to be validated
    if len(desired_state) == 0:
        result_text = u"\u26A0\uFE0F  No validations were performed as no desired_state was generated, check input file and template"
        return Result(host=task.host, failed=True, result=result_text)
    else:
        task.host["desired_state"] = desired_state


# ----------------------------------------------------------------------------
# 2. Creates desired state YML from template and serializes it
# ----------------------------------------------------------------------------
def template_task(
    task: Task, tmpl_path: str, input_vars: str, desired_state: Dict[str, Any]
) -> str:
    for val_feature, feature_vars in input_vars.items():
        tmp_desired_state = task.run(
            task=template_file,
            template="desired_state.j2",
            path=tmpl_path,
            feature=val_feature,
            input_vars=feature_vars,
        ).result
        # Converts jinja string into yaml and list of dicts [cmd: {seq: ket:val}] into a dict of cmds {cmd: {seq: key:val}}
        for each_list in yaml.load(tmp_desired_state, Loader=yaml.SafeLoader):
            desired_state.update(each_list)


# ----------------------------------------------------------------------------
# 3. Creates actual state by formatting cmd outputs
# ----------------------------------------------------------------------------
def actual_state_engine(host: "Nornir", cmd_output: Dict[str, List]) -> Dict[str, Dict]:
    actual_state: Dict[str, Any] = {}
    os_type: List = []

    # 3a. Gets os_type from host_var OS types (platform)
    os_type.append(host.platform)
    os_type.append(host.get_connection_parameters("scrapli").platform)
    os_type.append(host.get_connection_parameters("netmiko").platform)
    os_type.append(host.get_connection_parameters("napalm").platform)
    # 3b. Loops through getting command and output from the command
    for cmd, output in cmd_output.items():
        tmp_dict = defaultdict(dict)
        # EMPTY: If output is empty just adds an empty dictionary
        if output == None:
            actual_state[cmd] = tmp_dict
        else:
            format_actual_state(os_type, cmd, output, tmp_dict, actual_state)

    return actual_state


# ----------------------------------------------------------------------------
# 4. Formats gathered output as actual state and runs compliance report
# ----------------------------------------------------------------------------
def validate_task(
    task: Task, input_file: str = input_file, directory: str = report_directory
) -> str:
    task.run(
        task=input_task,
        input_file=input_file,
        template_task=template_task,
        severity_level=logging.DEBUG,
    )
    cmd_output = {}

    # 4a. CMD: Using commands from the desired output gathers the actual config form the device
    for each_cmd in task.host["desired_state"]:
        cmd_output[each_cmd] = task.run(
            task=netmiko_send_command,
            command_string=each_cmd,
            use_textfsm=True,
            severity_level=logging.DEBUG,
        ).result
    # 4b. ACTUAL: Formats the returned data into dict of cmds {cmd: {seq: key:val}} same as desired_state
    actual_state = actual_state_engine(task.host, cmd_output)
    # 4c. VAL: Uses Napalm_validate validate method to generate a compliance report
    comp_result = report(
        task.host["desired_state"], actual_state, str(task.host), directory
    )
    # 4d. RSLT: Nornir returns compliance result or if fails the compliance report
    return Result(
        host=task.host,
        failed=comp_result["failed"],
        result=comp_result["result"],
        report=comp_result["report"],
    )


# ----------------------------------------------------------------------------
# Runs the script
# ----------------------------------------------------------------------------
def main():
    args = _create_parser()
    nr = InitNornir(config_file="config.yml")
    result = nr.run(
        task=validate_task, input_file=args["filename"], directory=args["directory"]
    )
    print_result(result)


if __name__ == "__main__":
    main()
