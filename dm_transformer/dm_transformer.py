import os
import re
import traceback
from xml.etree.ElementTree import Element, fromstring
from typing import List

# region Additional Helper Functions for XML Parsing

def read_xml_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read().strip()

def split_into_class_blocks(xml_content):
    class_definitions = xml_content.split('</Class>')
    class_definitions = [class_def.strip() + '</Class>' for class_def in class_definitions if class_def.strip()]
    return class_definitions

def remove_whitespace_between_tags(xml_content: str) -> str:
    return re.sub(r'>\s*<', '><', xml_content)

def get_declared_classes(class_elements: List[Element]) -> List[str]:
    declared_classes = [class_element.attrib["name"] for class_element in class_elements]
    return declared_classes

def get_reference_maps(class_info: Element) -> dict:
    reference_maps = {}
    for ref in class_info.findall('Reference'):
        inv_name = ref.attrib.get("inverse")
        if inv_name is not None:
            reference_name = ref.text
            reference_maps[reference_name] = inv_name

    return reference_maps

# endregion

# region Helper Functions for Variable Definitions
import_statements = [
    "from typing import List",
    "from abc import ABC",
    "from datetime import datetime"
]

def attribute_type_to_annotation(attr_type):
    return {
        "text": "str",
        "int": "int",
        "pos_geo": "tuple",
        "float": "float",
        "datetime": "datetime",
    }.get(attr_type, "str")

def generate_attribute_code(attribute):
    attr_type = attribute_type_to_annotation(attribute.attrib["type"])
    return f"{attribute.text}: {attr_type}"

def generate_reference_code(reference):
    ref_type = reference.attrib["type"]
    if reference.attrib["multiplicity"] == "mono":
        return f"{reference.text}: '{ref_type}'"
    elif reference.attrib["multiplicity"] == "multi":
        return f"{reference.text}: List['{ref_type}'] = []"
    
# endregion

# region Input Validation

def validate_class_definition(class_info: dict, unvalidated_classes: List[dict]) -> bool:
    """
    PARAMS:
    class_info (dict): raw XML-code of a single class from <Class to </Class>
    unvalidated_classes (List[dict]): list of dicts containting all declared classes, not validated
    RETURNS:
    true if XML-code complies with format characterization
    false otherwise
    """
    declared_classes = get_declared_classes(unvalidated_classes)

    # Validate Class attributes
    # - existence of required attributes
    if "name" not in class_info.attrib:
        raise ValueError("Missing 'name' attribute in Class element.")
    # - no unexpected attributes
    for attr in class_info.attrib:
        if attr not in ["name", "is_abstract", "extends"]:
            raise ValueError(f"Unexpected attribute '{attr}' in Class element {class_info.attrib.get('name')}.")
    # - data types
    #   "name" already string -> valid
    if class_info.attrib.get("is_abstract") not in ["true", "false", None]:
        raise ValueError(f"Invalid value for 'is_abstract' attribute in Class element {class_info.attrib.get('name')}.")
    if class_info.attrib.get("extends") is not None and class_info.attrib.get("extends") not in declared_classes:
        raise ValueError(f"Invalid value for 'extends' attribute in Class element {class_info.attrib.get('name')}.")

    # Validate Sub Elements
    # - no unexpected sub elements
    for element in class_info:
        if element.tag not in ["Collection", "Attribute", "Reference"]:
            raise ValueError(f"Unexpected element '{element.tag}' in Class element {class_info.attrib.get('name')}.")
    key_count = 0
    # - validate Attribute elements
    for attr in class_info.findall("Attribute"):
        validate_attribute_info(attr)
        if attr.attrib.get("is_key") == "true":
            key_count += 1
    if not ((not class_info.attrib.get("is_abstract") == "true" and key_count == 1) or (class_info.attrib.get("is_abstract") == "true" and key_count == 0)):
        raise ValueError(f"Invalid number of Attributes declared as 'is_key' ({key_count}) in Class element {class_info.attrib.get('name')}.")
    # - validate Reference elements
    for ref in class_info.findall("Reference"):
        validate_reference_info(ref, unvalidated_classes)
    # - existence of required sub elements
    if class_info.attrib.get("is_abstract") != "true":
        # - validate Collection element
        #   - exactly one item
        if len(class_info.findall("Collection")) == 0:
            raise ValueError("Missing 'Collection' element in non-abstract Class.")
        if len(class_info.findall("Collection")) > 1:
            raise ValueError("More than one 'Collection' element found in Class.")
        #   - get collection item
        collection = class_info.find("Collection")
        #   - no attributes
        if collection.attrib and len(collection.attrib) > 0:
            raise ValueError("Unexpected attributes in 'Collection' element.")
        #   - no sub elements
        if len(list(collection)) > 0:
            raise ValueError("Unexpected sub-elements in 'Collection' element.")
        #   - contains text
        if not collection.text:
            raise ValueError("Missing text content in 'Collection' element.")
    else:
        #   - no collection element
        if len(class_info.findall("Collection")) > 0:
            raise ValueError("'Collection' element in abstract Class.")

    return True

