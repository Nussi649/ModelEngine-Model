from typing import List

# region Helper Functions for Variable Definitions

def generate_attribute_code(attr_name: str, attr_details: dict) -> str:
    """
    Convert attribute details into a type-annotated string.
    
    PARAMETERS:
    - attr_name (str): The name of the attribute.
    - attr_details (dict): The details of the attribute, including its type.

    RETURNS:
    - A string representing the type-annotated attribute.
    """
    return f"{attr_name}: {attr_details['type']}"

def generate_reference_code(ref_name: str, ref_details: dict) -> str:
    """
    Convert reference details into a type-annotated string.
    
    PARAMETERS:
    - ref_name (str): The name of the reference.
    - ref_details (dict): The details of the reference, including its type and multiplicity.

    RETURNS:
    - A string representing the type-annotated reference.
    """
    ref_type = ref_details["type"]
    if ref_details["multiplicity"] == "multi":
        ref_type = f"List['{ref_type}']"
    return f"{ref_name}: {ref_type}"

def generate_init(class_details: dict) -> List[str]:
    """
    FUNCTION generate_init
    PARAMS:
    class_details (dict): details about class as per data format used in ModelSpecifications
    RETURNS:
    List of Codeline Strings representing the init function
    """
    # Generate the parameter string for the method definition
    key_name = class_details['key']
    # attributes can be assumed to contain key attribute because generate_init would not be called for an abstract class
    attributes = dict(class_details.get("attributes", {}))
    attributes.pop(class_details['key'])

    # Initialize a list to hold lines of the __init__ method
    init_lines = []
    all_params = ["self"]
    all_params += [f"{attr_name}: {attr_details['type']}=None" for attr_name, attr_details in class_details.get("attributes", {}).items()]
    for ref_name, ref_details in class_details.get("references", {}).items():
        ref_type = ref_details["type"]
        if ref_details["multiplicity"] == "multi":
            ref_type = f"List['{ref_type}']"
        all_params.append(f"{ref_name}: {ref_type}=None")
    param_string = ",\n                 ".join(all_params) + ", *,\n                   mini_mode=False"
    
    # Add method definition with parameters
    init_lines.append(f"    def __init__({param_string}):")

    # Validate if key attribute is provided - class can be assumed to be non-abstract because otherwise there would be no init
    init_lines.extend([f"        if not {key_name}:",
                       f"            raise ValueError('Attribute {key_name} is required')"])
    
    # Add super initialization
    init_lines.append(f"        super().__init__(key={key_name}, mini_mode=mini_mode)")
    
    if attributes or class_details.get("references"):
        # Mini mode check
        init_lines.append("        if not mini_mode:")
        # Check and assign required attributes and references
        for attr_name, attr_details in class_details.get("attributes", {}).items():
            if attr_name == key_name:
                continue
            if attr_details.get("required"):
                init_lines.append(f"            if {attr_name} is None:")
                init_lines.append(f"                raise ValueError('Attribute {attr_name} is required')")
            init_lines.append(f"            self.{attr_name} = {attr_name}")

        for ref_name, ref_details in class_details.get("references", {}).items():
            if ref_details.get("required"):
                init_lines.append(f"            if {ref_name} is None:")
                init_lines.append(f"                raise ValueError('Reference {ref_name} is required')")
            if ref_details["multiplicity"] == "multi":
                init_lines.append(f"            self.{ref_name}.extend({ref_name})")
            else:
                init_lines.append(f"            self.{ref_name} = {ref_name}")

    return init_lines

