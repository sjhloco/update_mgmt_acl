import pytest
from update_mgmt_acl import InputValidate
import os
import yaml
from typing import Any, Dict, List
import re


# ----------------------------------------------------------------------------
# VARS: Directories that store files used for testing
# ----------------------------------------------------------------------------
test_input_dir = os.path.join(os.path.dirname(__file__), "test_inputs")
test_acl_input = "test_acl_input_data.yml"


# ----------------------------------------------------------------------------
# FIXTURES: Run to setup the test environment
# ----------------------------------------------------------------------------
# Fixture used to instanise Validate class
@pytest.fixture(scope="class")
def instanize_validate():
    global validate
    validate = InputValidate(test_input_dir)


# Fixture used to load variable file
@pytest.fixture(scope="function")
def load_acl_vars():
    global acl_vars
    with open(os.path.join(test_input_dir, test_acl_input), "r") as file_content:
        acl_vars = yaml.load(file_content, Loader=yaml.FullLoader)


# ----------------------------------------------------------------------------
# 1. FILE: Tests check to ensure contents of input file are of a valid format
# ----------------------------------------------------------------------------
@pytest.mark.usefixtures("instanize_validate")
class TestValidateFile:

    # ----------------------------------------------------------------------------
    # 1a. Tests IP address formatting errors are found
    # ----------------------------------------------------------------------------
    def test_assert_ipv4(self):
        # Tests that valid IP address formatting is found
        error: List = []
        validate._assert_ipv4(error, "10.10.10.0/24", "good_ip_mask")
        assert (
            error == []
        ), "'assert_ipv4' failed to validate good IP address and mask format"
        # Tests that IP address formatting errors are found
        error_input = dict(
            bad_ip="10.10.510.0/24",
            bad_mask="10.10.10.0/44",
            bad_ip_mask="510.10.10.0/246",
            not_ip="blah/blah",
        )
        for err_msg, err_input in error_input.items():
            error: List = []
            validate._assert_ipv4(error, err_input, f"{err_msg}")
            assert error == [
                f"{err_msg}"
            ], f"❌ assert_ipv4: Unit test for {err_msg} failed"

    # ----------------------------------------------------------------------------
    # 1b. Validation check of test file location
    # ----------------------------------------------------------------------------
    def test_assert_file_exist(self):
        err_msg = "❌ _assert_file_exist: Unit test for valid file location failed"
        actual_result = validate._assert_file_exist(
            os.path.join(test_input_dir, "test_acl_input_data.yml")
        )
        desired_result = os.path.join(test_input_dir, "test_acl_input_data.yml")
        assert actual_result == desired_result, err_msg

    # ----------------------------------------------------------------------------
    # 1c. Validates errors (not dict, key not permit/deny/remark, etc) in ACE entries are picked up
    # ----------------------------------------------------------------------------
    def test_ace_errors(self):
        err_msg = "❌ _assert_ace: Unit test 'ace' is a dictionary failed"
        desired_result = ["-ACE entry [i]'must be a dict'[/i] is not a dictionary"]
        actual_result = validate._assert_ace("must be a dict")
        assert actual_result == desired_result, err_msg

        err_msg = "❌ _assert_ace: Unit test 'ace' is valid IP address failed"
        desired_result = ["-[i]10.10.10.230/323[/i] is not a valid IP address"]
        actual_result = validate._assert_ace(dict(permit="10.10.10.230/323"))
        assert actual_result == desired_result, err_msg

        err_msg = "❌ _assert_ace: Unit test 'ace' is remark, permit or deny failed"
        desired_result = [
            "-[i]not_known[/i] is not valid, options are 'remark', 'permit' or 'deny'"
        ]
        actual_result = validate._assert_ace(dict(not_known="10.20.20.168/32"))
        assert actual_result == desired_result, err_msg

    # ----------------------------------------------------------------------------
    # 1d. Validatess check combined ACE errors are returned
    # ----------------------------------------------------------------------------
    def test_assert_acl(self):
        err_msg = "❌ _assert_acl: Unit test combined ace errors failed"
        desired_result = {
            "TEST_ACL": [
                "-ACE entry [i]'must be a dict'[/i] is not a dictionary",
                "-[i]10.10.10.230/323[/i] is not a valid IP address",
            ]
        }
        actual_result = validate._assert_acl(
            {
                "name": "TEST_ACL",
                "ace": [
                    "must be a dict",
                    dict(permit="10.10.10.230/323"),
                ],
            }
        )
        assert actual_result == desired_result, err_msg

    # ----------------------------------------------------------------------------
    # 1e. Validatess check that each ACL has a name and ACE is a list
    # ----------------------------------------------------------------------------
    def test_assert_acl1(self, capsys):
        err_msg = "❌ _assert_acl: Unit test for acl 'name' dictionary existence failed"
        desired_result = (
            "❌ AclError: ACL name is missing or the  ACE dictionary is not a list\n"
        )

        try:
            validate._assert_acl(
                {
                    "ace": [
                        {"remark": "MGMT Orion - SRVF-ORION01"},
                        {"permit": "10.20.30.16/32"},
                    ]
                }
            )
        except SystemExit:
            pass
        assert capsys.readouterr().out == desired_result, err_msg

        err_msg = "❌ _assert_acl: Unit test for 'ace' dictionary existence failed"
        desired_result = "❌ AclError: ACL name is missing or the SSH_ACCESS ACE dictionary is not a list\n"
        try:
            validate._assert_acl(
                {
                    "name": "SSH_ACCESS",
                    "ace": {"remark": "MGMT Orion - SRVF-ORION01"},
                }
            )
        except SystemExit:
            pass
        assert capsys.readouterr().out == desired_result, err_msg

    # ----------------------------------------------------------------------------
    # 1f. Validates check that top level ACL dictionary is a list
    # ----------------------------------------------------------------------------
    def test_validate_file(self, capsys):
        err_msg = "❌ validate_file: Unit test for the 'acl' top level dictionary failed"
        desired_result = (
            "❌ AclError: Top level dict 'acl' does not exist or is not a list\n"
        )
        try:
            validate.validate_file(
                dict(filename=os.path.join(test_input_dir, "acl_is_list.yml"))
            )
        except SystemExit:
            pass
        assert capsys.readouterr().out == desired_result, err_msg

    # 1g. Validates well formated ACL with no errors is returned back
    def test_valid_acl(self):
        desired_result = {
            "acl": [
                {
                    "name": "SSH_ACCESS",
                    "ace": [
                        {"remark": "MGMT Access - VLAN810"},
                        {"permit": "172.17.10.0/24"},
                        {"remark": "Citrix Access"},
                        {"permit": "10.10.109.10/32"},
                        {"deny": "any"},
                    ],
                },
                {
                    "name": "SNMP_ACCESS",
                    "ace": [{"deny": "10.10.209.11"}, {"permit": "any"}],
                },
            ]
        }
        err_msg = "❌ validate_file: Unit test for 'acl' formatting failed"
        output = validate.validate_file(
            dict(filename=os.path.join(test_input_dir, "test_acl_input_data.yml"))
        )
        assert output == desired_result, err_msg

    # ----------------------------------------------------------------------------
    # 1h. Validates well formated ACL with no errors is returned back
    # ----------------------------------------------------------------------------
    @pytest.mark.usefixtures("load_acl_vars")
    def test_format_input_vars(self):
        err_msg = (
            "❌ format_input_vars: Unit test for the creation of ACL variables failed"
        )
        desired_result = {
            "name": ["SSH_ACCESS", "SNMP_ACCESS"],
            "wcard": {
                "acl": [
                    {
                        "name": "SSH_ACCESS",
                        "ace": [
                            {"remark": "MGMT Access - VLAN810"},
                            {"permit": "172.17.10.0 0.0.0.255"},
                            {"remark": "Citrix Access"},
                            {"permit": "host 10.10.109.10"},
                            {"deny": "any"},
                        ],
                    },
                    {
                        "name": "SNMP_ACCESS",
                        "ace": [{"deny": "host 10.10.209.11"}, {"permit": "any"}],
                    },
                ]
            },
            "mask": {
                "acl": [
                    {
                        "name": "SSH_ACCESS",
                        "ace": [
                            {"remark": "MGMT Access - VLAN810"},
                            {"permit": "172.17.10.0 255.255.255.0"},
                            {"remark": "Citrix Access"},
                            {"permit": "10.10.109.10 255.255.255.255"},
                            {"deny": "any"},
                        ],
                    },
                    {
                        "name": "SNMP_ACCESS",
                        "ace": [
                            {"deny": "10.10.209.11 255.255.255.255"},
                            {"permit": "any"},
                        ],
                    },
                ]
            },
            "prefix": {
                "acl": [
                    {
                        "name": "SSH_ACCESS",
                        "ace": [
                            {"remark": "MGMT Access - VLAN810"},
                            {"permit": "172.17.10.0/24"},
                            {"remark": "Citrix Access"},
                            {"permit": "10.10.109.10/32"},
                            {"deny": "any"},
                        ],
                    },
                    {
                        "name": "SNMP_ACCESS",
                        "ace": [{"deny": "10.10.209.11/32"}, {"permit": "any"}],
                    },
                ]
            },
        }
        assert validate.format_input_vars(acl_vars) == desired_result, err_msg
