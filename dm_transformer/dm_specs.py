from lxml import etree
import xml.etree.ElementTree as ET
from typing import List

def attribute_type_to_annotation(attr_type: str) -> str:
    return {
        "text": "str",
        "int": "int",
        "pos_geo": "tuple",
        "float": "float",
        "datetime": "datetime",
    }.get(attr_type, "str")

class ModelSpecifications:

    def __init__(self, xml_path=None, xml_content=None, xsd_path="format_specifications/dm_specification_schema.xsd"):
        """
        Constructor for the DataModelService.

        Parameters:
            xml_path (str): Path to the XML specification file 
            xml_content (str): XML data.
        """
        if xml_path is None and xml_content is None:
            raise ValueError("No XML file specified. Neither through its filepath nor directly as string.")
        
        self.classes = {}
        if xml_path:
            with open(xml_path, 'r') as xml_file:
                xml_content = xml_file.read()

        # Syntactic validation against XSD
        self._syntactic_validate(xml_content, xsd_path)

        # Parse XML
        self._parse_xml(xml_content)

        # Semantic validation
        self._semantic_validate()

    def _syntactic_validate(self, xml_content, xsd_path):
        with open(xsd_path, 'r') as xsd_file:
            xsd_root = etree.XML(xsd_file.read())
        
        schema = etree.XMLSchema(xsd_root)
        xml_parser = etree.XMLParser(schema=schema)
        
        try:
            etree.fromstring(xml_content, xml_parser)
        except etree.XMLSyntaxError as e:
            raise ValueError(f"Syntactic validation error: {e}")
        
    def _semantic_validate(self):
        # Check 1: Collection is optional if is_abstract="true" for a Class
        for class_name, class_info in self.classes.items():
            if class_info.get('is_abstract') and 'Collection' in class_info:
                raise ValueError(f"Class {class_name} is abstract and should not contain a Collection element.")
        
        # Check 2: Exactly one Attribute within each non-abstract class should have is_key="true" and type="string"
        for class_name, class_info in self.classes.items():
            if not class_info.get('is_abstract'):
                key_attrs = [attr_info for attr, attr_info in class_info['attributes'].items() if attr_info.get('is_key')]
                if len(key_attrs) != 1 or key_attrs[0].get('type') != 'str':
                    raise ValueError(f"Class {class_name} should have exactly one key Attribute of type string.")
        
        # Check 3: If Attribute has is_key="true", it implies required=true
        for class_name, class_info in self.classes.items():
            for attr, attr_info in class_info['attributes'].items():
                if attr_info.get('is_key') and not attr_info.get('required'):
                    raise ValueError(f"Attribute {attr} in Class {class_name} with is_key='true' should also have required='true'.")

    def _parse_xml(self, xml_content):
        """
        Parses the XML content to populate the internal data structures.

        The XML content should have a structure where all `Class` elements are wrapped 
        inside a `Classes` root element.

        Parameters:
            xml_content (str): XML data containing the model specifications.

        Structure of expected XML:
        <Classes>
            <Class name="ClassName1" ...>
                <Attribute ...>attr_name1</Attribute>
                ...
                <Reference ...>ref_name1</Reference>
                ...
            </Class>
            ...
        </Classes>
        """
        root = ET.fromstring(xml_content)

        # Iterating over each 'Class' element under the 'Classes' root
        for class_elem in root.findall('Class'):
            class_name = class_elem.get('name')
            class_info = {
                'is_abstract': class_elem.get('is_abstract') == 'true',
                'extends': class_elem.get('extends'),
                'attributes': {},
                'references': {},
            }

            # Parsing each 'Attribute' element under the current 'Class' element
            for attr_elem in class_elem.findall('Attribute'):
                attr_name = attr_elem.text.strip()
                attribute_info = {
                    'type': attribute_type_to_annotation(attr_elem.get('type')),
                    'is_key': attr_elem.get('is_key') == 'true',
                    'required': True if attr_elem.get('is_key') == 'true' else attr_elem.get('required') == 'true'
                }
                # If the attribute is marked as the key, store its name at the class level
                if attribute_info['is_key']:
                    class_info['key'] = attr_name
                class_info['attributes'][attr_name] = attribute_info

            # Parsing each 'Reference' element under the current 'Class' element
            for ref_elem in class_elem.findall('Reference'):
                ref_name = ref_elem.text.strip()
                reference_info = {
                    'type': ref_elem.get('type'),
                    'multiplicity': ref_elem.get('multiplicity'),
                    'required': ref_elem.get('required') == 'true',
                    'inverse': ref_elem.get('inverse')
                }
                class_info['references'][ref_name] = reference_info

            # Storing the parsed information for the current class
            self.classes[class_name] = class_info

    def get_class_names(self) -> List[str]:
        """
        Returns all known Class names as list of strings
        """
        return list(self.classes.keys())
    
    def get_key_attribute(self, class_name: str) -> str:
        """
        Returns the key attribute for the given class.

        Parameters:
            class_name (str): Name of the class.

        Returns:
            str: Name of the key attribute.
        """
        return self.classes[class_name]['key']

    def get_reference_type(self, class_name: str, reference_name: str) -> str:
        """
        Returns the type of the given reference for the specified class.

        Parameters:
            class_name (str): Name of the class.
            reference_name (str): Name of the reference.

        Returns:
            str: Type of the reference (e.g., another class name).
        """
        return self.classes[class_name]['references'][reference_name]['type']

    def is_multi_reference(self, class_name: str, reference_name: str) -> bool:
        """
        Checks if the given reference for the specified class is a multi-reference.

        Parameters:
            class_name (str): Name of the class.
            reference_name (str): Name of the reference.

        Returns:
            bool: True if multi-reference, False otherwise.
        """
        return self.classes[class_name]['references'][reference_name]['multiplicity'] == 'multi'

    def is_attribute_required(self, class_name: str, attribute_name: str) -> bool:
        """
        Checks if the given attribute for the specified class is required.

        Parameters:
            class_name (str): Name of the class.
            attribute_name (str): Name of the attribute.

        Returns:
            bool: True if the attribute is required, False otherwise.
        """
        return self.classes[class_name]['attributes'][attribute_name]['required']

    def is_reference_required(self, class_name: str, reference_name: str) -> bool:
        """
        Checks if the given reference for the specified class is required.

        Parameters:
            class_name (str): Name of the class.
            reference_name (str): Name of the reference.

        Returns:
            bool: True if the reference is required, False otherwise.
        """
        return self.classes[class_name]['references'][reference_name]['required']
