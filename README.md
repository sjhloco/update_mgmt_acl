# Network Device management (SSH, SNMP) ACL update

The idea behind this script is to apply SSH and SNMP management ACLs at scale across different device types without fear of lockout.

- Takes a YAML file input of variables for the ACLs such as name, permission and source address
- Only supports extended ACLs as the way [Cisco IOS changes order of standard ACLs](https://community.cisco.com/t5/switching/access-list-wrong-order/td-p/3070419/highlight/true/page/2) breaks validation
- The ACLs must be existing, it does not apply them to lines only updates them
- Nornir-template builds ACL configs based on device types allowing for multi-vendor device type config
- Dynamically builds the Nornir inventory from Solarwinds Orion NPM
- Custom Orion Nornir inventory plugin creates Nornir groups based on device specific attributes
- Runtime flags allow for filtering of which devices from the inventory it will run against
- Tests SSH access after ACL application and will rollback before closing connection if SSH access is broken
- Uses a customized version of naplam-validate to validate ACLs after completion

## Installation and Prerequisites

Clone the repository and create a virtual environment

```bash
git clone https://github.com/mgmt_acl_update
python -m venv ~/venv/mgmt_acl_update
source ~/venv/mgmt_acl_update/bin/activate
```

Install the packages (norir, orionsdk, rich, etc)

```bash
pip install -r mgmt_acl_update/requirements.txt
```

## Input File

The input file is list of ACLs which in turn hold a list of dictionaries. There are a few rules for it:

- The top level ACL dictionary must have a list of ACLs
- Each ACL needs to have a name dictionary
- Each ACL needs to have an ACE dictionary that contain a list of dictionaries
- The ACE dictionary keys are permissions, can only be *remark*, *permit* or *deny*
- The ACE dictionary values are the source addresses in the format *x.x.x.x* (will be /32), *x.x.x.x/x* or *any*

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

The *nornir-template* plugin creates group specific configuration from the input variable file and adds this as a *config* variable under the relevant group. The configuration is only created if there is a member of that group in the inventory. Configuration is only rendered once against the first member of that group (rather than for every member) and the result printed to screen once per-group. All template files are stored in the *templates* directory.

| Template Name | Groups | Format and Information |
| ------------- | ----- | ------ |
| cfg_iosxe_acl_tmpl.j2 | `ios`, `ios-xe` | Wildcard based ACLs (SSH and SNMP) |
| cfg_nxos_acl_tmpl.j2 | `nxos` | Prefix based ACLs (SSH and SNMP) |
| cfg_asa_acl_tmpl.j2 | `asa` | Subnet mask based management interface access (SSH and HTTP) |

## Application

When running the script is best to first test out the filters to make sure that it is only run against the appropriate hosts.

| flag | Description |
| ---- | -------------|
| `-n` | Match any ***hostnames*** that contains this string
| `-g` | Match a ***group*** or combination of groups *(ios, iosxe, nxos, wlc, asa (includes ftd), checkpoint (includes managers)* |
| `-l` | Match a ***physical location*** or combination of them *(DC1, DC2, DCI (Overlay), ET, FG)* |
| `-ll` | Match a ***logical location*** or combination of them *(WAN, WAN Edge, Core, Access, Services)* |
| `-t` | Match a ***device type*** or combination of them *(firewall, router, dc_switch, switch, wifi_controller)* |
| `-v` | Match any ***Cisco OS version*** that contains this string |
| `-s` | Prints (*show*) hostname and host for all the hosts within the filtered inventory |
| `-sd` | Prints (*show detail*) all the hosts within the inventory including their host_vars |

For example this will run against all IOS devices at the HME location, `-s` prints out the group membership.

```python
python main.py -s -g ios -l HME
```

Before applying any configuration run the script in *dry_run* mode by swapping `-s` for `f input_file_name.yml`, it will print the templated configuration and show what changes would have been applied.

It the filename does not exist the *directory* variable (default is the current working directory) from *update_mgmt_acl.py* is added to the path, if neither exists the script exists with an error message.

| flag           | Description |
| -------------- | ----------- |
| `-f` | Specify the input variable file name, if it doesnt exist adds home directory
| `a` | Disables dry_run so that the changes are applied
| `-nu` | Overrides the ***NPM username*** set with *npm.user* in *inv_settings.yml* |
| `-du` | Overrides the ***Network device username*** set with *device.user* in *inv_settings.yml* |

The Orion NPM username and device username are defined in *inv_settings.yml*, this can be overridden at runtime.

```python
python main.py -du test_user -g ios -l HME -f acl_input_data.yml
```

Finally once you are happy with what changes are to be made the script can be run with the `-a` flag to actually apply the changes.

```python
python main.py -du test_user -g ios -l HME -f acl_input_data.yml -a
```

To guard against locking ourselves out of the devices (as we are changing the SSH ACL) the connection to the device is kept open whilst a simple post-test connection test is done (telnet on port 22) and the  ACL changes reverted if this fails.

NEED DESCRIPTION of vlaidation
NEED A VIDEO ON WHAT HAPPENS ONCE FINSIH VALIDATION


## Unit testing

*Pytest* is used for the unit testing, this is split into 3 separate scripts.

**test_update_mgmt_acl.py:** Tests the *ValidateFile* class in the *test_update_mgmt_acl.py* script which does the input formatting, validation and is the engine that runs that calls and runs the other scripts. The majority of testing is done against input from the files in *test_inputs* that are used to in ensure the validation spots the errors. *test_acl_input_data.yml* holds all the variables used to create the ACLs, is same format as what would be used when running script for real.

```python
pytest test/test_update_mgmt_acl.py -vv
pytest test/test_update_mgmt_acl.py::TestValidateFile -vv
pytest test/test_update_mgmt_acl.py::TestValidateFile::test_assert_ipv4 -vv
```

**test_nornir.py:** Tests the *NornirTask* class in *nornir_tasks.py* script which includes templating, formatting and applying the configuration (including rollback). *TestNornirCfg* uses the fixture *setup_test_env* (with *nr_create_test_env_tasks* and *nr_delete_test_env_tasks*) to create and delete the test environment (adds ACLs and associate to vty) on a test device (in *hosts.yml*) at start and finish of the script to setup the environment to test against.

```python
pytest test/test_nornir.py -vv
pytest test/test_nornir.py::TestNornirTemplate -vv
pytest test/test_nornir.py::TestFormatAcl -vv
pytest test/test_nornir.py::TestNornirCfg -vv
```


[POA]
3. Validate
Have created group_var acl_var as  {'groups': {'ios': {'acl': [list of acls]}

All import vars must be in same format as file, so 'hosts', 'groups' or 'all'
Question is how to use this as am using import task, see if can load, if not need to make function more generic
3c. Add to nor-val to take data in variable format dict.
3d. add ASA SSH and HTTP check in nor_val(what does the cmds look like? - just be show run)
3e. Add unitests for this in nornir-val
3f. Update nor-val readme

4. Test in update mgmt_acl by unhashing line 293
Unit test adding acl_val




Caveats

Orion sees Firepower also as ASA, not sure whow to fix thta. Would probbaly be handling via the FMC so not really relvant to this

Dont use extended ACLs as the switch will rewrite thme to meet the hash, so although sequencing still correct (in terms of numbers), when you view in runnign config or show ip access-list it is displayed in a different order. Breaks checks and causes comments to be incorrect

https://community.cisco.com/t5/switching/access-list-wrong-order/td-p/3070419/highlight/true/page/2