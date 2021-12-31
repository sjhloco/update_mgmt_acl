# Nornir Validate

Uses Nornir (with ***nornir-netmiko***) to gather and format device output before feeding this into ***napalm-validate*** in the form of ***actual_state*** and ***desired_state*** to produce a ***compliance report***. The idea behind this is for running pre and post checks on network devices based and an input file of the desired device state.

As the name suggests I have not reinvented the wheel here, I have just extended *napalm_validate* to validate on commands rather than getters to allow for the flexibility of validating any command output. This is done by importing the *napalm_validate compare* method and feeding in to it the *desire_state* and *actual_state* manually. To understand what I am waffling on about you need to understand the following terms:

- **desired_state:** The state you expect the device to be in. For example, you could expect that the device has certain OSPF neighbors, specific CDP neighbors or that all ports in a port-channel are up
- **actual_state:** This is real-time state of the device gathered by connecting to it and scraping the output of show commands

## Installation and Prerequisites

Clone the repository, create a virtual environment and install the required python packages

```bash
git clone https://github.com/sjhloco/nornir_validate.git
python -m venv ~/venv/nr_val
source ~/venv/nr_val/bin/activate
cd nornir_validate/
pip install -r requirements.txt
```

It is worth noting that I couldnt use the latest PyPI version of netmiko (3.4.0) or nornir-utils due to bugs for [ntc-templates parsing in netmiko](https://github.com/ktbyers/netmiko/pull/2274) and [nornir-utils print_result tasks](https://github.com/nornir-automation/nornir_utils/pull/22). Therefore *requirements.txt* installs the github repository versions that have the fixes for these issues.

## Running nornir_validate

Before being able to generate a meaningful compliance report you will need to edit the following elements, they are explained in more detail in the later sections.

- **input data (variables)**: A yaml file (default *input_data.yml*) that holds the *host*, *group* and *all* (all devices) variables that describe the desired)state of the network
- **desired_state template:** A jinja template (*desired_state.j2*) that is rendered with the input variables to create the desired state
- **actual_state python logic:** A python method (in *actual_state.py*) that creates a data structure from the command outputs to be used as a comparison against the desired state

***nornir_validate*** can be run independently as a standalone script or imported into a script to use that scripts existing nornir inventory.

### Standalone

When run as standalone *nornir_validate* creates its own nornir inventory using the *config.yml* configuration file and looks in the *inventory* directory for the *hosts.yml*, *groups.yml* and *defaults.yml* files.

By default input data is gathered from *input_data.yml* and the compliance report is not saved to file. Either of these can be changed in the variables section at the start of *nornir_template.py* or overridden using flags at runtime.

```python
input_file = "input_data.yml"
report_directory = None
```

| flag           | Description |
| -------------- | ----------- |
| `-f` or `--filename` | Overrides the value set in the *input_file* variable to manually define the input data file |
| `-d` or `--directory` | Overrides the value set in *directory* variable to save compliance reports to file |

Specifying anything other than *None* for the *report_directory* enables saving the compliance report, the naming format is *hostname_compliance_report_YYYY-MM-DD.json*

```python
python nr_val.py
```

If the validation check fails the full compliance report will be printed to screen and the nornir task marked as failed.

<img src=https://user-images.githubusercontent.com/33333983/143948220-65f6745c-a67b-46ca-8791-39131f82ca32.gif  width="750" height="500">

### Imported

Rather than using the inventory in *nornir_validate* the ***validate_task*** function can be imported into a script to make use of an already existing nornir inventory.

```python
from nornir import InitNornir
from nornir_utils.plugins.functions import print_result
from nornir_validate.nr_val import validate_task

nr = InitNornir(config_file="config.yml")
result = nr.run(task=validate_task, input_file="my_input_data.yml")
print_result(result)
```

When calling the function it is mandatory to specify the *input_file*, the *directory* is still optional as is only needed if you want to save the report to file.

```python
result = nr.run(task=validate_task, input_file="my_input_data.yml", directory='/Users/user1/reports')
```

## Input Data

