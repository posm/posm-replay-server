from xml.etree import ElementTree as ET

from typing import List, Dict, Union


StrOrInt = Union[str, int]


def create_obj_attrs(elem: ET.Element, data: Dict[str, StrOrInt]) -> ET.Element:
    for k, v in data.items():
        elem.set(k, str(v))
    return elem


def convert_to_osm_change_xml(change_data: dict) -> str:
    # TODO: insert newline
    action = change_data['action']
    elem_type = change_data['type']
    root = ET.Element(action)
    element = ET.SubElement(root, elem_type)
    for k, v in change_data['data'].items():
        if isinstance(v, list):
            for x in v:
                se = ET.SubElement(element, k[:-1])  # k[:-1] : tags -> tag, etc
                create_obj_attrs(se, x)
        else:
            element.set(k, str(v))
    return ET.tostring(root, encoding='utf-8',)
