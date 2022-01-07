# Variables used as inputs for testing nornir with test_nornir.py and test_nornir_cfg.py
acl = {
    "name": [
        "UTEST_SSH_ACCESS",
        "UTEST_SNMP_ACCESS",
    ],
    "wcard": {
        "acl": [
            {
                "name": "UTEST_SSH_ACCESS",
                "ace": [
                    {"remark": "MGMT Access - VLAN810"},
                    {"permit": "172.17.10.0 0.0.0.255"},
                    {"remark": "Citrix Access"},
                    {"permit": "host 10.10.109.10"},
                    {"deny": "any"},
                ],
            },
            {
                "name": "UTEST_SNMP_ACCESS",
                "ace": [{"deny": "host 10.10.209.11"}, {"permit": "any"}],
            },
        ]
    },
    "mask": {
        "acl": [
            {
                "name": "UTEST_SSH_ACCESS",
                "ace": [
                    {"remark": "MGMT Access - VLAN810"},
                    {"permit": "172.17.10.0 255.255.255.0"},
                    {"remark": "Citrix Access"},
                    {"permit": "host 10.10.109.10"},
                    {"deny": "any"},
                ],
            },
            {
                "name": "UTEST_SNMP_ACCESS",
                "ace": [{"deny": "host 10.10.209.11"}, {"permit": "any"}],
            },
        ]
    },
    "prefix": {
        "acl": [
            {
                "name": "UTEST_SSH_ACCESS",
                "ace": [
                    {"remark": "MGMT Access - VLAN810"},
                    {"permit": "172.17.10.0/24"},
                    {"remark": "Citrix Access"},
                    {"permit": "10.10.109.10/32"},
                    {"deny": "any"},
                ],
            },
            {
                "name": "UTEST_SNMP_ACCESS",
                "ace": [{"deny": "10.10.209.11/32"}, {"permit": "any"}],
            },
        ]
    },
    "base_acl": "ip access-list extended UTEST_SSH_ACCESS\n"
    " remark MGMT Access - VLAN810\n"
    " permit ip 172.17.10.0 0.0.0.255 any\n"
    " remark Citrix Access\n"
    " permit ip host 10.10.109.10 any\n"
    " permit ip any any\n\n"
    "ip access-list extended UTEST_SNMP_ACCESS\n"
    " deny ip host 10.10.209.11 any\n"
    " permit ip any any",
}
