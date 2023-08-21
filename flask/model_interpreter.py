import importlib.util
import io
import sys
import inspect
from abc import ABC
from neo4j import GraphDatabase
from types import ModuleType
from pathlib import Path
from dm_specs import ModelSpecifications
from typing import Iterable, get_args, get_type_hints

create_object_query = "CREATE (n:{class_name}) SET n = $attributes"
get_object_query = """
    MATCH (n:{class_name}) WHERE n.{key_name} = '{key_value}'
    OPTIONAL MATCH (n)-[r]->(related)
    RETURN n, collect(r) as relationships, collect(related) as related_nodes
    """

BASIC_TYPES = {float, int, str}

class ModuleUnavailableError(RuntimeError):
    pass

class ModelInterpreter:
    loaded_module: ModuleType
    driver: GraphDatabase.driver
    execution_scope: dict
    class_types: dict

# region Constructor and @property Attributes

    def __init__(self, URI: str, AUTH: tuple, model_code=None):
        self._URI = URI
        self._AUTH = AUTH
        self.driver = GraphDatabase.driver(URI, auth=AUTH)
        if model_code is not None:
            self.init_module(self.load_model_code(model_code))
        # Load and parse the specifications file
        self.model_specs = ModelSpecifications(xml_path="/workspace/data_models/ResourceTransmission_v1.xml")

    @property
    def URI(self):
        return self._URI
    
    @property
    def AUTH(self):
        return self._AUTH

# endregion
    
# region Helper functions

    def load_model_code(self, file_name: str) -> ModuleType:
        file_path = Path('/data/model_code') / file_name

        if not file_path.exists():
            raise FileNotFoundError(f"{file_path} does not exist.")

        # Constructing the module spec
        spec = importlib.util.spec_from_file_location(file_name, file_path)

        # Creating a new module based on the spec
        module = importlib.util.module_from_spec(spec)

        # Executing the module
        spec.loader.exec_module(module)

        # Adding the module to the system modules
        sys.modules[spec.name] = module

        return module
    
    def init_module(self, module: ModuleType):
        self.loaded_module = module
        # Iterate through all the attributes of the loaded module
        for name, obj in inspect.getmembers(self.loaded_module):
            # Check if the object is a class
            if inspect.isclass(obj):
                # Check if the class is not abstract
                if not issubclass(obj, ABC):
                    # Create a dictionary with the desired name
                    dict_name = f"objects_{name}"
                    setattr(self.loaded_module, dict_name, {})
        self.execution_scope = dict(self.loaded_module.__dict__)
    def resolve_class_name(self, class_name):
        if self.loaded_module is None:
            raise ModuleUnavailableError("No model code loaded.")
        if class_name not in self.model_specs.classes:
            raise ValueError(f"Class {class_name} not recognized.")
        return getattr(self.loaded_module, class_name)

    def merge_relationship_nodes(self, class_name, records):
        references = {}

        # Iterate over records to build the desired dictionary
        for record in records:
            # get name of relationship (reference)
            rel_type = record["relationship_type"].lower()
            # get name of related class
            ref_class_name = self.model_specs.get_reference_type(class_name, rel_type)
            # get attributes of related node
            referred_node = dict(record["related_node_properties"])

            # Check if this relationship type indicates a list or a single object
            expected_type = self.model_specs.get_reference_multiplicity(ref_class_name, rel_type)
            
            if expected_type == "multi":
                if rel_type in references:
                    references[rel_type].append(referred_node)
                else:
                    references[rel_type] = [referred_node]
            else:
                references[rel_type] = referred_node

        return references

    def load_node(self, class_name, key, include_related=True):
        """
        Load a node and, optionally, its related nodes and relationships from the database.

        Parameters:
            class_name (str): The name of the node's class.
            key (str): The key to identify the node.
            include_related (bool): Whether to include related nodes and relationships in the result.

        Returns:
            A dictionary containing the main node's data and its related nodes' data.
        """
        # Get the key attribute name from the target class
        key_attribute_name = self.model_specs.get_key_attribute(class_name)
        # Base query to retrieve the node
        query = f"MATCH (n:{class_name}) WHERE n.{key_attribute_name} = $key "

        # If related nodes and relationships are to be included, modify the query
        if include_related:
            query += """
            OPTIONAL MATCH (n)-[r]->(related)
            RETURN 
                n as main_node,
                type(r) as relationship_type, 
                related as related_node_properties
            """
        else:
            query += "RETURN n as main_node"

        with self.driver.session() as session:
            result = session.run(query, key=key)
            records = result.data()

            if not records:
                return None

            main_node_data = dict(records[0]['main_node'])
            
            if include_related:
                related_info = self.merge_relationship_nodes(class_name, records)
                return {
                    'node': main_node_data,
                    'related': related_info
                }
            else:
                return {
                    'node': main_node_data
                }