The input data (variable) file holds the *host_vars* and *group_vars* which are made up of dictionaries of features and their values. It is structured around these three optional dictionaries:

- **hosts:** Dictionary of host names each holding dictionaries of host-specific variables for the different features being validated
- **groups:** Dictionary of group names each holding dictionaries of group-specific variables for the different features being validated
- **all**: Dictionaries of variables for the different features being validated across all hosts

The host or group name must be an exact match of the host or group name within the nornir inventory. If there are any conflictions between the variables, *groups* take precedence over *all* and *hosts* over *groups*.

The result of the below example will check the OSPF neighbors on *all* devices, ACLs on all hosts in the *ios* group and the port-channel state and port membership on host *HME-SWI-VSS01*.

```yaml
hosts:
  HME-SWI-VSS01:
    po:
      - name: Po2
        mode: LACP
        members: [Gi0/15, Gi0/16]
groups:
  ios:
    acl:
      - name: TEST_SSH_ACCESS
        ace:
          - { remark: MGMT Access - VLAN10 }
          - { permit: 10.17.10.0/24 }
          - { remark: Citrix Access }
          - { permit: 10.10.10.10/32 }
          - { deny: any }
      - name: TEST_SNMP_ACCESS
        ace:
          - { deny: 10.10.20.11 }
          - { permit: any }
all:
  ospf:
    nbrs: [192.168.255.1, 2.2.2.2]
```

## Desired State

The input file (***input_data.yml***) is rendered by a jinja template (***desired_state.j2***) to produce a YAML formatted list of dictionaries with the key being the command and the value the desired output. ***feature*** matches the name of the features within the input file to make the rendering conditional. ***strict*** mode means that it has to be an exact match, no more, no less. This can be omitted if that is not a requirement.

```jinja
{% if feature == 'ospf' %}
- show ip ospf neighbor:
    _mode: strict
{% for each_nbr in input_vars.nbrs %}
    {{ each_nbr }}:
      state: FULL
{% endfor %}

{% elif feature == 'po' %}
- show etherchannel summary:
{% for each_po in input_vars %}
    {{ each_po.name }}:
      status: U
      protocol: {{ each_po.mode }}
      members:
{% for each_memeber in each_po.members %}
        _mode: strict
        {{ each_memeber }}:
          mbr_status: P
{% endfor %}{% endfor %}
{% endif %}
```

Below is an example of the YAML output after rendering the template with the example input data.

```yaml
- show etherchannel summary:
    Po2:
      status: U
      protocol: LACP
      members:
        _mode: strict
        Gi0/15:
          mbr_status: P
        _mode: strict
        Gi0/16:
          mbr_status: P
- show ip ospf neighbor:
    _mode: strict
    192.168.255.1:
      state: FULL
    2.2.2.2:
      state: FULL
```

The resulting python object is generated by serialising the YAML output and is stored as a host_var (nornir *data* dictionary) called *desired_state* for that host. This is the same structure that the *actual_state* will be in.

```python
{'show etherchannel summary': {'Po2': {'members': {'Gi0/15': {'mbr_status': 'P'},
                                                   'Gi0/16': {'mbr_status': 'P'},
                                                   '_mode': 'strict'},
                                       'status': 'U',
                                       'protocol': 'LACP'}},
 'show ip ospf neighbor': {'192.168.255.1': {'state': 'FULL'},
                           '2.2.2.2': {'state': 'FULL'},
                           '_mode': 'strict'}}
```

## Actual State

Netmiko is used to gather the command outputs and create TextFSM formatted data-models using *ntc-templates*. This is fed into ***actual_state.py*** where a dictionary of the *command* (key) and *command output* (value) are passed through an *os_type* (based on nornir *platform*) specific method to create a nested dictionary that matches the structure of the *desired_state*.

For example, the python logic to format the OSPF and port-channel looks like this.