def validate_attribute_info(attribute_info: dict) -> bool:
    """
    PARAMS:
    attribute_info (dict): Dictionary containing the attributes and content of an Attribute element
    RETURNS:
    true if the Attribute element complies with format characterization
    false otherwise
    """
    # Validate required attributes
    if "type" not in attribute_info.attrib:
        raise ValueError("Missing 'type' attribute in Attribute element.")

    # Validate type attribute value
    if attribute_info.attrib["type"] not in ["text", "int", "pos_geo", "float", "datetime"]:
        raise ValueError(f"Invalid 'type' value '{attribute_info.attrib['type']}' in Attribute element.")

    # Validate is_key attribute if present
    if "is_key" in attribute_info.attrib and attribute_info.attrib["is_key"] not in ["true", "false"]:
        raise ValueError(f"Invalid 'is_key' value '{attribute_info.attrib['is_key']}' in Attribute element.")

    # Validate required attribute if present and not implied by is_key
    if "required" in attribute_info.attrib and attribute_info.attrib["required"] not in ["true", "false"]:
        raise ValueError(f"Invalid 'required' value '{attribute_info.attrib['required']}' in Attribute element.")
    if "required" not in attribute_info.attrib and attribute_info.get("is_key") != "true":
        raise ValueError("Missing 'required' attribute in Attribute element when 'is_key' is not true.")

    # Validate that the element contains text (the attribute name)
    if not attribute_info.text:
        raise ValueError("Missing attribute name (text content) in Attribute element.")

    return True

def validate_reference_info(reference_info: dict, unvalidated_classes: List[dict]) -> bool:
    """
    PARAMS:
    reference_info (dict): Element object containing the attributes and content of a Reference element
    unvalidated_classes (List[dict]): List of all declared classes
    RETURNS:
    true if the Reference element complies with format characterization
    false otherwise
    """

    # Validate required attributes
    if "type" not in reference_info.attrib or "multiplicity" not in reference_info.attrib or "required" not in reference_info.attrib:
        raise ValueError("Missing required attributes in Reference element.")

    # Validate type attribute value (must be one of the declared classes)
    target_class_name = reference_info.attrib["type"]
    target_class = next((cls for cls in unvalidated_classes if cls.attrib["name"] == target_class_name), None)
    if target_class is None:
        raise ValueError(f"Invalid 'type' value '{target_class_name}' in Reference element.")
    
    # Validate inverse if given
    inv_name = reference_info.attrib.get("inverse")
    if inv_name is not None:
        # Look for a Reference subelement with the name matching inv_name
        inverse_found = False
        for ref in target_class.findall('Reference'):
            if ref.text == inv_name:
                inverse_found = True
                break

        if not inverse_found:
            raise ValueError(f"Inverse reference '{inv_name}' not found in class '{reference_info.attrib['type']}'.")
        
    # Validate multiplicity attribute value
    if reference_info.attrib["multiplicity"] not in ["mono", "multi"]:
        raise ValueError(f"Invalid 'multiplicity' value '{reference_info.attrib['multiplicity']}' in Reference element.")

    # Validate required attribute value
    if reference_info.attrib["required"] not in ["true", "false"]:
        raise ValueError(f"Invalid 'required' value '{reference_info.attrib['required']}' in Reference element.")

    # Validate that the element contains text (the reference name)
    if not reference_info.text:
        raise ValueError("Missing reference name (text content) in Reference element.")

    return True

# endregion

