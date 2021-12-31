# Validation Builder

*validation_builder.py* is designed to help with the building of new validations, so the creation of the *desired_state* templates and *actual_state* python logic. Within the *validation_builder* directory there are four files that will be used to create the new validations:

- **input_data.yml:** Dictionaries of the features to be validated stored under *all*, *groups* and *hosts* dictionaries
- **desired_state.j2:** Template of per-feature Jinja logic used to render the input data to create the desired state
- **desired_state.yml:** The desired state which is the result of the rendered template
- **actual_state.json:** The actual state which is the result of the actual state python logic

*desired_state.yml* and *actual_state.json* are static files of what you are trying to achieve by either rendering the template or formatting the output returned by a device. *input_data.yml* and *desired_state.j2* will hold the code you are trying to create that will eventually be used to dynamically create the first two files.

Even if a file is empty or not used all of these files must be present or the script will not run. The file location and file names can be changed in the variables at the start of the script.

```python
input_file = "input_data.yml"                   # Name of the input data file
desired_state = "desired_state.yml"             # Name of the static desired_state file
desired_state_tmpl = "desired_state.j2"         # Name of the desired_state template
actual_state = "actual_state.json"              # Name of the static actual_state file
```

Differing runtime flags are used to assist with the different stages of the validation file build process. If no flag is specified the compliance report is created based on the *input_data.yml* and *desired_state.j2*, so is the equivalent of running *nornir_validate*.

| flag           | Description |
| -------------- | ----------- |
| `-ds` or `--desired_state` | Renders the contents of the *desired_state.j2* template and prints the YAML formatted output
| `-di` or `--discovery` | Runs the *desired_state* commands on a device printing the TextFSM data-modeled output
| `-as` or `--actual_state` | Runs the *desired_state* commands printing the JSON formatted *actual_state*
| `-rds` or `--report_desired_state` | Builds and prints a compliance report using the dynamically created *desired_state* and static *actual_state.json* file
| `-ras` or `--report_actual_state` |  Builds and prints a compliance report using the dynamically created *actual_state* and static *desired_state.yml* file

The following steps walk you through the process of creating a new validation using the validate builder.

## 1. Create desired state template

Define the Jinja2 template (*desired_state.j2*) which is used to create the *desired_state*. This is a YAML formatted list of nested dictionaries with the command being the key and the value the expected feature state.

```jinja
{% if feature == 'ospf' %}
- show ip ospf neighbor:
    _mode: strict
{% for each_nbr in input_vars.nbrs %}
    {{ each_nbr }}:
      state: FULL
{% endfor %}
{% endif %}
```

The template is rendered using the input data (*input_data.yml*) with the feature (*ospf* in this case) used for conditionally matching in the template.

```yaml
all:
  ospf:
    nbrs: [192.168.255.1]
```

`-ds` or `--desired_state` prints the output of the rendered template in YAML and JSON format. The JSON formatted output is what will be used by the compliance report, so this is what you are aiming for in terms of how the *actual_state* is structured (formatted command output).

```python
python val_build.py -ds
**** Validation Builder - Desired State ****************************************
desired_state_task**************************************************************
* HME-SWI-VSS01 ** changed : False *********************************************
vvvv desired_state_task ** changed : False vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv INFO
---- template in YAML ** changed : False --------------------------------------- INFO
- show ip ospf neighbor:
    _mode: strict
    192.168.255.1:
      state: FULL

---- template in JSON ** changed : False --------------------------------------- INFO
{ 'result': { 'show ip ospf neighbor': { '192.168.255.1': {'state': 'FULL'},
                                         '_mode': 'strict'}}}
^^^^ END desired_state_task ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

## 2. Discover TextFSM formatted command output

The discovery stage will gather the command output from the device and format it into a data model. The *desired_state.yml* defines a list of dictionaries with the key being the command (used to gather output) and the value the desired state. At this stage of the process it is just an empty dictionary as it is only being used to define the commands that will be run.

```yaml
- show ip ospf neighbor: {}
```

`-di` or `--discovery` return the command output formatted by TextFSM into a data model. TextFSM uses *ntc-templates* so the command must already have been defined by [NTC](https://github.com/networktocode/ntc-templates/tree/master/ntc_templates/templates) and be an exact match of the full command (no abbreviations like *show ip int brief*).

```python
python val_build.py -di
**** Validation Builder - Discovery ********************************************
discovery_task******************************************************************
* HME-SWI-VSS01 ** changed : False *********************************************
vvvv discovery_task ** changed : False vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv INFO
{ 'show ip ospf neighbor': [ { 'address': '192.168.255.1',
                               'dead_time': '00:00:35',
                               'interface': 'Vlan98',
                               'neighbor_id': '192.168.255.1',
                               'priority': '1',
                               'state': 'FULL/BDR'}]}
