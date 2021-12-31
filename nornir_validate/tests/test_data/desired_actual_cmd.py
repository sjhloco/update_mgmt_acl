# These dictionaries are used to test templated desired state (test_input_task) and formatted actual state (test_actual_state_cmds)

# --------------------------------------------------------------------------------------
# DESIRED: The desired state after it has been templated and assigned as a host_var
# --------------------------------------------------------------------------------------
desired_state = {
    "show ip ospf neighbor": {
        "_mode": "strict",
        "192.168.255.1": {"state": "FULL"},
        "2.2.2.2": {"state": "FULL"},
    },
    "show ip access-lists TEST_SSH_ACCESS": {
        "_mode": "strict",
        "10": {
            "action": "permit",
            "protocol": "ip",
            "src": "10.17.10.0/24",
            "dst": "any",
        },
        "20": {
            "action": "permit",
            "protocol": "ip",
            "src": "10.10.10.10/32",
            "dst": "any",
        },
        "30": {"action": "deny", "protocol": "ip", "src": "any", "dst": "any"},
    },
    "show etherchannel summary": {
        "Po3": {
            "status": "U",
            "protocol": "LACP",
            "members": {
                "_mode": "strict",
                "Gi0/15": {"mbr_status": "P"},
                "Gi0/16": {"mbr_status": "P"},
            },
        }
    },
}

# --------------------------------------------------------------------------------------
# ACTUAL: The actual state after it has been formated by actual_state.py
# --------------------------------------------------------------------------------------
actual_state = {
    "show ip ospf neighbor": {
        "192.168.255.1": {"state": "FULL"},
        "2.2.2.2": {"state": "FULL"},
    },
    "show ip access-lists TEST_SSH_ACCESS": {
        "10": {
            "action": "permit",
            "dst": "any",
            "protocol": "ip",
            "src": "10.17.10.0/24",
        },
        "20": {
            "action": "permit",
            "dst": "any",
            "protocol": "ip",
            "src": "10.10.10.10/32",
        },
        "30": {"action": "deny", "dst": "any", "protocol": "ip", "src": "any"},
    },
    "show etherchannel summary": {
        "Po3": {
            "members": {"Gi0/15": {"mbr_status": "D"}, "Gi0/16": {"mbr_status": "D"}},
            "protocol": "LACP",
            "status": "SD",
        }
    },
}

# --------------------------------------------------------------------------------------
# CMD: The command output (textFSM formatted) that is used to format the actual_state
# --------------------------------------------------------------------------------------
cmd_output = {
    "show ip ospf neighbor": [
        {
            "address": "192.168.255.1",
            "dead_time": "00:00:35",
            "interface": "Vlan98",
            "neighbor_id": "192.168.255.1",
            "priority": "1",
            "state": "FULL/BDR",
        },
        {
            "address": "2.2.2.2",
            "dead_time": "00:00:31",
            "interface": "Vlan2",
            "neighbor_id": "2.2.2.2",
            "priority": "1",
            "state": "FULL/BDR",
        },
    ],
    "show ip access-lists TEST_SSH_ACCESS": [
        {"acl_name": "TEST_SSH_ACCESS", "line_num": ""},
        {
            "acl_name": "TEST_SSH_ACCESS",
            "line_num": "10",
            "action": "permit",
            "protocol": "ip",
            "src_any": "",
            "src_network": "10.17.10.0",
            "src_wildcard": "0.0.0.255",
            "dst_any": "any",
        },
        {
            "acl_name": "TEST_SSH_ACCESS",
            "line_num": "20",
            "action": "permit",
            "protocol": "ip",
            "src_host": "10.10.10.10",
            "dst_any": "any",
        },
        {
            "acl_name": "TEST_SSH_ACCESS",
            "line_num": "30",
            "action": "deny",
            "protocol": "ip",
            "src_any": "any",
            "dst_any": "any",
        },
    ],
    "show etherchannel summary": [
        {
            "group": "3",
            "po_name": "Po3",
            "po_status": "SD",
            "protocol": "LACP",
            "interfaces": ["Gi0/15", "Gi0/16"],
            "interfaces_status": ["D", "D"],
        }
    ],
}