# endregion                    

# region CRUD related

    def get_object(self, class_name: str, key: str, reduced=False, object_data=None):
        """
        Finds an object of type class_name with the specified key.
        It first checks in the already loaded objects, then queries the database.
        If neither yields a result, the object does not exist.
        
        Parameters:
            class_name (str): name of the object class
            key (str): value of key attribute of object to be identified by
            reduced (bool): Whether to load the object in mini_mode or fully.
            object_data (dict, optional): Dictionary containing the object's data, skipping the database query if provided.
            
        Returns:
            Object of type class_name if it exists, None otherwise
        """
        target_class = self.resolve_class_name(class_name)

        # Check if object is available in loaded context aka object register
        register = getattr(self.loaded_module, f"objects_{class_name}")
        obj = register.get(key, None)
        
        # If object data is not provided, and it's either not in the register or in mini_mode, load data from DB
        if not object_data and (not obj or obj.mini_mode):
            object_data = self.load_node(class_name, key, include_related=not reduced)
            if not object_data:
                return None

        node_data = object_data['node']
        related_nodes_data = object_data.get('related_nodes', [])
        relationships_data = object_data.get('relationships', [])
        compiled_rels = self.merge_relationship_nodes(related_nodes_data, relationships_data)

        # Instantiate as a reduced object
        if not obj:
            obj = target_class.create_reduced(key)

        # If not in reduced mode, load related nodes and update the main object
        if not reduced:
            if not obj.mini_mode:
                return obj
            
            related_objects = {}
            for rel in relationships_data:
                rel_name = rel['type'].lower()
                related_key = rel['end_node_id']
                related_obj = self.get_object(rel['end_node_class'], related_key, reduced=True, object_data=related_nodes_data.get(related_key))
                
                if isinstance(related_objects.get(rel_name), list):
                    related_objects[rel_name].append(related_obj)
                else:
                    related_objects[rel_name] = [related_obj]

            # Upgrade the object using node data, attributes, and related objects
            all_data = {**node_data, **related_objects}
            all_data.pop(obj.key_name)
            obj.upgrade(**all_data)

            # Store the object in the register
            register[key] = obj

        return obj

    def create_object(self, class_name: str, args: dict):
        """
        Creates a new object of type class_name. If an object with the same key already exists, returns that object.
        Otherwise, creates a new one according to the provided parameters.

        Parameters:
            class_name (str): name of the object class.
            args (dict): dictionary of constructor parameters.

        Returns:
            Object of type class_name. Either a pre-existing object with the same key or the newly created object.
        """
        # Resolve target class, key_name, and register
        target_class = self.resolve_class_name(class_name)
        key_name = self.model_specs.get_key_attribute(class_name)
        register = getattr(self.loaded_module, f"objects_{class_name}")
        
        # Check if object already exists
        existing_object = self.get_object(class_name, args[key_name])
        if existing_object:
            return existing_object

        # Instantiate the object
        obj = target_class(**args)

        # Separate attributes from references
        attrs = {k: v for k, v in args.items() if not hasattr(v, 'key')}
        user_refs = {k: v for k, v in args.items() if hasattr(v, 'key')}

        # Prepare relationships for DB synchronization
        relationships = {}
        for ref_name, ref_object in user_refs.items():
            rel_type = ref_name.upper()  # capitalized relationship name
            rel_target_class_name = type(ref_object).__name__
            relationships[rel_type] = {
                'class_name': rel_target_class_name,
                'key': ref_object.key
            }

        # Construct and run the creation query
        node_attrs = ", ".join(f"{k}: '{v}'" for k, v in attrs.items()) #TODO: only ' if value is not numerical
        query_create = f"CREATE (a:{class_name} {{ {node_attrs} }})"
        if relationships:
            query_create += f"\nWITH a"
        for rel_name, rel_data in relationships.items():
            relationship_type = rel_name.upper()
            inv_rel_type = self.loaded_module.INV_REL_MAP.get(rel_name, "").upper()
            key_attribute_name = self.model_specs.get_key_attribute(rel_data['class_name'])
            query_create += f"\nMATCH (b_{rel_name}:{rel_data['class_name']} {{{key_attribute_name}: '{rel_data['key']}'}})"
            query_create += f"\nCREATE (a)-[:{relationship_type}]->(b_{rel_name})"
            if inv_rel_type:
                query_create += f"\nCREATE (b_{rel_name})-[:{inv_rel_type}]->(a)"
        
        with self.driver.session() as session:
            session.run(query_create)
        # TODO: validate result
        # Store the object in the register
        register[obj.key] = obj

        return obj

    def update_object(self, class_name: str, key: str, args: dict):
        """
        Updates an existing object of type class_name identified by the key.
        Updates both the object's representation in the program and in the database.

        Parameters:
            class_name (str): The name of the object class.
            key (str): The key to identify the object.
            args (dict): Dictionary of attributes and relationships to update.

        Returns:
            The updated object or an appropriate result/error message.
        """
        # 1. Object Lookup
        obj = self.get_object(class_name, key)
        if not obj:
            raise ValueError(f"No object of type {class_name} with key {key} found.")

        # Separate attributes and relationships
        attributes = {k: v for k, v in args.items() if not hasattr(v, 'key')}
        relationships = {k: v for k, v in args.items() if hasattr(v, 'key')}

        # 2. Update Database Node
        # Construct the Cypher query to update attributes
        set_clause = ", ".join(f"n.{attr_name} = $value_{attr_name}" for attr_name in attributes.keys())
        query = f"""
        MATCH (n:{class_name})
        WHERE n.{obj.key_name} = $key
        SET {set_clause}
        """
        query_params = {"key": key}
        query_params.update({f"value_{attr_name}": value for attr_name, value in attributes.items()})

        with self.driver.session() as session:
            result = session.run(query, query_params)
            # Check the result of the query
            if not result.single():
                raise RuntimeError(f"Failed to update attributes of node type {class_name} with key {key}.")

        # Update relationships
        for rel_name, rel_object in relationships.items():
            relationship_type = rel_name.upper()
            related_class_name = type(rel_object).__name__
            key_attribute_name = self.model_specs.get_key_attribute(related_class_name)
            related_key_value = rel_object.key
            inv_rel_type = self.loaded_module.INV_REL_MAP.get(rel_name, "").upper()

            # Detach old relationship
            query_detach = f"""
            MATCH (a:{class_name} {{{obj.key_name}: '{key}'}})-[r:{relationship_type}]->(b)
            DELETE r"""
            if inv_rel_type:
                query_detach += f"""
                OPTIONAL MATCH (b)-[r_inv:{inv_rel_type}]->(a) DELETE r_inv"""
            
            # Create new relationship and its inverse if defined
            query_relationship = f"""
            MATCH (a:{class_name} {{{obj.key_name}: '{key}'}})
            MATCH (b:{related_class_name} {{{key_attribute_name}: '{related_key_value}'}})
            MERGE (a)-[:{relationship_type}]->(b)"""
            if inv_rel_type:
                query_relationship += f"""
                MERGE (b)-[:{inv_rel_type}]->(a)"""
            
            with self.driver.session() as session:
                session.run(query_detach)
                session.run(query_relationship)

        # 3. Update Python Object
        # Update attributes
        for attr_name, value in attributes.items():
            setattr(obj, attr_name, value)
        # Update relationships
        for rel_name, rel_object in relationships.items():
            setattr(obj, rel_name, rel_object)

        # 4. Return the updated object
        return obj


    # TODO: 
    # create_multiple_objects
    # get_multiple_objects
    # update_object
    # update_multiple_objects
    # delete_object
    # delete_multiple_objects

# endregion


    def process_request(self, input: str):
        # get execution scope
        self.execution_scope['self'] = self
        # Capture the standard output
        captured_output = io.StringIO()
        sys.stdout = captured_output

        # Execute the code and capture the result of the last expression
        result = None
        try:
            # If the input contains '=', assume it's an assignment and use exec
            if '=' in input:
                # Execute the assignment
                exec(input, self.execution_scope)
                # Parse the variable name and retrieve its value
                var_name = input.split('=')[0].strip()
                result = self.execution_scope.get(var_name)
            else:
                # Otherwise, assume it's an expression and use eval
                result = eval(input, self.execution_scope)
        except Exception as e:
            result = str(e)

        # Reset the standard output
        sys.stdout = sys.__stdout__

        # Get the captured output as a string
        output = captured_output.getvalue()

        return {"output": output, "result": str(result)}
    