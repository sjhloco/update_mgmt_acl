from typing import Dict, List
import ipaddress

# ----------------------------------------------------------------------------
# Engine to run different formatters
# ----------------------------------------------------------------------------
def format_actual_state(
    os_type: str,
    cmd: str,
    output: List,
    tmp_dict: Dict[str, None],
    actual_state: Dict[str, None],
) -> Dict[str, Dict]:
    if "ios" in os_type:
        iosxe_format(cmd, output, tmp_dict, actual_state)
    elif "nxos" in os_type:
        pass
    elif "asa" in os_type:
        pass
    return actual_state


# ----------------------------------------------------------------------------
# Mini-functions used by all OS types to keep DRY
# ----------------------------------------------------------------------------
# ACL_FORMAT: Removes all the empty dictionaries from ACL list of dicts
def acl_format(input_acl: List) -> List:
    acl: List = []
    for each_acl in input_acl:
        tmp_acl = {}
        for ace_key, ace_val in each_acl.items():
            if len(ace_val) != 0:
                tmp_acl[ace_key] = ace_val
        acl.append(tmp_acl)
    return acl


# ACL_ADDR: Converts addressing into address/prefix
def acl_scr_dst(each_ace: Dict[str, str], src_dst: str) -> str:
    if each_ace.get(src_dst + "_network") != None:
        addr = each_ace[src_dst + "_network"] + "/" + each_ace[src_dst + "_wildcard"]
        return ipaddress.IPv4Interface(addr).with_prefixlen
    elif each_ace.get(src_dst + "_host") != None:
        return ipaddress.IPv4Interface(each_ace[src_dst + "_host"]).with_prefixlen
    else:
        return each_ace[src_dst + "_any"]


# REMOVE: Removes the specified character and anything after it
def remove_char(input_data: str, char: str) -> str:
    if char in input_data:
        return input_data.split(char)[0]
    else:
        return input_data


# ----------------------------------------------------------------------------
# IOS/IOS-XE desired state formatting
# ----------------------------------------------------------------------------
def iosxe_format(
    cmd: str, output: List, tmp_dict: Dict[str, None], actual_state: Dict[str, None]
) -> Dict[str, Dict]:
    # ACL: Creates ACL dicts in the format [{acl_name: {seq_num: {protocol: ip/tcp/udp, src: src_ip, dst: dst_ip, pst_port: port}]
    if "show ip access-lists" in cmd:
        acl = acl_format(output)
        for each_ace in acl:
            # Creates dict for each ACE entry
            if each_ace.get("line_num") != None:
                tmp_dict[each_ace["line_num"]]["action"] = each_ace["action"]
                tmp_dict[each_ace["line_num"]]["protocol"] = each_ace["protocol"]
                tmp_dict[each_ace["line_num"]]["src"] = acl_scr_dst(each_ace, "src")
                tmp_dict[each_ace["line_num"]]["dst"] = acl_scr_dst(each_ace, "dst")
                if each_ace.get("dst_port") != None:
                    tmp_dict[each_ace["line_num"]]["dst_port"] = each_ace["dst_port"]
                elif each_ace.get("icmp_type") != None:
                    tmp_dict[each_ace["line_num"]]["icmp_type"] = each_ace["icmp_type"]

    # OSPF: Creates OSPF dicts in the format {ospf_nbr_rid: {state: nbr_state}}
    elif "show ip ospf neighbor" in cmd:
        for each_nhbr in output:
            tmp_dict[each_nhbr["neighbor_id"]] = {
                "state": remove_char(each_nhbr["state"], "/")
            }
    # PO: Creates port-channel dicts in the format {po_name: {protocol: type, status: code, members: {intf_name: {mbr_status: code}}}}
    elif "show etherchannel summary" in cmd:
        for each_po in output:
            tmp_dict[each_po["po_name"]]["status"] = each_po["po_status"]
            tmp_dict[each_po["po_name"]]["protocol"] = each_po["protocol"]
            po_mbrs = {}
            for mbr_intf, mbr_status in zip(
                each_po["interfaces"], each_po["interfaces_status"]
            ):
                # Creates dict of members to add to as value in the PO dictionary
                po_mbrs[mbr_intf] = {"mbr_status": mbr_status}
            tmp_dict[each_po["po_name"]]["members"] = po_mbrs

    actual_state[cmd] = dict(tmp_dict)
    return actual_state
