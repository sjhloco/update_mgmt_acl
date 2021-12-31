import pytest
import os
import yaml
import datetime
import json

from nornir import InitNornir
from nornir.core.task import Result

from .test_data import desired_actual_cmd
from nr_val import template_task
from nr_val import input_task
from nr_val import actual_state_engine
from compliance_report import report
from compliance_report import report_file

# ----------------------------------------------------------------------------
# Directory that holds inventory files and load ACL dict (show, delete, wcard, mask, prefix)
# ----------------------------------------------------------------------------
test_inventory = os.path.join(os.path.dirname(__file__), "test_inventory")
test_data = os.path.join(os.path.dirname(__file__), "test_data")
template_dir = os.path.join(os.getcwd(), "templates/")

# ----------------------------------------------------------------------------
# Fixture to initialise Nornir and load inventory
# ----------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def load_inv_and_data():
    global nr, input_vars
    nr = InitNornir(
        inventory={
            "plugin": "SimpleInventory",
            "options": {
                "host_file": os.path.join(test_inventory, "hosts.yml"),
                "group_file": os.path.join(test_inventory, "groups.yml"),
            },
        }
    )
    with open(os.path.join(test_data, "input_data.yml"), "r") as file_content:
        input_vars = yaml.load(file_content, Loader=yaml.FullLoader)


# ----------------------------------------------------------------------------
# Tests all the methods within nornir_validate.py
# ----------------------------------------------------------------------------
class TestNornirValidate:

    # 1. TEMPLATE: Checks nornir-template rendered data is converted into a dictionary of commands
    def test_template_task(self):
        err_msg = "❌ template_task: Individual Nornir template task failed"
        desired_output = {}
        actual_output = {
            "show ip ospf neighbor": {
                "_mode": "strict",
                "192.168.255.1": {"state": "FULL"},
                "2.2.2.2": {"state": "FULL"},
            }
        }
        nr.run(
            task=template_task,
            tmpl_path=template_dir,
            input_vars=input_vars["hosts"]["TEST_HOST"],
            desired_state=desired_output,
        )
        assert actual_output == desired_output, err_msg

    # 2a. INPUT: Used by input tests to get host_var info
    def input_task_nr_task(self, task, input_file):
        task.run(task=input_task, input_file=input_file, template_task=template_task)
        return Result(host=task.host, result=task.host["desired_state"])

    # 2b. INPUT: Tests templated input_vars is assigned as a host_var (is testing templates)
    def test_input_task(self):
        err_msg = "❌ input_task: Input task to create desired_state host_var failed"
        desired_output = desired_actual_cmd.desired_state
        actual_output = nr.run(
            task=self.input_task_nr_task,
            input_file=os.path.join(test_data, "input_data.yml"),
        )
        assert actual_output["TEST_HOST"][0].result == desired_output, err_msg
        # 2c. INPUT: Tests empty input_data is caught and an nornir exception raised
        err_msg = "❌ input_task: Input task to catch bad input file (no hosts, groups or all) failed"
        desired_output = "⚠️  No validations were performed as no desired_state was generated, check input file and template"
        actual_output = nr.run(
            task=self.input_task_nr_task,
            input_file=os.path.join(test_data, "bad_input_data.yml"),
        )
        assert actual_output.failed == True
        assert actual_output["TEST_HOST"][1].result == desired_output

    # 3a. ACTUAL_STATE: Tests that empty command outputs are picked up on
    def test_actual_state_engine(self):
        err_msg = "❌ actual_state_engine: Task to catch empty command output failed"
        actual_output = actual_state_engine(
            nr.inventory.hosts["TEST_HOST"], {"show ip ospf neighbor": None}
        )
        assert actual_output == {"show ip ospf neighbor": {}}, err_msg

    # 3b. ACTUAL_STATE: Tests actual state is formattign commands properly (command data is in actual_state_data.py)
    def test_actual_state_cmds(self):
        err_msg = "❌ actual_state: Formatting of '{}' by actual_state.py is incorrect"
        for cmd_output, desired_output in zip(
            desired_actual_cmd.cmd_output.items(),
            desired_actual_cmd.actual_state.items(),
        ):
            actual_output = actual_state_engine(
                nr.inventory.hosts["TEST_HOST"], {cmd_output[0]: cmd_output[1]}
            )
            assert actual_output == {
                desired_output[0]: desired_output[1]
            }, err_msg.format(desired_output[0])

    # 4. VALIDATE: Decided not worth testing this as out of it is is only sending cmds that is not already tested
    def test_validate_task(self):
        pass