```python
    if "show ip ospf neighbor" in cmd:
        for each_nhbr in output:
            tmp_dict[each_nhbr['neighbor_id']] = {'state': remove_char(each_nhbr['state'], '/')}
    elif "show etherchannel summary" in cmd:
        for each_po in output:
            tmp_dict[each_po['po_name']]['status'] = each_po['po_status']
            tmp_dict[each_po['po_name']]['protocol'] = each_po['protocol']
            po_mbrs = {}
            for mbr_intf, mbr_status in zip(each_po['interfaces'], each_po['interfaces_status']):
                po_mbrs[mbr_intf] = {'mbr_status': mbr_status}
            tmp_dict[each_po['po_name']]['members'] = po_mbrs
```

The resulting *actual_state* is the same as the *desired_state* except for the absence of the *'_mode': 'strict'* dictionary.

```python
{'show etherchannel summary': {'Po3': {'members': {'Gi0/15': {'mbr_status': 'D'},
                                                   'Gi0/16': {'mbr_status': 'D'}},
                                       'protocol': 'LACP',
                                       'status': 'SD'}},
 'show ip ospf neighbor': {'192.168.255.1': {'state': 'FULL'},
                           '2.2.2.2': {'state': 'FULL'}}}
```

For each command the formatting will be different as the captured data is different, however the principle is same in terms of the structure.

## Compliance Report

The desired_state and actual_state are fed into ***compliance_report.py*** which iterates through them feeding the command outputs into ***napalm_validate*** (its ***validate.compare*** method) which produces a per-command compliance report (complies *true* of *false*). All the commands are grouped into an overall compliance report with the reports compliance status set to *false* if any of the individual commands fail compliance.

This example shows a failed compliance report where the ACLs passed but OSPF failed due to a missing OSPF neighbor (*2.2.2.2*).

```python
{ 'complies': False,
  'show ip access-lists TEST_SNMP_ACCESS': { 'complies': True,
                                             'extra': [],
                                             'missing': [],
                                             'present': { '10': { 'complies': True,
                                                                  'nested': True},
                                                          '20': { 'complies': True,
                                                                  'nested': True}}},
  'show ip access-lists TEST_SSH_ACCESS': { 'complies': True,
                                            'extra': [],
                                            'missing': [],
                                            'present': { '10': { 'complies': True,
                                                                 'nested': True},
                                                         '20': { 'complies': True,
                                                                 'nested': True},
                                                         '30': { 'complies': True,
                                                                 'nested': True}}},
  'show ip ospf neighbor': { 'complies': False,
                             'extra': [],
                             'missing': ['2.2.2.2'],
                             'present': { '192.168.255.1': { 'complies': True,
                                                             'nested': True}}},
  'skipped': []}
  ```

## Validation Builder

At the moment there are only *desired_state* templates and *actual_state* python logic for the IOS commands *show ip access-lists*, *show ip ospf neighbor* and *show etherchannel summary*. The *validation_builder* directory has a script to assist with the building of new validations, have a look at the README in this directory for full details on how to use this.

## Future

This the first build of this project to get the structure of the base components correct. There is still a lot of work to be done on adding more commands to validate and putting it through its paces in a real world environment. Like many of my other projects what seems like a great idea in my head could turn out in reality to not be much use in the real world. Only time will tell..........

I plan to do the following over the coming months:

- Add a lot more IOS/IOS-XE, NXOS, ASA and Checkpoint commands to the actual_state.py and desired_state.j2. Unit-testing is already setup for the project so should hopefully speed up this process
- Once happy with the commands add a layer of abstraction for *actual_state.py* and *desired_state.j2* so these can be fed in by the user when it is imported into another script to merge with the base files
- Package it up as hopefully with a bigger command base and the ease of extending (abstraction of actual_state.py and desired_state.j2) should not be as much need to make changes to the base code
- Drink a few beers 🍺🍺🍺
- Maybe look at what is involved to add it as a nornir plugin

To allow me to fudge it to be able to import it as a module (due to inheritance) I added the following to *nr_val.py* that I need to remember to remove when it gets packaged up and check validation_builder (as effects inheritance), don't forget.....

```python
import os
import sys
sys.path.insert(0, "nornir_validate")

    if "nornir_validate" in os.getcwd():
        tmpl_path = "templates/"
    else:
       tmpl_path =  "nornir_validate/templates/"
```