^^^^ END discovery_task ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

## 3. Create actual state

Based on the discovery output build the python logic to perform the data model formatting of the *actual_state*, this is done in *actual_state.py* on a *per-os_type* basis. The result of this formatting should match the JSON formatted output from step1 (minus top-level dict of *result* and *_mode*).

```python
if "show ip ospf neighbor" in cmd:
    for each_nhbr in output:
        tmp_dict[each_nhbr['neighbor_id']] = {'state': remove_char(each_nhbr['state'], '/')}
```

`-as` or `--actual_state` runs the commands from *desired_state.yml* and passes the returned output (TextFSM data-model) through *actual_state.py* printing the resulting *actual_state* to screen.

```python
python val_build.py -as
**** Validation Builder - Actual State *****************************************
actual_state_task***************************************************************
* HME-SWI-VSS01 ** changed : False *********************************************
vvvv actual_state_task ** changed : False vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv INFO
{'show ip ospf neighbor': {'192.168.255.1': {'state': 'FULL'}}}
^^^^ END actual_state_task ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

## Using static files to create compliance report

A compliance report can be generated using either a static *actual_state* (*actual_state.json*) file and dynamic *desired_state* (from step1) or a static *desired_state* (*desired_state.yml*) file and dynamic *actual_state* (from step3). This is a good way to test out the either of the dynamic states created in the above steps.

It is worth noting that although the JSON formatting in step1 is correct, for this to be used in Python (like when create static *actual_state.json* file) you must swap out all the `'` for `"`.

`--rds` or `--report_desired_state` builds and prints a compliance report with the *desire_state* dynamically created (rendering *desired_state.j2*) and the *actual_state* got from a static file (loads *actual_state.json*).

```python
python val_build.py -rds
**** Validation Builder - Compliance Report using dynamic desired_state and static actual_state
report_desired_state_task*******************************************************
* HME-SWI-VSS01 ** changed : False *********************************************
vvvv report_desired_state_task ** changed : False vvvvvvvvvvvvvvvvvvvvvvvvvvvvvv INFO
{ 'show ip ospf neighbor': { 'complies': True,
                             'extra': [],
                             'missing': [],
                             'present': { '192.168.255.1': { 'complies': True,
                                                             'nested': True}}}}
^^^^ END report_desired_state_task ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

`--ads` or `--report_actual_state` builds and prints a compliance report with the *actual_state* dynamically created (from python logic in *actual_state.py*) and the *desired_state* got from a static file (loads *desired_state.yml*).

```python
python val_build.py -ras
**** Validation Builder - Compliance Report using dynamic actual_state and static desired_state
report_actual_state_task********************************************************
* HME-SWI-VSS01 ** changed : False *********************************************
vvvv report_actual_state_task ** changed : False vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv INFO
{ 'show ip ospf neighbor': { 'complies': True,
                             'extra': [],
                             'missing': [],
                             'present': { '192.168.255.1': { 'complies': True,
                                                             'nested': True}}}}
^^^^ END report_actual_state_task ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

Finally once happy with the new validations run the script with no flags which is the equivalent of using nornir_validate.


 use dynamically created files for both the desired and actual states. These lines of code can then be moved into the nornir_validate *templates* directory to be used for future .