# ----------------------------------------------------------------------------
# Tests all the methods within nornir_validate.py
# ----------------------------------------------------------------------------
class TestComplianceReport:

    # 5a. COMPL_REPORT: Tests compliance report pass and ignoring empty outputs
    def test_report(self):
        state = {
            "show ip ospf neighbor": {"192.168.255.1": {"state": "FULL"}},
            "show version": None,
        }
        desired_output = {
            "failed": False,
            "result": "✅ Validation report complies, desired_state and actual_state match.",
            "report": {
                "complies": True,
                "show ip ospf neighbor": {
                    "complies": True,
                    "present": {"192.168.255.1": {"complies": True, "nested": True}},
                    "missing": [],
                    "extra": [],
                },
                "skipped": [],
            },
        }
        actual_output = report(state, state, "TEST_HOST", None)
        assert (
            actual_output == desired_output
        ), "❌ compliance_report: Report for a compliance of true failed"

        # 5b. COMPL_REPORT: Tests compliance report fail when combining the compliance from multiple commands
        desired_state = {
            "show ip ospf neighbor": {
                "_mode": "strict",
                "192.168.255.1": {"state": "FULL"},
            },
            "show etherchannel summary": {
                "Po3": {
                    "members": {"Gi0/15": {"mbr_status": "P"}},
                    "protocol": "LACP",
                    "status": "U",
                }
            },
        }
        actual_state = {
            "show ip ospf neighbor": {
                "192.168.255.1": {"state": "FULL"},
                "2.2.2.2": {"state": "FULL"},
            },
            "show etherchannel summary": {
                "Po3": {
                    "members": {"Gi0/15": {"mbr_status": "P"}},
                    "protocol": "LACP",
                    "status": "U",
                }
            },
        }
        actual_output = report(desired_state, actual_state, "TEST_HOST", None)
        desired_output = {
            "failed": True,
            "result": {
                "show ip ospf neighbor": {
                    "complies": False,
                    "present": {"192.168.255.1": {"complies": True, "nested": True}},
                    "missing": [],
                    "extra": ["2.2.2.2"],
                },
                "show etherchannel summary": {
                    "complies": True,
                    "present": {"Po3": {"complies": True, "nested": True}},
                    "missing": [],
                    "extra": [],
                },
                "complies": False,
                "skipped": [],
            },
            "report": {
                "complies": False,
                "show ip ospf neighbor": {
                    "complies": False,
                    "present": {"192.168.255.1": {"complies": True, "nested": True}},
                    "missing": [],
                    "extra": ["2.2.2.2"],
                },
                "show etherchannel summary": {
                    "complies": True,
                    "present": {"Po3": {"complies": True, "nested": True}},
                    "missing": [],
                    "extra": [],
                },
                "complies": False,
                "skipped": [],
            },
        }
        assert (
            actual_output == desired_output
        ), "❌ compliance_report: Combining report of comply true and false failed"

    # 6a. REPORT_FILE: Test saving a report to file, validate the contents
    def test_report_file(self):
        report = {
            "show ip ospf neighbor": {
                "complies": True,
                "present": {"192.168.255.1": {"complies": True, "nested": True}},
                "missing": [],
                "extra": [],
            }
        }
        report_file("TEST_HOST", test_data, report, True, [])
        filename = os.path.join(
            test_data,
            "TEST_HOST" + "_compliance_report_" + str(datetime.date.today()) + ".json",
        )
        assert (
            os.path.exists(filename) == True
        ), "❌ report_file: Creation of saved report failed"
        desired_output = {
            "complies": True,
            "skipped": [],
            "show ip ospf neighbor": {
                "complies": True,
                "present": {"192.168.255.1": {"complies": True, "nested": True}},
                "missing": [],
                "extra": [],
            },
        }
        with open(filename, "r") as file_content:
            report_from_file = json.load(file_content)
        assert (
            report_from_file == desired_output
        ), "❌ report_file: Saved report contents are incorrect"

        # 6b. REPORT_FILE: Updating existing file and compliance state
        report = {
            "show etherchannel summary": {
                "complies": False,
                "present": {"Po3": {"complies": True, "nested": True}},
                "missing": [],
                "extra": [],
            }
        }
        report_file("TEST_HOST", test_data, report, False, [])
        desired_output = {
            "complies": False,
            "skipped": [],
            "show ip ospf neighbor": {
                "complies": True,
                "present": {"192.168.255.1": {"complies": True, "nested": True}},
                "missing": [],
                "extra": [],
            },
            "show etherchannel summary": {
                "complies": False,
                "present": {"Po3": {"complies": True, "nested": True}},
                "missing": [],
                "extra": [],
            },
        }
        with open(filename, "r") as file_content:
            report_from_file = json.load(file_content)
        assert (
            report_from_file == desired_output
        ), "❌ report_file: Extending report and updating compliance failed"
        os.remove(filename)