def generate_upgrade(class_details: dict) -> List[str]:
    """
    FUNCTION generate_upgrade
    Generate the upgrade function based on the provided class details.

    PARAMETERS:
    - class_details (dict): Details about class as per data format used in ModelSpecifications.

    RETURNS:
    - List of Codeline Strings representing the upgrade function.
    """

    # Initialize a list to hold lines of the upgrade method
    upgrade_lines = [""]
    
    # Generate the parameter string for the method definition
    key_name = class_details['key']
    all_params = ["self"]
    all_params += [f"{attr_name}: {attr_details['type']}=None" for attr_name, attr_details in class_details.get("attributes", {}).items() if attr_name != key_name]
    for ref_name, ref_details in class_details.get("references", {}).items():
        ref_type = ref_details["type"]
        if ref_details["multiplicity"] == "multi":
            ref_type = f"List['{ref_type}']"
        all_params.append(f"{ref_name}: {ref_type}=None")
    param_string = ",\n                ".join(all_params)
    
    # Start the method definition
    upgrade_lines.append(f"    def upgrade({param_string}):")
    
    # Check if object is in full mode and return False if so
    upgrade_lines.extend([
        "        # Abort if object is already in full mode",
        "        if not self._mini_mode:",
        "            return False"
    ])

    # attributes can be assumed to contain key attribute because generate_upgrade would not be called for an abstract class
    attributes = dict(class_details.get("attributes", {}))
    attributes.pop(class_details['key'])
    
    if attributes or class_details.get("references", {}):
        upgrade_lines.append("\n        # Validate provided parameters")
        # Check and validate required attributes and references
        for attr_name, attr_details in attributes.items():
            if not class_details['is_abstract'] and attr_name == class_details['key']:
                continue
            if attr_details.get("required"):
                upgrade_lines.append(f"        if {attr_name} is None:")
                upgrade_lines.append(f"            raise ValueError('Attribute {attr_name} is required for upgrade')")
        for ref_name, ref_details in class_details.get("references", {}).items():
            if ref_details.get("required"):
                upgrade_lines.append(f"        if {ref_name} is None:")
                upgrade_lines.append(f"            raise ValueError('Reference {ref_name} is required for upgrade')")
    
        # Assign attributes and references
        upgrade_lines.append("\n        # Assign attributes and references")
        for attr_name in class_details.get("attributes", {}).keys():
            if attr_name != key_name:  # Skip the key attribute
                upgrade_lines.append(f"        self.{attr_name} = {attr_name} if {attr_name} is not None else self.{attr_name}")
        for ref_name, ref_details in class_details.get("references", {}).items():
            if ref_details["multiplicity"] == "multi":
                upgrade_lines.append(f"        if {ref_name} is not None:")
                upgrade_lines.append(f"            self.{ref_name}.extend({ref_name})")
            else:
                upgrade_lines.append(f"        self.{ref_name} = {ref_name} if {ref_name} is not None else self.{ref_name}")
    
    # Set mini_mode to False and return True
    upgrade_lines.extend([
        "\n        # Indicate successful upgrade",
        "        self._mini_mode = False",
        "        return True"
    ])

    return upgrade_lines
    
# endregion

def generate_class_code(class_name: str, class_details: dict) -> List[str]:
    class_code = []
    # Add class definition line
    if class_details['is_abstract']:
        class_code.append(f'class {class_name}(ABC):')
    else:
        extends = class_details.get('extends')
        class_code.append(f'class {class_name}(ModelEntity' + (f', {extends})' if extends is not None else ")") + ':')

    # Add empty line after class definition
    class_code.append('')

    # set flag to indicate whether to close the variables block with an empty line
    has_variables = False
    # Define attributes with type annotations
    for attr_name, attr_details in class_details['attributes'].items():
        # skip key attribute, will get defined later
        if not class_details['is_abstract'] and attr_name == class_details['key']:
            continue
        class_code.append(f'    {generate_attribute_code(attr_name, attr_details)}')
        has_variables = True
    # Define references with type annotations
    for ref_name, ref_details in class_details['references'].items():
        class_code.append(f'    {generate_reference_code(ref_name, ref_details)}')
        has_variables = True

    if has_variables:
        # Add empty line after variable definition
        class_code.append('')

    # only add constructor if class is not abstract
    if class_details['is_abstract']:
        return "\n".join(class_code)

    # Generate list of constructor params (all optional - generator functions handle required checks)
    class_code.extend(generate_init(class_details))
    # Add upgrade function
    class_code.extend(generate_upgrade(class_details))
    # Add key attribute also as property
    class_code.extend([
        "",
        "    @property",
        f"    def {class_details['key']}(self):",
        f"        return self.key"
        ])
    # 
    return "\n".join(class_code)