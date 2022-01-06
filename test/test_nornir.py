import pytest
import sys
import os

from nornir.core.task import Task, Result

from nornir_netmiko.tasks import netmiko_send_command, netmiko_send_config
from dotmap import DotMap

from nornir_utils.plugins.functions import print_result

from nornir import InitNornir
from nornir.core.filter import F

from nornir_tasks import NornirTask
from .test_inputs import acl_vars


# ----------------------------------------------------------------------------
# VARS: Directories that store files used for testing
# ----------------------------------------------------------------------------
test_inventory = os.path.join(os.path.dirname(__file__), "test_inventory")
acl = acl_vars.acl

# ----------------------------------------------------------------------------
# BUILD_TASKS: Tasks to build the a test environment to run tests against physical devices
# ----------------------------------------------------------------------------
# PRE_TASK: Task to create test environment
def nr_create_test_env_tasks(task: Task) -> Result:
    global vty_config
    # Get the line config
    vty_config = task.run(
        name="Get vty config",
        task=netmiko_send_command,
        command_string="show run | in line vty|access-class",
    )
    vty_config = vty_config.result.splitlines()
    # Add ACLs to the switch
    acl_config = "\n".join(acl["delete"]) + "\n" + acl["base_acl"]
    task.run(
        name="Adding ACLs",
        task=netmiko_send_config,
        config_commands=acl_config.splitlines(),
    )
    # Apply ACLs to lines
    tmp_vty_config = []
    for each_line in vty_config:
        if "line vty" in each_line:
            tmp_vty_config.append(each_line)
            tmp_vty_config.append(" access-class UTEST_SSH_ACCESS in vrf-also")
    task.run(
        name="Setting VTY", task=netmiko_send_config, config_commands=tmp_vty_config
    )


# POST_TASK: Task to remove the test environment
def nr_delete_test_env_tasks(task: Task) -> Result:
    # Reverting line vty config back
    task.run(name="Reverting VTY", task=netmiko_send_config, config_commands=vty_config)
    # delete ACLs to the switch
    task.run(
        name="Deleting ACLs", task=netmiko_send_config, config_commands=acl["delete"]
    )


# ----------------------------------------------------------------------------
# FIXTURES: Run to setup the test environment
# ----------------------------------------------------------------------------
# Fixture to initialise Nornir and load inventory against
@pytest.fixture(scope="session", autouse=True)
def setup_nr_inv():
    global nr_task, nr_inv
    nr_task = NornirTask()
    nr_inv = InitNornir(
        inventory={
            "plugin": "SimpleInventory",
            "options": {
                "host_file": os.path.join(test_inventory, "hosts.yml"),
                "group_file": os.path.join(test_inventory, "groups.yml"),
            },
        }
    )


# Fixture to add vars used by all this Class
@pytest.fixture(scope="class")
def load_vars():
    global dm_task, asa_config, acl_config
    dm_task = DotMap()
    asa_config = [
        "ssh 172.17.10.0 255.255.255.0 MGMT\nssh host 10.10.109.10 MGMT",
        "http 172.17.10.0 255.255.255.0 MGMT\nhttp host 10.10.109.10 MGMT",
    ]
    acl_config = [
        "ip access-list extended TEST1\n remark TEST\n permit ip host 172.25.24.168 any",
        "ip access-list extended TEST2\n deny ip 10.100.108.224 0.0.0.31 any\n permit ip any any",
    ]


# Fixture ACLs to test running the ACL commands
@pytest.fixture(scope="class")
def setup_test_env():
    global nr_host
    # Filters the inventory to the one test hosts and adds host_vars
    nr_host = nr_inv.filter(name="TEST_DEVICE")
    nr_host.inventory.hosts["TEST_DEVICE"]["config"] = acl["base_acl"].split("\n\n")
    nr_host.inventory.hosts["TEST_DEVICE"]["show_cmd"] = acl["show"]
    # Run the Nornir tasks to setup the environment
    result = nr_host.run(task=nr_create_test_env_tasks)
    if result.failed == True:
        print_result(result)
        sys.exit(1)
    else:
        yield nr_host
    result = nr_host.run(task=nr_delete_test_env_tasks)
    if result.failed == True:
        print_result(result)


