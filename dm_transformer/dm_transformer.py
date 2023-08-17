import os
import re
import traceback
from xml.etree.ElementTree import Element, fromstring
from validation import validate_class_definition
from code_generation import generate_class_code


import_statements = [
    "from typing import List",
    "from abc import ABC",
    "from datetime import datetime"
]

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

def get_reference_maps(class_info: Element) -> dict:
    reference_maps = {}
    for ref in class_info.findall('Reference'):
        inv_name = ref.attrib.get("inverse")
        if inv_name is not None:
            reference_name = ref.text
            reference_maps[reference_name] = inv_name

    return reference_maps

# endregion

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
        invalid_usage_block,
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
    #script_directory = os.path.dirname(os.path.abspath(__file__))
    #in_path = os.path.join(script_directory, "datamodels", "ResourceTransmission_v1.xml")
    in_path = "dm_transformer/datamodels/ResourceTransmission_v1.xml"
    out_path = "model_code/resource_transmission_v1.py"

    process_file(in_path, out_path)