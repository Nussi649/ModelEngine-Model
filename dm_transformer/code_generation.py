from typing import List

# region Helper Functions for Variable Definitions

def generate_attribute_code(attr_name: str, attr_details: dict) -> str:
    """Generate code for attribute with type annotations."""
    return f"{attr_name}: {attr_details['type']}"

def generate_reference_code(ref_name: str, ref_details: dict) -> str:
    """Generate code for reference with type annotations."""
    ref_type = f"'{ref_details['type']}'"
    return f"{ref_name}: {f'List [{ref_type}]' if ref_details['multiplicity'] == 'multi' else f'{ref_type}'}"

def generate_init(class_name: str, class_details: dict) -> List[str]:
    """
    Generate the __init__ method for the class.
    
    Args:
    - class_name (str): Name of the class that should be initiated
    - class_details (dict): Details about class as per data format used in ModelSpecifications.
    
    Returns:
    - List of Codeline Strings representing the init function.
    """
    key_name = class_details['key']
    attributes = class_details.get("attributes", {}).copy()
    if key_name in attributes:
        attributes['key'] = attributes.pop(key_name)
    references = class_details.get("references", {})
    collections = class_details.get("collections", {})

    params = [
        "self",
        *[f"{attr}: {details['type']}=None" for attr, details in attributes.items()],
        *[
            f"{ref}: List['{ref_details['type']}']=[]" if ref_details['multiplicity'] == 'multi' 
            else f"{ref}: '{ref_details['type']}'=None" 
            for ref, ref_details in references.items()
        ]
    ]
    # compile params together with line breaks for readability
    param_string = ",\n                 ".join(params) + f", *,\n{' ' * 19}mini_mode=False"

    # Initialize a list to hold lines of the __init__ method
    init_lines = [
        f"{' ' * 4}def __init__({param_string}):",
        f"{' ' * 4}    if not key:",
        f"{' ' * 4}        raise ValueError('Attribute key is required')",
        f"{' ' * 4}    super().__init__(key=key, mini_mode=mini_mode)"
    ]

    # Initialize Collection objects
    for coll, details in collections.items():
        init_lines.append(f"{' ' * 8}self.{coll}: 'Collection' = Collection({class_name}, key, '{coll}', {details['type']})")
    
    # From here on, key attribute will be only redundant
    attributes.pop('key') # attributes can be assumed to contain key attribute because generate_init would not be called for an abstract class

    if attributes or references:
        # Mini mode check
        init_lines.append(f"{' ' * 8}if not mini_mode:")
        # Check and assign attributes
        for attr, details in attributes.items():
            if details.get("required"):
                init_lines.extend([
                    f"{' ' * 12}if {attr} is None:",
                    f"{' ' * 12}    raise ValueError('Attribute {attr} is required')"
                ])
            init_lines.append(f"{' ' * 12}self.{attr}: {details['type']} = {attr}")

        # Check and assign references
        for ref, details in references.items():
            if details.get("required"):
                init_lines.extend([
                    f"{' ' * 12}if not {ref}:",
                    f"{' ' * 12}    raise ValueError('Reference {ref} is required')"
                ])
            init_lines.append(f"{' ' * 12}self.{ref}: " + (f"List ['{details['type']}']" if details['multiplicity'] == 'multi' else f"'{details['type']}'") + f" = {ref}")

    init_lines.append("")
    return init_lines

