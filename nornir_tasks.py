from typing import Any, Dict, List
import getpass
import sys
import socket
import logging
import difflib
import getpass
import yaml

from rich.console import Console
from rich.theme import Theme

from nornir.core.filter import F

from nornir.core.task import Task, Result
from nornir_utils.plugins.functions import print_title, print_result
from nornir_jinja2.plugins.tasks import template_file

from nornir_netmiko.tasks import netmiko_send_command, netmiko_send_config

from nornir_validate.nr_val import validate_task

# from validate.actual_state import actual_state_engine
# from validate.custom_validate import compliance_report


class NornirTask:
    def __init__(self):
        my_theme = {"repr.ipv4": "none", "repr.number": "none", "repr.call": "none"}
        self.rc = Console(theme=Theme(my_theme))

    # ----------------------------------------------------------------------------
    # TMPL: Nornir task to renders the template and ACL_VAR input to produce the config
    # ----------------------------------------------------------------------------
    def template_config(
        self, task: Task, info: str, template: str, acl: Dict[str, Any]
    ) -> Result:
        task.run(
            task=template_file,
            name=f"Generating {info} configuration",
            template=template,
            path="templates/",
            acl_vars=acl,
        )

    # ----------------------------------------------------------------------------
    # BACKUP: Gets backup of ACLs, summary message rather than the result is printed
    # ----------------------------------------------------------------------------
    def backup_acl(self, task: Task, show_cmd: List) -> str:
        for each_cmd in show_cmd:
            task.run(
                task=netmiko_send_command,
                command_string=each_cmd,
                severity_level=logging.DEBUG,
            )
        return "Backing up current ACL configurations"

    # ----------------------------------------------------------------------------
    # FORMAT_CFG: Formats config cmds aswell as the ASA show cmds
    # ----------------------------------------------------------------------------
    # ASA: Creates delete SSH and HTTP cmds for ASAs as doesn't use ACLs
    def asa_del(self, config):
        del_cmds = []
        for ssh_or_http in config:
            for each_cmd in ssh_or_http.splitlines():
                del_cmds.append("no " + each_cmd)
        return del_cmds

    # ACL: Converts ACLs into list of commands
    def list_of_cmds(self, acl_config):
        cmds = []
        for each_acl in acl_config:
            cmds.extend(each_acl.splitlines())
        return cmds

    # CFG: Joins delete cmds to config or backup_config ready to apply
    def format_config(self, task, config1, config2):
        config = task.host.get("delete_cmd", self.asa_del(config1)).copy()
        config.extend(self.list_of_cmds(config2))
        return config

    # ----------------------------------------------------------------------------
    # DIFF: Finds the differences between current device ACLs and templated ACLs (- is removed, + is added)
    # ----------------------------------------------------------------------------
    def get_difference(self, task: Task, sw_acl: List, tmpl_acl: List) -> Result:
        acl_diff: List = []

        for each_sw_acl, each_tmpl_acl in zip(sw_acl, tmpl_acl):
            # Creates a new ACL with just the ACL name to hold the differences
            tmp_diff_list = [each_tmpl_acl.splitlines()[0]]
            # Creates a list of common elements between and differences between the ACLs (replace removes '  ' after deny in ACLs)
            diff = difflib.ndiff(
                each_sw_acl.lstrip().replace("   ", " ").splitlines(),
                each_tmpl_acl.lstrip().splitlines(),
            )
            diff = list(diff)
            # Only takes the differences (- or +, separate loops so can group them) and removes new lines (n)
            for each_diff in diff:
                if each_diff.startswith("- "):
                    tmp_diff_list.append(each_diff.replace("\n", ""))
            for each_diff in diff:
                if each_diff.startswith("+ "):
                    tmp_diff_list.append(each_diff.replace("\n", ""))
            if len(tmp_diff_list) != 1:
                acl_diff.append(("\n").join(tmp_diff_list) + "\n")
        if len(acl_diff) == 0:
            return Result(
                host=task.host, result="✅  No differences between configurations"
            )
        elif len(acl_diff) != 0:
            return Result(host=task.host, result="\n".join(acl_diff))

    # ----------------------------------------------------------------------------
    # APPLY: Applies config, possible rollsback dependant on if it fails.
    # ----------------------------------------------------------------------------
    def apply_acl(self, task: Task, acl_config: str, backup_config: str) -> Result:
        # Manually open the connection, all tasks are run under this open connection so can rollback in same conn
        task.run(
            task=netmiko_send_config,
            dry_run=False,
            config_commands=acl_config,
            severity_level=logging.DEBUG,
        )
        # Test if can still connect over SSH, if cant rollback the change
        try:
            test_ssh = socket.socket()
            test_ssh.connect((task.host.hostname, 22))
            return Result(
                host=task.host, changed=True, result="✅  ACLs successfully updated"
            )
        except:
            task.run(
                task=netmiko_send_config,
                dry_run=False,
                config_commands=backup_config,
                severity_level=logging.DEBUG,
            )
            return Result(
                host=task.host,
                failed=True,
                result="❌  ACL update rolled back as it broke SSH access",
            )

    # ----------------------------------------------------------------------------
    # 1. TMPL_ENGINE: Engine to create device configs from templates
    # ----------------------------------------------------------------------------
    def generate_acl_config(self, nr_inv: "Nornir", acl: Dict[str, Any]) -> "Nornir":
        # Get all the members (hosts) of each group
        iosxe_nr = nr_inv.filter(F(groups__any=["ios", "iosxe"]))
        nxos_nr = nr_inv.filter(F(groups__any=["nxos"]))
        asa_nr = nr_inv.filter(F(groups__any=["asa"]))

        self.rc.print(
            "[b cyan]nornir_template*****************************************************************[/b cyan]"
        )
        # 1a. IOS: Create config (runs against first host in group), print to screen and assign as a group_var
        if len(iosxe_nr.inventory.hosts) != 0:
            iosxe_nr = iosxe_nr.filter(F(name=list(iosxe_nr.inventory.hosts.keys())[0]))
            config = iosxe_nr.run(
                task=self.template_config,
                info="IOS/IOS-XE",
                template="cfg_iosxe_acl_tmpl.j2",
                acl=acl["wcard"],
            )
            print_result(config[list(config.keys())[0]][1])
            # Creates host_vars for config (list of each ACL) and commands for show and delete ACLs
            for grp in ["ios", "iosxe"]:
                nr_inv.inventory.groups[grp]["config"] = (
                    config[list(config.keys())[0]][1].result.rstrip().split("\n\n")
                )
                nr_inv.inventory.groups[grp]["show_cmd"] = acl["show"]
                nr_inv.inventory.groups[grp]["delete_cmd"] = acl["delete"]
                # VAL: Adds prefix ACL to be used for the nornir-validate file
                nr_inv.inventory.groups[grp]["acl_val"] = {
                    "groups": {grp: acl["prefix"]}
                }

        # 1b. NXOS: Create config (runs against first host in group), print to screen and assign as a group_var
        if len(nxos_nr.inventory.hosts) != 0:
            nxos_nr = nxos_nr.filter(F(name=list(nxos_nr.inventory.hosts.keys())[0]))
            config = nxos_nr.run(
                task=self.template_config,
                info="NXOS",
                template="cfg_nxos_acl_tmpl.j2",
                acl=acl["prefix"],
            )
            print_result(config[list(config.keys())[0]][1])
            # Creates host_vars for config and commands for show and delete ACLs
            nr_inv.inventory.groups["nxos"]["config"] = (
                config[list(config.keys())[0]][1].result.rstrip().split("\n\n")
            )
            nr_inv.inventory.groups[grp]["show_cmd"] = acl["show"]
            nr_inv.inventory.groups[grp]["delete_cmd"] = acl["delete"]
            # VAL: Adds prefix ACL to be used for the nornir-validate file
            nr_inv.inventory.groups[grp]["acl_val"] = {"groups": {grp: acl["prefix"]}}

        # 1c. ASA: Create config (runs against first host in group), print to screen and assign as a group_var
        if len(asa_nr.inventory.hosts) != 0:
            asa_nr = asa_nr.filter(F(name=list(asa_nr.inventory.hosts.keys())[0]))
            config = asa_nr.run(
                task=self.template_config,
                info="ASA",
                template="cfg_asa_acl_tmpl.j2",
                acl=acl["mask"],
            )
            print_result(config[list(config.keys())[0]][1])
            # Creates host_vars for config and commands for show and delete ACLs
            nr_inv.inventory.groups["asa"]["config"] = (
                config[list(config.keys())[0]][1].result.rstrip().split("\n\n")
            )
            # VAL: Adds prefix ACL to be used for the nornir-validate file
            nr_inv.inventory.groups[grp]["acl_val"] = {"groups": {grp: acl["prefix"]}}

        # 1d. FAILFAST: If no config generated is nothing to configure on devices
        if (
            len(iosxe_nr.inventory.hosts) == 0
            and len(nxos_nr.inventory.hosts) == 0
            and len(asa_nr.inventory.hosts) == 0
        ):
            self.rc.print(
                ":x: Error: No config generated as are no objects in groups [i]ios, iosxe, nxos[/i] or [i]asa[/i]"
            )
            sys.exit(1)
        else:
            return nr_inv

    # ----------------------------------------------------------------------------
    # 2. TASK_ENGINE: Engine to call and run nornir sub-tasks
    # ----------------------------------------------------------------------------
    def task_engine(self, task: Task, dry_run: bool) -> Result:
        # 2a.BACKUP: Gathers a backup of the current ACL configuration (ASA doesn't use ACLs so change cmd)
        result = task.run(
            task=self.backup_acl,
            show_cmd=task.host.get("show_cmd", ["show run ssh", "show run http"]),
        )
        # Creates a list with each element being an ACL
        backup_acl_config = []
        for each_acl in result[1:]:
            backup_acl_config.append(each_acl.result)

        # 2b. DIFF: Splits into a list of ACLs and uses them to gather differences
        acl_diff = task.run(
            name="ACL differences (- remove, + add)",
            task=self.get_difference,
            sw_acl=backup_acl_config,
            tmpl_acl=task.host["config"],
        )
        # 2c. DRY_RUN: If is a dry run no need to do anything else
        if dry_run == True:
            print_title(
                "DRY_RUN=TRUE: This is the configuration that would have been applied"
            )
        # 2d. APPLY: If Not a dry run and are differences apply the config
        elif dry_run == False:
            if acl_diff.result == "✅  No differences between configurations":
                print_title(
                    "DRY_RUN=False: No need for any configuration to be applied"
                )
            else:
                print_title("DRY_RUN=False: This is result of configuration applied")
                # Adds delete cmds before acl and backup cfg (ASA changes delete cmds as no ACLs)
                acl_config = self.format_config(
                    task, backup_acl_config, task.host["config"]
                )
                backup_config = self.format_config(
                    task, task.host["config"], backup_acl_config
                )
                # Runs the apply config task
                task.run(
                    task=self.apply_acl,
                    acl_config=acl_config,
                    backup_config=backup_config,
                )
                # 2e. VALIDATE: Runs nornir-validate to validate the ACL
                # task.run(task=validate_task, input_file=task.host["acl_val"])

    # ----------------------------------------------------------------------------
    # 3. CFG ENGINE: Engine to run main-task to apply config
    # ----------------------------------------------------------------------------
    def config_engine(self, nr_inv: "Nornir", dry_run: bool) -> Result:
        result = nr_inv.run(task=self.task_engine, dry_run=dry_run)
        print_result(result)

    # ##4b. TMPL_VAL: Renders the validate desired state file from the ACL_VAR input
    # def template_desired(
    #     self, task: Task, template: str, acl: Dict[str, Any]
    # ) -> Result:
    #     desired_state = {}
    #     tmp_desired_state = task.run(
    #         task=template_file,
    #         template=template,
    #         path="validate/",
    #         acl_vars=acl,
    #         severity_level=logging.DEBUG,
    #     ).result
    #     # Converts jinja string into yaml and list of dicts [cmd: {seq: ket:val}] into a dict of cmds {cmd: {seq: key:val}}
    #     for each_list in yaml.load(tmp_desired_state, Loader=yaml.SafeLoader):
    #         desired_state.update(each_list)
    #     breakpoint()
    #     return desired_state

    # Builds desired config used for validation after ACL applied
    # desired_state = iosxe_nr.run(
    #     task=self.template_desired,
    #     template="desired_state.j2",
    #     acl=acl["prefix"],
    # )
    # nr_fltr.inventory.groups["ios"]["desired_state"] = desired_state[
    #     list(desired_state.keys())[0]
    # ][1].result
    # nr_fltr.inventory.groups["iosxe"]["desired_state"] = desired_state[
    #     list(desired_state.keys())[0]
    # ][1].result

    # # 4h, APPLY: Validates ACL actual state against desired state
    # def validate_task(task: Task) -> str:
    #     cmd_output = {}
    #     # Using commands from the desired output gathers the actual config from the device
    #     for each_cmd in task.host.desired_state.keys():
    #         cmd_output[each_cmd] = task.run(
    #             task=netmiko_send_command,
    #             command_string=each_cmd,
    #             use_textfsm=True,
    #             severity_level=logging.DEBUG,
    #         ).result
    #     # Formats the returned data into dict of cmds {cmd: {seq: key:val}} same as desired_state
    #     actual_state = actual_state_engine(str(task.host.groups[0]), cmd_output)
    #     # Uses Napalm_validate validate method to generate a compliance report
    #     comply_result = compliance_report(task.host.desired_state, actual_state)
    #     # f Nornir returns compliance result or if fails the compliance report
    #     return Result(
    #         host=task.host,
    #         failed=comply_result["failed"],
    #         result=comply_result["result"],
    #     )


# # def verify_acl_config(task):
# #     pass
# #     # Can get the output in parsed from so just need to inport custme validate and use
# #     # cmd['ET-6509E-VSS-01'].scrapli_response.genie_parse_output()
# # acl_vars = format_input_vars()
# # # print_title("Playbook to configure the network")
# # result = tmp_host_nr.run(task=generate_acl_config)
# # # print(acl_config)
# # # result1 = nr.run(task=apply_acl_config)
# # # breakpoint()
# # # print_result(result1, vars=['test'])
# # # print_result(result)


# #     def verify_config(self):
# #         pass
# # c = Connection(hostname='Router',
# #                             start=['mock_device_cli --os ios --state login'],
# #                             os='ios',
# #                             username='cisco',
# #                             tacacs_password='cisco',
# #                             enable_password='cisco')
# # c.connect()

# def apply_acl(self, task: Task, acl_config: str, backup_config: str) -> Result:
# Manually open the connection, all tasks are run under this open connection so can rollback in same conn
