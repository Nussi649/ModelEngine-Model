import os
from dm_specs import ModelSpecifications
from code_generation import generate_class_code


import_statements = [
    "from typing import List, Optional, Union",
    "from abc import ABC",
    "from datetime import datetime",
    "from model_entity import ModelEntity"
]

# region Additional Helper Functions for XML Parsing

def read_xml_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read().strip()

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

    # Use ModelSpecifications for parsing and validation
    model_specs = ModelSpecifications(xml_path=input_path)

    # Collect Relationship Inverses
    relationship_inverses = {}
    for _, class_details in model_specs.classes.items():
        for ref_name, ref_details in class_details.get("references", {}).items():
            inv = ref_details.get("inverse")
            if inv is not None:
                relationship_inverses[ref_name] = inv

    # Generate Static Code Blocks
    import_block = "\n".join(import_statements)
    inv_rel_map_code = "INVERSE_RELATIONSHIPS = {\n" + ",\n".join([f"    '{k}': '{v}'" for k, v in relationship_inverses.items()]) + "\n}"
    generated_python_code = [
        import_block,
        inv_rel_map_code,  # Include the INV_REL_MAP code string
        "register = {}"
    ]

    # Iterate through all classes and generate corresponding code
    for class_name, class_details in model_specs.classes.items():
        generated_python_code.append(generate_class_code(class_name, class_details))

    # Concatenate code lines
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
    in_path = "data_models/ResourceTransmission_v1.xml"
    out_path = "../model_code/test.py"

    process_file(in_path, out_path)