# ----------------------------------------------------------------------------
# 1. TEMPLATE: Checks Nornir tasks for creating group_var config using nornir-template
# ----------------------------------------------------------------------------
class TestNornirTemplate:
    # 1a. Tests the individual nornir-template tasks used by generate_acl_config
    def test_nr_template(self):
        err_msg = "❌ template_config: Individual Nornir template task failed"
        desired_result = (
            "ip access-list extended UTEST_SSH_ACCESS\n"
            " remark MGMT Access - VLAN810\n"
            " permit ip 172.17.10.0 0.0.0.255 any\n"
            " remark Citrix Access\n"
            " permit ip host 10.10.109.10 any\n"
            " deny ip any any\n"
            "\n"
            "ip access-list extended UTEST_SNMP_ACCESS\n"
            " deny ip host 10.10.209.11 any\n"
            " permit ip any any\n"
            "\n"
        )
        tmp_nr_inv = nr_inv.filter(F(name=list(nr_inv.inventory.hosts.keys())[0]))
        config = tmp_nr_inv.run(
            task=nr_task.template_config,
            info="IOS/IOS-XE",
            template="cfg_iosxe_acl_tmpl.j2",
            acl=acl["wcard"],
        )
        assert str(config[list(config.keys())[0]][1].result) == desired_result, err_msg

    # 1b. Tests template creation and group_var assignment
    def test_generate_acl_config(self):
        err_msg = "❌ generate_acl_config: Nornir task for {} template creation and group_var failed"
        desired_result_iosxe = [
            "ip access-list extended UTEST_SSH_ACCESS\n remark MGMT Access - VLAN810\n permit ip 172.17.10.0 0.0.0.255 any\n remark Citrix Access\n permit ip host 10.10.109.10 any\n deny ip any any",
            "ip access-list extended UTEST_SNMP_ACCESS\n deny ip host 10.10.209.11 any\n permit ip any any",
        ]
        desired_result_nxos = [
            "ip access-list extended UTEST_SSH_ACCESS\n remark MGMT Access - VLAN810\n permit ip 172.17.10.0/24 any\n remark Citrix Access\n permit ip 10.10.109.10/32 any\n deny ip any any",
            "ip access-list extended UTEST_SNMP_ACCESS\n deny ip 10.10.209.11/32 any\n permit ip any any",
        ]
        desired_result_asa = [
            "ssh 172.17.10.0 255.255.255.0 MGMT\nssh host 10.10.109.10 MGMT",
            "http 172.17.10.0 255.255.255.0 MGMT\nhttp host 10.10.109.10 MGMT",
        ]
        nr_config = nr_task.generate_acl_config(nr_inv, acl)
        assert (
            nr_config.inventory.groups["iosxe"]["config"] == desired_result_iosxe
        ), err_msg.format("IOS-XE")
        assert (
            nr_config.inventory.groups["ios"]["config"] == desired_result_iosxe
        ), err_msg.format("IOS")
        assert (
            nr_config.inventory.groups["nxos"]["config"] == desired_result_nxos
        ), err_msg.format("NXOS")
        assert (
            nr_config.inventory.groups["asa"]["config"] == desired_result_asa
        ), err_msg.format("ASA")

    # 1c. Tests script catches that no config was generated
    def test_dont_generate_acl_config(self, capsys):
        err_msg = "❌ generate_acl_config: Failfast if no ios/iosxe/nxos/asa failed"
        desired_result = (
            "nornir_template*****************************************************************\n"
            "❌ Error: No config generated as are no objects in groups ios, iosxe, nxos or \nasa\n"
        )
        tmp_nr_inv = nr_inv.filter(F(groups__any=["wlc"]))
        try:
            nr_task.generate_acl_config(tmp_nr_inv, acl)
        except SystemExit:
            pass
        assert capsys.readouterr().out == desired_result, err_msg


