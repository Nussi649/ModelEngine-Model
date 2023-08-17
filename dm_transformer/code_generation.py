from xml.etree.ElementTree import Element
from typing import List


# region Helper Functions for Variable Definitions

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

def generate_init(key_attrib: Element,
                  required_attrib: List[Element],
                  optional_attrib: List[Element],
                  required_refs: List[Element],
                  optional_refs: List[Element]):
    """
    FUNCTION generate_init
    PARAMS:
    key_attrib (Element): XML-Element of the key attribute's <Attribute> Block
    required_attrib (List[Element]): List of XML-Elements of all required attributes except key_attrib, may be empty
    optional_attrib (List[Element]): List of XML-Elements of optional attributes, may be empty
    required_refs (List[Element]): List of XML-Elements of required references, may be empty
    optional_refs (List[Element]): List of XML-Elements of optional references, may be empty
    RETURNS:
    List of Codeline Strings representing the init function
    """
    result = [""]
    # Compile list of parameters with type hints and default values
    params = [(key_attrib.text, attribute_type_to_annotation(key_attrib.get('type')), None)]
    params.extend([(el.text, attribute_type_to_annotation(el.get('type')), " = None") for el in required_attrib])
    params.extend([(el.text, attribute_type_to_annotation(el.get('type')), " = None") for el in optional_attrib])
    params.extend([(el.text, f"'{el.get('type')}'", " = None") for el in required_refs])
    params.extend([(el.text, f"'{el.get('type')}'", " = []" if el.get("multiplicity") == "multi" else " = None") for el in optional_refs])

    # Generate string of all parameters as used in output code
    param_strings = [f"{param_name}: {param_type}{default if default else ''}" for param_name, param_type, default in params]
    param_string = ",\n                 ".join(param_strings)
    # Append mini_mode parameter
    param_string += ", *,\n                   mini_mode=False"
    result.append(f"    def __init__(self, {param_string}):")

    # Start with common operations (regardles of mini_mode or not)
    # Add line to store mini_mode adequately
    result.append("        self._mini_mode = mini_mode")
    # Initiate key attribute
    result.append(f"        self._{key_attrib.text} = {key_attrib.text}")

    # in case there are no further attributes (extraordinarily simple classes) break at this point
    if not required_attrib and not required_refs and not optional_attrib and not optional_refs:
        return result
    # Differentiate between call as reduced or not
    result.append("        if not mini_mode:")
    # Add parameter validation checks
    required_param_names = [el.text for el in required_attrib]
    required_param_names.extend([el.text for el in required_refs])
    required_param_checks = [f"if {param_name} is None:\n                raise ValueError('{param_name} is required')" for param_name in required_param_names]
    
    # Indent the function body
    result.extend([f"            {check}" for check in required_param_checks])
    # Instantiate required attributes
    if required_attrib:
        for attr in required_attrib:
            result.append(f"            self.{attr.text} = {attr.text}")
    # Instantiate required references
    if required_refs:
        for ref in required_refs:
            # differentiate between mono and multi references
            if ref.attrib['multiplicity'] == "mono":
                result.append(f"            self.{ref.text} = {ref.text}")
            elif ref.attrib['multiplicity'] == "multi":
                result.extend([f"            if {ref.text}:", f"                self.{ref.text}.extend({ref.text})"])
    # Instantiate optional attributes
    if optional_attrib:
        for attr in optional_attrib:
            result.append(f"            self.{attr.text} = {attr.text}")
    # Instantiate required references
    if optional_refs:
        for ref in optional_refs:
            # differentiate between mono and multi references
            if ref.attrib['multiplicity'] == "mono":
                result.append(f"            self.{ref.text} = {ref.text}")
            elif ref.attrib['multiplicity'] == "multi":
                result.extend([f"            if {ref.text}:", f"                self.{ref.text}.extend({ref.text})"])

    return result

def generate_reduced_generator(key_attrib: Element):
    name = key_attrib.text
    result = [
        "",
        "    @classmethod",
        f"    def create_reduced(cls, {name}: str):",
        f"        instance = cls({name}={name}, mini_mode=True)",
        "        return instance"
    ]
    return result

def generate_upgrade(required_attrib: List[Element],
                     optional_attrib: List[Element],
                     required_refs: List[Element],
                     optional_refs: List[Element]):
    """
    FUNCTION generate_upgrade
    PARAMS:
    required_attrib (List[Element]): List of XML-Elements of all required attributes except key_attrib, may be empty
    optional_attrib (List[Element]): List of XML-Elements of optional attributes, may be empty
    required_refs (List[Element]): List of XML-Elements of required references, may be empty
    optional_refs (List[Element]): List of XML-Elements of optional references, may be empty
    RETURNS:
    List of Codeline Strings representing the upgrade function
    """
    # calculate required attributes without key_attribute (this is already set)
    attributes = []
    for el in required_attrib:
        is_key = el.get("is_key")
        if is_key and is_key.lower() == "true":
            continue
        attributes.append(el)
    result = [""]
    params = [(el.text, attribute_type_to_annotation(el.get('type')), None) for el in attributes]
    params.extend([(el.text, attribute_type_to_annotation(el.get('type')), " = None") for el in optional_attrib])
    params.extend([(el.text, f"'{el.get('type')}'", None) for el in required_refs])
    params.extend([(el.text, f"'{el.get('type')}'", " = []" if el.get("multiplicity") == "multi" else " = None") for el in optional_refs])

    param_strings = [f"{param_name}: {param_type}{default if default else ''}" for param_name, param_type, default in params]
    param_string = ",\n                ".join(param_strings)
    result.extend([
        f"    def upgrade(self{', ' + param_string if param_string else ''}):",
        "        # abort if object is already in full mode",
        "        if not self._mini_mode:",
        "            return False"
        ])

    # Add parameter validation checks
    required_param_names = [el.text for el in required_attrib]
    required_param_names.extend([el.text for el in required_refs])
    required_param_checks = [f"if {param_name} is None:\n            raise ValueError('{param_name} is required')" for param_name in required_param_names]
    
    # Indent the function body
    result.extend([f"        {check}" for check in required_param_checks])
    result.append(f"        self._mini_mode = False")
    result.extend([f"        if {param[0]}:\n              self.{param[0]} = {param[0]}" for param in params])
    result.append("        return True")

    return result
    
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
    required_references = [ref for ref in all_references if ref.get("required") == "true"]
    optional_attributes = [attr for attr in all_attributes if attr.get("required") != "true" and attr.get("is_key") != "true"]
    optional_references = [ref for ref in all_references if ref.get("required") != "true"]

    # Generate list of constructor params (all optional - generator functions handle required checks)
    class_code.extend(generate_init(key_attribute, required_attributes, optional_attributes, required_references, optional_references))
    # Add reduced generator
    class_code.extend(generate_reduced_generator(key_attribute))
    # Add upgrade function
    class_code.extend(generate_upgrade(required_attributes, optional_attributes, required_references, optional_references))
    # Add mini_mode property
    class_code.extend([
        "",
        "    @property",
        "    def mini_mode(self):",
        "        return self._mini_mode"
    ])
    # Add key property
    class_code.extend([
        "",
        "    @property",
        "    def key(self):",
        "        return getattr(self, self.key_name)"
        ])
    # Add key attribute also as property
    class_code.extend([
        "",
        "    @property",
        f"    def {key_attribute.text}(self):",
        f"        return self._{key_attribute.text}"
        ])
    # Add default __str__ implementation
    class_code.extend([
        "",
        "    def __str__(self):",
        f"        return f'({attrs['name']}) {{self.key}}'"])
    return "\n".join(class_code) + "\n"