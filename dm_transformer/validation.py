from typing import List
from xml.etree.ElementTree import Element


def get_declared_classes(class_elements: List[Element]) -> List[str]:
    declared_classes = [class_element.attrib["name"] for class_element in class_elements]
    return declared_classes

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
    if "is_key" in attribute_info.attrib:
        if attribute_info.attrib["is_key"] not in ["true", "false"]:
            raise ValueError(f"Invalid 'is_key' value '{attribute_info.attrib['is_key']}' in Attribute element.")
        if attribute_info.get("type") != "text":
            raise ValueError(f"Invalid key attribute {attribute_info.text}. Claims is_key = True but type is not text.")

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