# ----------------------------------------------------------------------------
# 2. FORMAT_DIFF: Tests formatting of config lists and checking the diff between ACL configs
# ----------------------------------------------------------------------------
@pytest.mark.usefixtures("load_vars")
class TestFormatAcl:
    # 2a. Test formatting ASA SSH and HTTP config for deletion (add no to cmds)
    def test_asa_del(self):
        err_msg = "❌ asa_del: ASA delete command formatting failed"
        desired_result = [
            "no ssh 172.17.10.0 255.255.255.0 MGMT",
            "no ssh host 10.10.109.10 MGMT",
            "no http 172.17.10.0 255.255.255.0 MGMT",
            "no http host 10.10.109.10 MGMT",
        ]
        assert nr_task.asa_del(asa_config) == desired_result, err_msg

    # 2b. Test formatting input ACLs into list with each ACE a list element
    def test_list_of_cmds(self):
        err_msg = "❌ list_of_cmds: Formatting config commands into a list failed"
        desired_result = [
            "ip access-list extended TEST1",
            " remark TEST",
            " permit ip host 172.25.24.168 any",
            "ip access-list extended TEST2",
            " deny ip 10.100.108.224 0.0.0.31 any",
            " permit ip any any",
        ]
        assert nr_task.list_of_cmds(acl_config) == desired_result, err_msg

    # 2c. Test formatting config into lists of commands, uses 'asa_del' and 'list_of_cmds' methods
    def test_format_config(self):
        err_msg = "❌ format_config: Formatting of ASA config ready to apply failed"
        desired_result = [
            "no ssh 172.17.10.0 255.255.255.0 MGMT",
            "no ssh host 10.10.109.10 MGMT",
            "no http 172.17.10.0 255.255.255.0 MGMT",
            "no http host 10.10.109.10 MGMT",
            "ssh 172.17.10.0 255.255.255.0 MGMT",
            "ssh host 10.10.109.10 MGMT",
            "http 172.17.10.0 255.255.255.0 MGMT",
            "http host 10.10.109.10 MGMT",
        ]
        actual_result = nr_task.format_config(dm_task, asa_config, asa_config)
        assert actual_result == desired_result, err_msg

        err_msg = "❌ format_config: Formatting of ASA config ready to apply failed"
        desired_result = [
            "no ip access-list extended TEST1",
            "no ip access-list extended TEST2",
            "ip access-list extended TEST1",
            " remark TEST",
            " permit ip host 172.25.24.168 any",
            "ip access-list extended TEST2",
            " deny ip 10.100.108.224 0.0.0.31 any",
            " permit ip any any",
        ]
        dm_task.host.delete_cmd = [
            "no ip access-list extended TEST1",
            "no ip access-list extended TEST2",
        ]
        actual_result = nr_task.format_config(dm_task, acl_config, acl_config)
        assert actual_result == desired_result, err_msg