def generate_class_code(class_info):
    attrs = class_info.attrib
    all_attributes = class_info.findall("Attribute")
    all_references = class_info.findall("Reference")
    # Extract key attribute
    key_attribute = next((attr for attr in all_attributes if attr.get("is_key") == "true"), None)

    class_code = []
    # Add class definition line
    if "is_abstract" in attrs and attrs["is_abstract"] == "true":
        class_code.append(f'class {attrs["name"]}(ABC):')
    else:
        class_code.append(f'class {attrs["name"]}' + (f'({attrs["extends"]})' if ("extends" in attrs and attrs["extends"]) else "") + ':')

    # Add empty line after class definition
    class_code.append('')

    # Add key_name
    if key_attribute is not None:
        class_code.append(f"    key_name = '{key_attribute.text}'")
    # Define attributes with type annotations
    for attribute in all_attributes:
        # skip key attribute, will get defined later
        if attribute == key_attribute:
            continue
        class_code.append(f'    {generate_attribute_code(attribute)}')
    # Define references with type annotations
    for reference in all_references:
        class_code.append(f'    {generate_reference_code(reference)}')
    # Add empty line after variable definition
    class_code.append('')

    # only add constructor if class is not abstract
    if "is_abstract" in attrs and attrs["is_abstract"] == "true":
        return "\n".join(class_code)
    
    # Extract required attributes, including key attributes, required references, optional attributes, optional references
    required_attributes = [attr for attr in all_attributes if attr.get("required") == "true" and attr.get("is_key") != "true"]
    if required_attributes:
        required_attributes.insert(0, key_attribute)
    else:
        required_attributes = [key_attribute]
    required_references = [ref for ref in all_references if ref.get("required") == "true"]
    optional_attributes = [attr for attr in all_attributes if attr.get("required") != "true" and attr.get("is_key") != "true"]
    optional_references = [ref for ref in all_references if ref.get("required") != "true"]

    # Generate list of constructor params for each required attribute and reference
    constructor_params = [f"{attr.text}: {attribute_type_to_annotation(attr.attrib['type'])}" for attr in required_attributes]
    constructor_params.extend([f"{ref.text}: '{ref.attrib['type']}'" for ref in required_references])
    constructor_params.extend([f"{attr.text}: {attr.attrib['type']} = None" for attr in optional_attributes])
    constructor_params.extend([f"{ref.text}: '{ref.attrib['type']}' = None" if ref.attrib["multiplicity"] == "mono" else f"{ref.text}: List['{ref.attrib['type']}'] = []" for ref in optional_references])

    # Concatenate params list into single string
    constructor_params_code = ",\n                 ".join(constructor_params)
    
    # Add constructor
    class_code.append(f"    def __init__(self{', ' + constructor_params_code}):")
    # Initiate all attributes (always at least one: key)
    for attr in all_attributes:
        # differentiate between key_attribute and regular attributes
        if attr == key_attribute:
            class_code.append(f"        self._{key_attribute.text} = {key_attribute.text}")
        else:
            class_code.append(f"        self.{attr.text} = {attr.text}")
    # Initiate all references
    if all_references:
        for ref in all_references:
            # differentiate between mono and multi references
            if ref.attrib['multiplicity'] == "mono":
                class_code.append(f"        self.{ref.text} = {ref.text}")
            elif ref.attrib['multiplicity'] == "multi":
                class_code.extend([f"        if {ref.text}:", f"            self.{ref.text}.extend({ref.text})"])

    # Add key property
    class_code.extend(["", "    @property", "    def key(self):", "        return getattr(self, self.key_name)"])
    # Add key attribute also as property
    class_code.extend(["", "    @property", f"    def {key_attribute.text}(self):", f"        return self._{key_attribute.text}"])
    # Add default __str__ implementation
    class_code.extend(["", "    def __str__(self):", f"        return f'({attrs['name']}) {{self.key}}'"])
    return "\n".join(class_code) + "\n"

def process_file(input_path: str, output_path: str):
    """
    PARAMS:
    input_path (str): absolute or relative path to input xml file
    output_path (str): absolute or relative path to output .py file
    """

    # Validate input file path
    if not os.path.exists(input_path) or not input_path.endswith('.xml'):
        print("Error: Invalid input file path or file type. Please provide a valid XML file.")
        return

    # Read XML content from input file
    xml_content = remove_whitespace_between_tags(read_xml_file(input_path))

    # Split into class blocks
    class_blocks = split_into_class_blocks(xml_content)

    # Collect declared classes for validation context
    declared_classes = []
    for class_block in class_blocks:
        try:
            declared_classes.append(fromstring(class_block))
        except Exception as e:
            print(f"Error: Invalid class definition encountered at:\n\n{class_block}\n\nError message: {str(e)}")
            traceback.print_exc()


    # Validate class definitions and parse
    validated_classes = []
    validated_references = {}
    for class_info in declared_classes:
        try:
            if validate_class_definition(class_info, declared_classes):
                validated_classes.append(class_info)
                # Get the reference maps for this class
                reference_maps = get_reference_maps(class_info)
                
                # Update the unified dictionary with the reference maps, checking for duplicates
                for key, value in reference_maps.items():
                    if key in validated_references:
                        raise ValueError(f"Duplicate reference key '{key}' encountered in class {class_info.attrib.get('name')}.")
                    validated_references[key] = value
        except Exception as e:
            print(f"Error: Invalid class definition encountered at Class {class_info.attrib.get('name')}.\nError message: {str(e)}")
            traceback.print_exc()

    # Convert the validated_references dictionary to a Python code string
    inv_rel_map_code = "INV_REL_MAP = {\n" + ",\n".join([f"    '{k}': '{v}'" for k, v in validated_references.items()]) + "\n}"

    # Generate Import statement block
    import_block = "\n".join(import_statements)

    # Generate Python classes code
    generated_python_code = [
        import_block,
        inv_rel_map_code  # Include the INV_REL_MAP code string
    ]
    generated_python_code.extend([generate_class_code(class_info) for class_info in validated_classes])
    final_code = "\n\n".join(generated_python_code)

    # Validate output file path (optional)
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        print(f"Error: Output directory {output_dir} does not exist.")
        return

    # Write to output file
    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(final_code)

    print(f"Python classes generated successfully and written to {output_path}")

if __name__ == "__main__":
    in_path = "datamodels/ResourceTransmission_v1.xml"
    out_path = "model_code/resource_transmission_v1.py"

    process_file(in_path, out_path)