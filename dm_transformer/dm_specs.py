from lxml import etree
import xml.etree.ElementTree as ET
from typing import List, Tuple

type_map = {
    "str": str,
    "float": float,
    "int": int,
    "bool": bool
}

def attribute_type_to_annotation(attr_type: str) -> str:
    return {
        "text": "str",
        "int": "int",
        "pos_geo": "tuple",
        "float": "float",
        "boolean": "bool",
        "datetime": "datetime",
    }.get(attr_type, "str")

class ModelSpecifications:

# region Setup
    def __init__(self, xml_path=None, xml_content=None, xsd_path="dm_transformer/data_models/format_specifications/dm_specification_schema.xsd"):
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
# endregion

# region Helper functions
    def _is_valid_reference(self, source_class: str, reference_name: str, target_class: str) -> bool:
        """
        Validates if the reference between the source and target classes is valid according to the model specifications.

        Parameters:
            source_class (str): Name of the source class.
            reference_name (str): Name of the reference.
            target_class (str): Name of the target class.

        Returns:
            bool: True if the reference is valid, False otherwise.
        """
        valid_references = [details['type'] for ref, details in self.classes[source_class]['references'].items() if ref == reference_name]
        return target_class in valid_references
# endregion

# region Primitive functions
    def get_class_names(self) -> List[str]:
        """
        Returns all known Class names as list of strings
        """
        return list(self.classes.keys())
    
    def get_attributes(self, class_name: str, indiv_key=True) -> List[str]:
        """
        Provides the names of all attributes of a given class.

        Parameters:
            class_name (str): Name of the class.
            indiv_key (bool): Whether to use the individual key name (e.g. 'identifier') or the general key name 'key'.

        Returns:
            List[str]: List of attribute names as strings
        """
        class_dict = self.classes.get(class_name)
        if not class_dict:
            return None
        
        attributes = class_dict.get('attributes', [])

        # If indiv_key is False, replace the individual key name with the general 'key' name
        if not indiv_key:
            individual_key_name = class_dict.get('key', 'key')
            attributes = ['key' if attr == individual_key_name else attr for attr in attributes]

        return attributes

    def get_references(self, class_name: str) -> List[str]:
        """
        Provides the names of all references of a given class.

        Parameters:
            class_name (str): Name of the class.

        Returns:
            List[str]: List of reference names as strings
        """
        class_dict = self.classes.get(class_name)
        return class_dict['references'] if class_dict else None

    def has_any_reference(self, class_name: str) -> bool:
        """
        Validates whether a class contains references.

        Parameters:
            class_name (str): Name of the class.

        Returns:
            bool: True if the class has any variables that point to objects of other Model classes.
        """
        return bool(self.classes[class_name]['references'])

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
        # transform to lower case
        reference_name = reference_name.lower()
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
        # transform to lower case
        reference_name = reference_name.lower()
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
# endregion

# region Complex functions
    def validate_arguments(self, class_name: str, args: dict, strict=True) -> bool:
        """
        Validates if the provided arguments match the model specifications for the given class. Assumes class is not abstract.

        Parameters:
            class_name (str): Name of the class to validate against.
            args (dict): Dictionary of attribute names and their values.
            strict (bool): If True, checks all required parameters. If False, only checks provided parameters.

        Returns:
            bool: True if arguments match the model specifications, False otherwise.
        """
        class_info = self.classes.get(class_name)
        if not class_info:
            return False
        args_copy = args.copy()
        key_name = class_info.get('key')
        if key_name and 'key' in args_copy:
            args_copy[key_name] = args_copy.pop('key')

        # If class is not in the specifications, return False
        if not class_info:
            return False

        # Validate attributes
        for attr, info in class_info['attributes'].items():
            attr_type = info['type']
            is_required = info['required']

            # If the attribute is required but not provided, return False
            if strict and is_required and attr not in args_copy:
                return False

            # If the attribute is provided, validate its type
            if attr in args_copy and not isinstance(args_copy[attr], type_map.get(attr_type)):
                return False

        # Validate references
        for ref, info in class_info['references'].items():
            ref_type = info['type']
            is_required = info['required']

            # If the reference is required but not provided, return False
            if strict and is_required and ref not in args:
                return False

            # If the reference is provided, validate its type
            if ref in args and not self._is_valid_reference(class_name, ref, type(args[ref]).__name__):
                return False

        return True

    def separate_attrs_refs(self, class_name: str, args: dict) -> Tuple[dict, dict]:
        """
        Separate the given arguments into attributes and references based on the class specification.

        Parameters:
            class_name (str): The name of the class for which the arguments are intended.
            args (dict): Dictionary of arguments.

        Returns:
            Tuple[dict, dict]: A tuple containing two dictionaries. The first is the attributes and the second is the references.
        """

        attributes = {}
        references = {}

        # Get the key attribute name for the class
        key_attribute_name = self.classes[class_name]['key']

        # Get attributes and references from the class specification
        class_attributes = set(attr for attr, _ in self.classes[class_name]['attributes'].items())
        class_references = set(ref for ref, _ in self.classes[class_name]['references'].items())

        # If the key attribute name exists in class_attributes and is not 'key', replace it with 'key'
        if key_attribute_name in class_attributes and key_attribute_name != 'key':
            class_attributes.remove(key_attribute_name)
            class_attributes.add('key')

        # Check for erroneous keys
        valid_keys = class_attributes.union(class_references)
        erroneous_keys = set(args.keys()) - valid_keys
        if erroneous_keys:
            raise ValueError(f"Invalid keys found: {', '.join(erroneous_keys)}. These are not valid attributes or references for class '{class_name}'.")

        # Separate attributes and references based on the class specification
        for key, value in args.items():
            if key in class_attributes:
                attributes[key] = value
            elif key in class_references:
                references[key] = value

        return attributes, references

    def get_variable_summary(self, class_name: str) -> List[str]:
        """
        Provides a textual summary of the attributes and references associated with a given class.

        Parameters:
            class_name (str): Name of the class.

        Returns:
            List[str]: List of strings summarizing each attribute and reference
        """
        class_dict = self.classes.get(class_name)
        if not class_dict:
            return None
        attr_sum = [f"{key + (' (key)' if data['is_key'] else '')} : {data['type'] + ' (required)' if data['required'] else ' (optional)'}" for key, data in class_dict['attributes'].items()]
        ref_sum = [f"{key} : {data['type'] + ' (required)' if data['required'] else ' (optional)' } ({data['multiplicity']}){' Inverse: ' + data['inverse'] if data['inverse'] else ''}" for key, data in class_dict['references'].items()]
        return attr_sum + ref_sum

# endregion