# Network Device management (SSH, SNMP) ACL update

The idea behind this script is to apply SSH and SNMP management ACLs at scale across different device types without fear of lockout.

- Takes a YAML file input of variables for the ACLs such as name, permission and source address
- Only supports extended ACLs as [Cisco IOS changes order of standard ACLs](https://community.cisco.com/t5/switching/access-list-wrong-order/td-p/3070419/highlight/true/page/2) which breaks validation
- The ACLs must be existing, it does not apply them to lines only updates them
- Dynamically builds the Nornir inventory from Solarwinds Orion NPM (can be disabled to use static inventory)
- Devices are group by device type (platform) with the available groups being *ios, ios-xe, nxos, asa, wlc, checkpoint*
- Runtime flags allow for filtering of which devices from the inventory it will run against
- Nornir-template builds ACL configs based on device types (groups) allowing for multi-vendor device type config
- Tests SSH access after ACL application and will rollback before closing connection if SSH access is broken
- Uses a customized version of naplam-validate to validate ACLs after completion (does not rollback, just reports)

## Installation and Prerequisites

Clone the repository and create a virtual environment

```bash
git clone https://github.com/mgmt_acl_update
python -m venv ~/venv/mgmt_acl_update
source ~/venv/mgmt_acl_update/bin/activate
```

Install the packages (nornir, orionsdk, rich, etc)

```bash
pip install -r mgmt_acl_update/requirements.txt
```

## Input File

The input file is list of ACLs which in turn hold a list of dictionaries. The top level ACL dictionary is a list of ACLs with each ACL having a name and an ACE list of dictionaries. The ACE dictionary keys is the permissions (*remark*, *permit* or *deny*) and the values are the source addresses (*x.x.x.x* (will be /32), *x.x.x.x/x* or *any*).

```yaml
acl:
  - name: SSH_ACCESS
    ace:
      - { remark: MGMT Access - VLAN810 }
      - { permit: 172.17.10.0/24 }
      - { remark: Citrix Access }
      - { permit: 10.10.109.10/32 }
      - { deny: any }
  - name: SNMP_ACCESS
    ace:
      - { deny: 10.10.209.11 }
      - { remark: any }
```

## Templating

The *nornir-template* plugin creates device_type specific configuration (based on group membership) from the input variable file and adds this as a *config* variable under the relevant group. If there is a member of that group in the inventory the configuration is rendered once against the first member of that group (rather than for every member) and the result printed to screen. All the template configuration is in the one file with conditional rendering done based on the os_type (platform) variable within the template. The following device types (groups) are supported:

| Groups | Jinja os_type | Information
| ------------- | ----- | ------ |
| ios and ios-xe | `ios` | Wildcard based ACLs (SSH and SNMP) |
| nxos | `nxos` | Prefix based ACLs (SSH and SNMP) |
| asa | `asa` | Subnet mask based management interface (called mgmt) access (SSH and HTTP) |

## Filtering the inventory

When running the script is best to first test out the filters to make sure it is only run against the appropriate hosts.

| flag    | Description |
| ------- | -------------|
| `-n` | Match any ***hostnames*** that contains this string
| `-g` | Match a ***group*** or combination of groups *(ios, iosxe, nxos, wlc, asa (includes ftd), checkpoint* |
| `-l` | Match a ***physical location*** or combination of them *(DC1, DC2, DCI (Overlay), ET, FG)* |
| `-ll` | Match a ***logical location*** or combination of them *(WAN, WAN Edge, Core, Access, Services)* |
| `-t` | Match a ***device type*** or combination of them *(firewall, router, dc_switch, switch, wifi_controller)* |
| `-v` | Match any ***Cisco OS version*** that contains this string |
| `-s` | Prints (*show*) hostname and host for all the hosts within the filtered inventory |
| `-sd` | Prints (*show detail*) all the hosts within the inventory including their host_vars |

For example this will run against all IOS devices at the HME location, `-s` prints out the group membership.

```python
$ python update_mgmt_acl.py -g ios -l HME -s
======================================================================
2 hosts have matched the filters 'ios, HME':
-Host: HME-SWI-VSS01      -Hostname: 10.10.20.1
-Host: HME-SWI-ACC01      -Hostname: 10.10.10.104
```

## Running the script

Before applying any configuration run the script in *dry_run* mode to print the templated configuration and show what changes would have been applied. If the filename does not exist the *directory* variable (default is the current working directory) from *update_mgmt_acl.py* is added to the path, if neither exists the script exits with an error message.

| flag           | Description |
| -------------- | ----------- |
| `-f` | Run in ***dry_run*** mode by specifying the input variable file, if it doesn't exist adds home directory
| `a` | Disables *dry_run* mode so that the changes are applied
| `-nu` | Overrides the ***NPM username*** set with *npm.user* in *inv_settings.yml* |
| `-du` | Overrides the ***Network device username*** set with *device.user* in *inv_settings.yml* |

The Orion NPM username and device username are defined in *inv_settings.yml*, this can be overridden at runtime.

```python
$ python update_mgmt_acl.py -du test_user -g asa -f acl_input_data.yml
nornir_template*****************************************************************
---- HME-ASA-FW01: Generating ASA configuration ** changed : False ------------- INFO

ssh 172.25.24.168 255.255.255.255 mgmt
ssh 172.25.24.230 255.255.255.255 mgmt
........

**** DRY_RUN=TRUE: This is the configuration that would have been applied ******
task_engine*********************************************************************
* HME-ASA-FW01 ** changed : False **********************************************
vvvv task_engine ** changed : False vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv INFO
vvvv backup_acl ** changed : False vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv INFO
Backing up current ACL configurations
^^^^ END backup_acl ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
---- ACL differences (- remove, + add) ** changed : False ---------------------- INFO

+ ssh 172.25.24.44 255.255.255.255 mgmt
+ ssh 172.25.24.32 255.255.255.255 mgmt
+ ssh 172.25.24.31 255.255.255.255 mgmt


+ http 172.17.10.0 255.255.255.0 mgmt
+ http 10.200.109.103 255.255.255.255 mgmt

^^^^ END task_engine ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

Finally once you are happy with what changes are to be made the script can be run with the `-a` flag to actually apply the changes.

```python
$ python update_mgmt_acl.py -g asa -f acl_input_data.yml -a
nornir_template*****************************************************************
---- HME-ASA-FW01: Generating ASA configuration ** changed : False ------------- INFO

ssh 172.25.24.168 255.255.255.255 mgmt
ssh 172.25.24.230 255.255.255.255 mgmt
ssh 172.17.10.0 255.255.255.0 mgmt
..........
**** DRY_RUN=False: This is result of configuration applied ********************
task_engine*********************************************************************
* HME-ASA-FW01 ** changed : True ***********************************************
vvvv task_engine ** changed : False vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv INFO
vvvv backup_acl ** changed : False vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv INFO
Backing up current ACL configurations
^^^^ END backup_acl ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
---- ACL differences (- remove, + add) ** changed : False ---------------------- INFO

+ ssh 172.25.24.44 255.255.255.255 mgmt
+ ssh 172.25.24.32 255.255.255.255 mgmt
+ ssh 172.25.24.31 255.255.255.255 mgmt


+ http 172.17.10.0 255.255.255.0 mgmt
+ http 10.200.109.103 255.255.255.255 mgmt

vvvv apply_acl ** changed : True vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv INFO
✅  ACLs successfully updated
^^^^ END apply_acl ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
^^^^ END task_engine ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

To guard against locking ourselves out of the devices (as we are changing the SSH ACL) the connection to the device is kept open whilst a simple post-test connection test is done (telnet on port 22) and the  ACL changes reverted if this fails. A further post-test validation is done on task completion using nornir-validate to produce a compliance report if the actual_state and desired_state do not match (only reports, does not revert the config).

!!!!!!! NEED A VIDEO TO SHOW Operation !!!!!

## Unit testing

*Pytest* is used for the unit testing, this is split into 2 separate scripts.

**test_update_mgmt_acl.py:** Test the *update_mgmt_acl.py* *InputValidate* class which does the input formatting, validation and is the engine that runs that calls and runs the other scripts. The majority of testing is done against input from the files in *test_inputs* that are used to in ensure the validation spots the errors. *test_acl_input_data.yml* holds all the variables used to create the ACLs, is same format as what would be used when running script for real.

```python
pytest test/test_update_mgmt_acl.py -vv
```

**test_nornir_tasks.py:** The script is split into 3 classes to test the different elements within *nornir_tasks.py*

- TestNornirTemplate: Uses a nornir inventory (in fixture setup_nr_inv) to test templating and the creation of nornir group_vars
- TestFormatAcl: Uses dotmap and acl_config (in fixture load_vars) to test all the formatting of python objects used by nornir_tasks
- TestNornirCfg: Uses the the fixture *setup_test_env* (with *nr_create_test_env_tasks* and *nr_delete_test_env_tasks*) to create and delete the test environment (adds ACLs and associate to vty) on a test device (in *hosts.yml*) at start and finish of the script to setup the environment to test against. This tests the application of the configuration including rollback on a failure (only tests IOS device)

```python
pytest test/test_nornir_tasks.py::TestNornirTemplate -vv
pytest test/test_nornir_tasks.py::TestFormatAcl -vv
pytest test/test_nornir_tasks.py::TestNornirCfg -vv
pytest test/test_nornir_tasks.py -vv
```

## Caveats

Orion sees Firepower also as ASA, not sure whow to fix thta. Would probbaly be handling via the FMC so not really relvant to this

Dont use extended ACLs as the switch will rewrite thme to meet the hash, so although sequencing still correct (in terms of numbers), when you view in runnign config or show ip access-list it is displayed in a different order. Breaks checks and causes comments to be incorrect

https://community.cisco.com/t5/switching/access-list-wrong-order/td-p/3070419/highlight/true/page/2

On NXOS the ACLs must be entered in the format x.x.x.x/x, if you use masks or wildcards will be in the config that way and will get the wrong result form the [cisco_nxos_show_access-lists.textfsm](https://github.com/networktocode/ntc-templates/blob/master/ntc_templates/templates/cisco_nxos_show_access-lists.textfsm) NTC template,


[POA]
1. Test once more on nxos, IOS (build IOS in eve-ng), IOSXE and ASA to prove - if it breaks rollsback, validate works, updates correctly
2. Create a video to show operation and add to end of  Running the script
3. Update work windows setup, needs to include typing, ipdb and versions of netmiko and napalm, dotmap
