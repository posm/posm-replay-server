from xml.etree import ElementTree as ET

from typing import Dict, Union


StrOrInt = Union[str, int]


def create_obj_attrs(elem: ET.Element, data: Dict[str, StrOrInt]) -> ET.Element:
    for k, v in data.items():
        if isinstance(v, list):
            for x in v:
                se = ET.SubElement(elem, k[:-1])  # k[:-1] : tags -> tag, etc
                create_obj_attrs(se, x)
        elif v is not None:
            elem.set(k, str(v))
    return elem


def convert_to_osm_change_xml(change_data: dict) -> str:
    # TODO: insert newline
    action = change_data['action']
    elem_type = change_data['type']
    root = ET.Element(action)
    element = ET.SubElement(root, elem_type)

    create_obj_attrs(element, change_data['data'])

    return ET.tostring(root, encoding='utf-8',)


class ChangesetsToXMLWriter:
    def __init__(self):
        self.root = ET.Element('osmChange')
        self.create_el = ET.SubElement(self.root, 'create')
        self.modify_el = ET.SubElement(self.root, 'modify')
        self.delete_el = ET.SubElement(self.root, 'delete')

    def add_change(self, change: dict) -> None:
        action = change['action']
        if action == 'modify':
            obj_el = ET.SubElement(self.modify_el, change['type'])
        elif action == 'create':
            obj_el = ET.SubElement(self.create_el, change['type'])
        elif action == 'delete':
            obj_el = ET.SubElement(self.delete_el, change['type'])
        else:
            raise Exception(f'Invalid action "{action}"')
        create_obj_attrs(obj_el, change['data'])

    def get_xml(self) -> str:
        return ET.tostring(self.root, encoding='utf-8')