# ----------------------------------------------------------------------------
# 3. NR_CONFIG: Checks Nornir tasks to update ACLs on devices. All tests reset failed hosts to stop other failing
# ----------------------------------------------------------------------------
@pytest.mark.usefixtures("setup_test_env")
class TestNornirCfg:
    # 3a. Tests collecting backup of ACL from device
    def test_backup_acl(self):
        err_msg = "❌ backup_acl: Task to gather backup of ACL from device failed"
        backup_acl_config = nr_host.run(task=nr_task.backup_acl, show_cmd=acl["show"])
        nr_host.data.reset_failed_hosts()
        assert (
            backup_acl_config["TEST_DEVICE"][0].result
            == "Backing up current ACL configurations"
        ), err_msg
        assert (
            backup_acl_config["TEST_DEVICE"][1].result.lstrip().replace("   ", " ")
            == acl["base_acl"].split("\n\n")[0]
        ), err_msg
        assert (
            backup_acl_config["TEST_DEVICE"][2].result.lstrip().replace("   ", " ")
            == acl["base_acl"].split("\n\n")[1]
        ), err_msg

    # 3b. Tests comparing ACLs when there are no differences
    def test_get_difference_same(self):
        err_msg_same = "❌ get_difference: Task find no differences between ACLs failed"
        result = nr_host.run(
            name="Test diff",
            task=nr_task.get_difference,
            sw_acl=acl["base_acl"],
            tmpl_acl=acl["base_acl"],
        )
        nr_host.data.reset_failed_hosts()
        assert (
            result["TEST_DEVICE"][0].result
            == "✅  No differences between configurations"
        ), err_msg_same

    ##3c. Tests comparing ACLs when there are differences
    def test_get_difference_diff(self):
        err_msg_diff = "❌ get_difference: Task find differences between ACLs failed"
        desired_result = (
            "ip access-list extended UTEST_SSH_ACCESS\n-  permit ip any any\n+  deny ip host 1.1.1.1 any\n+  \n\n"
            "ip access-list extended UTEST_SNMP_ACCESS\n-  permit ip any any\n+  deny tcp any any\n"
        )
        tmpl_acl = [
            "ip access-list extended UTEST_SSH_ACCESS\n remark MGMT Access - VLAN810\n deny ip host 1.1.1.1 any\n"
            " permit ip 172.17.10.0 0.0.0.255 any\n remark Citrix Access\n permit ip host 10.10.109.10 any\n ",
            "ip access-list extended UTEST_SNMP_ACCESS\n deny ip host 10.10.209.11 any\n deny tcp any any",
        ]
        result = nr_inv.run(
            name="Test diff",
            task=nr_task.get_difference,
            sw_acl=acl["base_acl"].split("\n\n"),
            tmpl_acl=tmpl_acl,
        )
        nr_inv.data.reset_failed_hosts()
        assert result["TEST_DEVICE"][0].result == desired_result, err_msg_diff

    # 3d. Tests applying config
    def test_apply_acl(self):
        err_msg = "❌ test_apply_acl: Test task to successfully apply ACL config failed"
        acl_config = acl["delete"].copy()
        acl_config.extend(acl["base_acl"].splitlines())
        result = nr_host.run(
            task=nr_task.apply_acl, acl_config=acl_config, backup_config=""
        )
        nr_inv.data.reset_failed_hosts()
        assert (
            result["TEST_DEVICE"][0].result == "✅  ACLs successfully updated"
        ), err_msg
        # Need to remove hostname from commands
        actual_result = []
        for each_line in result["TEST_DEVICE"][1].result.splitlines()[:-2]:
            if "#" in each_line:
                actual_result.append(each_line.split("#")[1])
        assert actual_result == acl_config, err_msg

    # 3e. Test applying config and rollback
    def test_apply_acl_rollback(self):
        err_msg = "❌ test_apply_acl: Test task to apply and rollback ACL config failed"
        acl_config = acl["delete"].copy()
        acl_config.extend(
            ["ip access-list extended UTEST_SSH_ACCESS", "deny ip any any"]
        )
        backup_config = acl["delete"].copy()
        backup_config.extend(acl["base_acl"].splitlines())
        result = nr_host.run(
            task=nr_task.apply_acl, acl_config=acl_config, backup_config=backup_config
        )
        nr_inv.data.reset_failed_hosts()
        assert (
            result["TEST_DEVICE"][0].result
            == "❌  ACL update rolled back as it broke SSH access"
        ), err_msg
        # Need to remove hostname from commands
        actual_result = []
        for each_line in result["TEST_DEVICE"][1].result.splitlines()[:-2]:
            if "#" in each_line:
                actual_result.append(each_line.split("#")[1])
        assert actual_result == acl_config, err_msg

    # 3f. Test task engine with dry_run
    def test_task_engine_dryrun(self):
        err_msg = "❌ test_task_engine: Test running all tasks as a dry_run failed"
        desired_result2 = "✅  No differences between configurations"
        result = nr_host.run(task=nr_task.task_engine, dry_run=True)
        nr_host.data.reset_failed_hosts()
        assert result["TEST_DEVICE"][2].result == desired_result2, err_msg

    # 3g. Test task engine without any changes
    def test_task_engine_nochange(self):
        err_msg = (
            "❌ test_task_engine: Test running all tasks with no change needed failed"
        )
        desired_result2 = "✅  No differences between configurations"
        result = nr_host.run(task=nr_task.task_engine, dry_run=False)
        nr_host.data.reset_failed_hosts()
        assert result["TEST_DEVICE"][2].result == desired_result2, err_msg

    # 3h. Test task engine with changes
    def test_task_engine_change(self):
        err_msg = "❌ test_task_engine: Test running all tasks with changes failed"
        desired_result2 = (
            "ip access-list extended UTEST_SNMP_ACCESS\n+  permit ip any any\n"
        )
        pre_config = [
            "ip access-list extended UTEST_SNMP_ACCESS",
            "no permit ip any any",
        ]
        nr_host.run(
            name="Set env to add ACE",
            task=netmiko_send_config,
            config_commands=pre_config,
        )
        result = nr_host.run(task=nr_task.task_engine, dry_run=False)
        nr_host.data.reset_failed_hosts()
        assert result["TEST_DEVICE"][2].result == desired_result2, err_msg