def generate_upgrade(class_details: dict) -> List[str]:
    """
    Generate the upgrade function based on the provided class details.

    Args:
    - class_details (dict): Details about class as per data format used in ModelSpecifications.

    Returns:
    - List of Codeline Strings representing the upgrade function.
    """
    key_name = class_details['key']
    attributes = class_details.get("attributes", {}).copy()
    attributes.pop(key_name) # key attribute would be redundant for whole function
    references = class_details.get("references", {})

    params = [
            "self",
            *[f"{attr}: {details['type']}=None" for attr, details in attributes.items() if attr != key_name],
            *[
                f"{ref}: List['{ref_details['type']}']=None" if ref_details['multiplicity'] == 'multi' 
                else f"{ref}: '{ref_details['type']}'=None" 
                for ref, ref_details in references.items()
            ]
        ]
    param_string = f",\n{' ' * 16}".join(params)
    
    upgrade_lines = [
        f"{' ' * 4}def upgrade({param_string}):",
        f"{' ' * 4}    # Abort if object is already in full mode",
        f"{' ' * 4}    if not self._mini_mode:",
        f"{' ' * 4}        return False"
    ]

    # Check and assign attributes
    for attr, details in attributes.items():
        if details.get("required"):
            upgrade_lines.extend([
                f"{' ' * 8}if {attr} is None:",
                f"{' ' * 8}    raise ValueError('Attribute {attr} is required for upgrade')"
            ])
        upgrade_lines.append(f"{' ' * 8}self.{attr} = {attr} if {attr} is not None else getattr(self, '{attr}', None)")
    
    # Check and assign references
    for ref, details in references.items():
        if details.get("required"):
            upgrade_lines.extend([
                f"{' ' * 8}if {ref} is None:",
                f"{' ' * 8}    raise ValueError('Reference {ref} is required for upgrade')"
            ])
        if details["multiplicity"] == "multi":
            upgrade_lines.extend([
                f"{' ' * 8}if {ref} is not None:",
                f"{' ' * 8}    self.{ref}.extend({ref})"
            ])
        else:
            upgrade_lines.append(f"{' ' * 8}self.{ref} = {ref} if {ref} is not None else getattr(self, '{ref}', None)")
    
    # Set mini_mode to False and return True
    upgrade_lines.extend([
        f"{' ' * 8}# Indicate successful upgrade",
        f"{' ' * 8}self._mini_mode = False",
        f"{' ' * 8}return True"
    ])

    return upgrade_lines
    
def generate_composite(composite_name: str, composite_details: dict) -> List[str]:
    """
    Generate the class definition for a composite.
    
    Args:
    - composite_name (str): Name of the composite that should be generated.
    - composite_details (dict): Details about composite as per data format used in ModelSpecifications.
    
    Returns:
    - List of Codeline Strings representing the class.
    """
    attributes = composite_details.get("attributes", {})
    
    # Constructing parameters for __init__ method
    params = [
        "self",
        *[f"{attr}: {details['type']}" for attr, details in attributes.items()]  # Making every attribute required
    ]
    param_string = ", ".join(params)

    # Initialize a list to hold lines of the class
    composite_lines = [
        f"class {composite_name}(Composite):",
        f"{' ' * 4}def __init__({param_string}):"
    ]

    # Assign attributes
    for attr, details in attributes.items():
        composite_lines.append(f"{' ' * 8}self.{attr} = {attr}")
        
    composite_lines.append("")
    return "\n".join(composite_lines)


# endregion

def generate_class_code(class_name: str, class_details: dict) -> str:
    """
    Generate the complete class code based on the provided class name and details.
    Args:
    - class_name (str): Name of the class.
    - class_details (dict): Details about class as per data format used in ModelSpecifications.
    Returns:
    - Class code as a string.
    """
    attributes = class_details.get("attributes", {})
    references = class_details.get("references", {})
    key_name = class_details.get('key', None)
    extends = class_details.get('extends')
    base_classes = ', '.join(['ModelObject', extends] if extends else ['ModelObject'])
    if class_details['is_abstract']:
        base_classes = "ABC"

    # Add class definition line
    class_code = [f"class {class_name}({base_classes}):", ""]

    # only add constructor if class is not abstract
    if class_details['is_abstract']:    
        # Define attributes with type annotations
        for attr, details in attributes.items():
            class_code.append(f"{' ' * 4}{generate_attribute_code(attr, details)}")
        # Define references with type annotations
        for ref, details in references.items():
            class_code.append(f"{' ' * 4}{generate_reference_code(ref, details)}")

        if attributes or references:
            # Add empty line after variable definition
            class_code.append('')
        return "\n".join(class_code)

    # Generate list of constructor params (all optional - generator functions handle required checks)
    class_code.extend(generate_init(class_name, class_details))
    # Add upgrade function
    class_code.extend(generate_upgrade(class_details))
    # Add key attribute also as property
    class_code.extend([
        "",
        f"{' ' * 4}@property",
        f"{' ' * 4}def {class_details['key']}(self):",
        f"{' ' * 4}    return self.key"
        ])
    # 
    return "\n".join(class_code)