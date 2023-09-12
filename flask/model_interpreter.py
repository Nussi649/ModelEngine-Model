import importlib.util
import re
import os
import sys
import random
import string
import inspect
import json
from abc import ABC, ABCMeta
from datetime import datetime
from neo4j import GraphDatabase
from types import ModuleType
from pathlib import Path
from collections import defaultdict
from dm_specs import ModelSpecifications
from typing import _SpecialForm, List, Tuple, Any, Union, get_args, get_type_hints

create_object_query = "CREATE (n:{class_name}) SET n = $attributes"
get_object_query = """
    MATCH (n:{class_name}) WHERE n.{key_name} = '{key_value}'
    OPTIONAL MATCH (n)-[r]->(related)
    RETURN n, collect(r) as relationships, collect(related) as related_nodes
    """

valid_commands = ["get", "create", "add", "io", "help"]

known_dicts = ["INVERSE_RELATIONSHIPS", "register"]

command_help = """
_______ Command Usage _______

- Any input is directly evaluated as a Python expression unless it starts with the '>' character.
- Expressions starting with '>' are treated as special commands.

_______ Available Commands _______

> help [command] - Provides further information about the usage of each command.

> get [class_name] [attribute/reference=value] ... [attribute/reference=value] optional: as [name of return list] 
    - Loads a model object or list of model objects of type class_name based on attribute/reference=value specifications. 
    - Results can optionally be stored under a specific name.

> create [class_name] -help 
    - Provides information about the required and optional parameters for a specific class.

> create [class_name] [attribute/reference=value] ... [attribute/reference=value] 
    - Creates a new model object with the specified parameters in both program context and persistent storage.

> add [expression that evaluates to a model object or list of model objects] 
    - Adds a model object or list of model objects created in program context to persistent storage.

_______ Referring to Model Objects _______

- To refer to a specific model object within an expression, use the format: @Class.Key
- This format can be used anywhere within your expression to fetch and utilize model objects.

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
        self.model_specs = ModelSpecifications(xml_path="/workspace/data_models/FinanceHelper.xml",
                                               xsd_path="/workspace/data_models/format_specifications/dm_specification_schema.xsd")

    @property
    def URI(self):
        return self._URI
    
    @property
    def AUTH(self):
        return self._AUTH

# endregion
    
# region Helper functions

    def load_model_code(self, file_name: str) -> ModuleType:
        file_path = Path('/workspace/data_models/model_code') / file_name

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
        ## Iterate through all the attributes of the loaded module
        #for name, obj in inspect.getmembers(self.loaded_module):
        #    # Check if the object is a class
        #    if inspect.isclass(obj):
        #        # Check if the class is not abstract
        #        if not issubclass(obj, ABC):
        #            # Create a dictionary with the desired name
        #            dict_name = f"objects_{name}"
        #            setattr(self.loaded_module, dict_name, {})
        self.execution_scope = dict(self.loaded_module.__dict__)

    def resolve_class_name(self, class_name):
        if self.loaded_module is None:
            raise ModuleUnavailableError("No model code loaded.")
        if class_name not in self.model_specs.classes:
            raise ValueError(f"Class {class_name} not recognized.")
        return getattr(self.loaded_module, class_name)
    
    def get_register(self, class_name: str):
        general_register = getattr(self.loaded_module, "register")
        register = general_register.get(class_name, None)
        if not register:
            general_register[class_name] = {}
            register = general_register[class_name]
        return register
    
    def object_from_node(self, class_name, node, records=None, reduced_object=None):
        """
        Constructs a full Python object from a Neo4j node.

        Parameters:
            class_name: the expected class name
            node: The Neo4j node.
            records (list): Optional list of related records.
            reduced_object (ModelEntity): Optional reduced object that can be upgraded to full object representation

        Returns:
            The corresponding Python object.
        """
        if reduced_object:
            obj_class = type(reduced_object)
            assert class_name == obj_class.__name__
        else:
            obj_class = self.resolve_class_name(class_name)
        key = node['key']
        custom_key = self.model_specs.get_key_attribute(class_name)

        register = self.get_register(class_name)
        obj = register.get(key, None)
        if reduced_object and obj:
            assert reduced_object == obj, f"Found two different objects for class {class_name} with key {key}. This should not happen."
        if obj:
            reduced_object = obj
        # Extract attributes and references from the records
        attributes = {key: node[key] for key in node if key != "key" and key != custom_key}
        references = self._fetch_references_from_records(class_name, records) if records else {}

        if reduced_object:
            if not reduced_object.mini_mode:
                reduced_object._mini_mode = True
            reduced_object.upgrade(**attributes, **references)
            register[key] = reduced_object
            return reduced_object
        new_obj = obj_class(key=key, **attributes, **references)
        register[key] = new_obj
        return new_obj
    
    def load_node(self, class_name: str, key: str, tx, reduced=False, reduced_object=None):
        """
        Fetches the node from the database and returns its corresponding Python object.

        Parameters:
            class_name (str): The class name of the node.
            key (str): The key to identify the node.
            tx: The active transaction.
            include_related (bool): Whether to load related nodes or just the main node.

        Returns:
            The corresponding Python object or None if not found.
        """
        # Base query to retrieve the node
        query = f"MATCH (n:{class_name}) WHERE n.key = $key "

        # If related nodes and relationships are to be included, modify the query
        if not reduced:
            query += """
            OPTIONAL MATCH (n)-[r]->(related)
            RETURN 
                n as main_node,
                type(r) as relationship_type, 
                related as related_node_properties
            """
        try:
            result = tx.run(query, key=key)
            records = result.data()
            
            if not records:
                return None

            obj = self.object_from_node(class_name, records[0]['main_node'], records if not reduced else None, reduced_object)
            return obj

        except Exception as e:
            # TODO: Handle the error robustly
            raise e
        
    def _objects_match(self, obj1, obj2) -> bool:
        """
        Check if two objects match in every attribute and reference.
        """
        attrs = self.model_specs.get_attributes(type(obj1).__name__)
        refs = self.model_specs.get_references(type(obj1).__name__)
        
        for attr in attrs:
            if getattr(obj1, attr) != getattr(obj2, attr):
                return False

        for ref in refs:
            if getattr(obj1, ref) != getattr(obj2, ref):
                return False

        return True
    
    def _fetch_references_from_records(self, class_name, records):
        references = {}
        register_cache = {}  # Cache for object registers

        for record in records:
            relationship = record.get('relationship_type')
            rel_node = record.get('related_node_properties')
            if not relationship or not rel_node:
                continue
            
            relationship = relationship.lower()
            rel_class_name = self.model_specs.get_reference_type(class_name, relationship)
            if rel_class_name not in register_cache:
                register_cache[rel_class_name] = self.get_register(rel_class_name)
            
            related_obj = register_cache[rel_class_name].get(rel_node['key'])
            if not related_obj:
                related_class = self.resolve_class_name(rel_class_name)
                related_obj = related_class.create_reduced(rel_node['key'])
                register_cache[rel_class_name][rel_node['key']] = related_obj
            
            if self.model_specs.is_multi_reference(class_name, relationship):
                references.setdefault(relationship, []).append(related_obj)
            else:
                references[relationship] = related_obj

        return references

    def _construct_create_query(self, class_name, attrs, refs):
        node_attrs_list = []
        for k, v in attrs.items():
            if isinstance(v, datetime):
                formatted_datetime = v.isoformat()
                node_attr = f'{k}: datetime("{formatted_datetime}")'
            else:
                node_attr = f"{k}: {json.dumps(v)}"
            node_attrs_list.append(node_attr)

        node_attrs = ", ".join(node_attrs_list)
        query = [f"CREATE (a:{class_name} {{ {node_attrs} }})"]
        expected_rel_created = 0

        if any(ref_data for ref_data in refs.values()):
            for rel_name, rel_data in refs.items():
                relationship_type = rel_name.upper()
                inv_rel_type = self.loaded_module.INVERSE_RELATIONSHIPS.get(rel_name, "").upper()

                # Check if rel_data is a list (indicating multi-reference)
                if isinstance(rel_data, list):
                    for item in rel_data:
                        related_class_name = type(item).__name__
                        related_key = item.key
                        query.append("WITH a")
                        query.append(f"MATCH (b_{rel_name}:{related_class_name} {{key: '{related_key}'}})")
                        query.append(f"CREATE (a)-[:{relationship_type}]->(b_{rel_name})")
                        expected_rel_created += 1
                        if inv_rel_type:
                            query.append(f"CREATE (b_{rel_name})-[:{inv_rel_type}]->(a)")
                            expected_rel_created += 1

                else:  # Single reference
                    if isinstance(rel_data, dict):
                        related_class_name = rel_data['class_name']
                        related_key = rel_data['key']
                    else:  # It's an object
                        related_class_name = type(rel_data).__name__
                        related_key = rel_data.key

                    query.append("WITH a")
                    query.append(f"MATCH (b_{rel_name}:{related_class_name} {{key: '{related_key}'}})")
                    query.append(f"CREATE (a)-[:{relationship_type}]->(b_{rel_name})")
                    expected_rel_created += 1
                    if inv_rel_type:
                        query.append(f"CREATE (b_{rel_name})-[:{inv_rel_type}]->(a)")
                        expected_rel_created += 1

        return "\n".join(query), expected_rel_created
    
    def _construct_update_node_query(self, class_name, key, attrs):
        set_clause = ", ".join(f"n.{attr_name} = ${attr_name}" for attr_name in attrs.keys())
        query = f"""
        MATCH (n:{class_name})
        WHERE n.key = $key
        SET {set_clause}
        """
        query_params = {"key": key, **attrs}
        return query, query_params

    def _construct_update_relationships_query(self, class_name, key, refs):
        detach_queries = []
        attach_queries = []
        for rel_name, rel_object in refs.items():
            relationship_type = rel_name.upper()
            related_class_name = type(rel_object).__name__
            inv_rel_type = self.loaded_module.INVERSE_RELATIONSHIPS.get(rel_name, "").upper()

            detach_queries.append(f"""
            MATCH (a:{class_name} {{key: '{key}'}})-[r:{relationship_type}]->(b)
            DELETE r""")
            if inv_rel_type:
                detach_queries.append(f"""
                OPTIONAL MATCH (b)-[r_inv:{inv_rel_type}]->(a) DELETE r_inv""")
            
            attach_queries.append(f"""
            MATCH (a:{class_name} {{key: '{key}'}})
            MATCH (b:{related_class_name} {{key: '{rel_object.key}'}})
            MERGE (a)-[:{relationship_type}]->(b)""")
            if inv_rel_type:
                attach_queries.append(f"""
                MERGE (b)-[:{inv_rel_type}]->(a)""")

        return "\n".join(detach_queries), "\n".join(attach_queries)
# endregion                    

# region CRUD related

    def get_object(self, class_name: str, key: str, reduced=False):
        """
        Finds an object of type class_name with the specified key.
        It first checks in the already loaded objects, then queries the database.
        If neither yields a result, the object does not exist.
        
        Parameters:
            class_name (str): name of the object class
            key (str): value of key attribute of object to be identified by
            reduced (bool): Whether to load the object in mini_mode or fully.
            
        Returns:
            Object of type class_name if it exists, None otherwise
        """
        register = self.get_register(class_name)

        # Check if object is available in loaded context aka object register
        obj = register.get(key, None)

        # If an object was found and it's in full mode or only reduced mode is required
        if obj and (not obj.mini_mode or reduced):
            return obj
        # Fetch the object data from the database because we have nothing loaded and need to know, if the object even exists
        with self.driver.session() as session:
            tx = session.begin_transaction()
            obj = self.load_node(class_name, key, tx, reduced)
            tx.commit()
        return obj

    def get_multiple_objects(self, class_key_pairs: List[Tuple[str, str]], reduced=False) -> List[Any]:
        """
        Retrieves multiple objects based on a list of class and key pairs.

        Parameters:
            class_key_pairs (list): A list of tuples, each containing a class name and key.
            reduced (bool): Whether to load the objects in mini_mode or fully.

        Returns:
            list: A list of objects corresponding to the class and key pairs.
        """
        objects = []
        # Group by class_name for more efficient querying
        grouped_pairs = defaultdict(list)
        for class_name, key in class_key_pairs:
            grouped_pairs[class_name].append(key)

        with self.driver.session() as session:
            tx = session.begin_transaction()
            for class_name, keys in grouped_pairs.items():
                register = self.get_register(class_name)
                for key in keys:
                    # check register if the object is already loaded
                    obj = register.get(key)
                    # If an object was found and it's in full mode or only reduced mode is required
                    if obj and (not obj.mini_mode or reduced):
                        objects.append(obj)
                        continue
                    obj = self.load_node(class_name, key, tx, reduced_object=obj, include_related=not reduced)
                    # add the result to return list if an object was found
                    if obj:
                        objects.append(obj)
            tx.commit()

        return objects
    
    def find_objects(self, class_name, args, reduced=False): # TODO: Test
        """
        Finds objects of type class_name based on provided properties.
        
        Parameters:
            class_name (str): The class name of the objects to find.
            args (dict): Dictionary of properties and references to use for filtering.
            reduced (bool): Whether to load the object in reduced mode or fully.
            
        Returns:
            List of objects matching the criteria.
        """
        # Validate args
        valid_attributes = self.model_specs.get_attributes(class_name, indiv_key=False)
        valid_references = self.model_specs.get_references(class_name)
        property_filters = []
        relationship_filters = []

        for key, value in args.items():
            if key in valid_attributes:
                property_filters.append(f"n.{key} = {value}")
            elif key in valid_references:
                if isinstance(value, str):  # If value is a key string
                    relationship_key = value
                else:  # If value is an object
                    relationship_key = value.key
                related_class = self.model_specs.get_reference_type(class_name, key)
                relationship_name = key.upper()
                relationship_filters.append(f"(n)-[:{relationship_name}]->(:{related_class} {{key: '{relationship_key}'}})")

        # Construct the Cypher query
        filters = property_filters + relationship_filters
        query_filter = " AND ".join(filters)
        query = f"""
        MATCH (n:{class_name})
        WHERE {query_filter}
        RETURN n
        """

        nodes_to_process = []

        with self.driver.session() as session:
            tx = session.begin_transaction()
            results = tx.run(query)
            
            # Gather nodes to process outside the session
            nodes_to_process = [record['n'] for record in results]
            objects_found = []

            for node in nodes_to_process:
                key = node['key']
                register = self.get_register(class_name)
                obj = register.get(key, None)

                # Check register and handle object
                if not obj or (obj and obj.mini_mode and not reduced):
                    obj = self.load_node(class_name, key, tx, reduced=reduced, reduced_object=obj)
                elif reduced and not obj:
                    obj = self.object_from_node(node, reduced=True)
                
                objects_found.append(obj)
            tx.commit()
        
        return objects_found

    def create_object(self, class_name: str, args: dict, tx=None): # TODO: Test
        """
        Creates a new object of type class_name. If an object with the same key already exists, returns that object.
        Otherwise, creates a new one according to the provided parameters.

        Parameters:
            class_name (str): name of the object class.
            args (dict): dictionary of constructor parameters.
            tx: Optional transaction to run the database query.

        Returns:
            Object of type class_name. Either a pre-existing object with the same key or the newly created object.
        """
        # -- Gather local variables, validate parameters, check for target object in register --
        target_class = self.resolve_class_name(class_name)
        key_name = self.model_specs.get_key_attribute(class_name)
        register = self.get_register(class_name)

        key_value = args.get('key', args.get(key_name))
        if not key_value:
            raise ValueError(f'Key attribute {key_name} not provided in arguments.')

        existing_object = self.get_object(class_name, key_value)
        if existing_object:
            return existing_object

        if not self.model_specs.validate_arguments(class_name, args):
            raise ValueError(f'Invalid Constructor Arguments for class {class_name}: {str(args)}')

        # -- Prepare Object creation and Database Query --
        # Rename custom key name to 'key'
        args['key'] = args.pop(key_name, key_value)

        # Instantiate the object
        obj = target_class(**args)
        attrs, refs = self.model_specs.separate_attrs_refs(class_name, args)

        # Construct the creation query
        query_create, expected_rel_created = self._construct_create_query(class_name, attrs, refs)
        
        # -- Run Query on Database and handle results --
        # Execute the query and handle results
        def execute_query(transaction):
            counters = transaction.run(query_create).consume().counters
            if (counters.nodes_created != 1) or (counters.relationships_created != expected_rel_created):
                raise ValueError(f"Error creating node or relationships in Neo4j. Expected 1 node and {expected_rel_created} relationships but got {counters.nodes_created} nodes and {counters.relationships_created} relationships.")

        if tx:
            execute_query(tx)
        else:
            with self.driver.session() as session:
                session.write_transaction(execute_query)
                
        # Store the object in the register
        register[obj.key] = obj

        return obj
    
    def create_multiple_objects(self, objects_to_create: List[Tuple[str, dict]]): # TODO: Test
        """
        Creates multiple new objects. If an object with the same key already exists, returns that object.
        Otherwise, creates a new one according to the provided parameters.

        Parameters:
            objects_to_create (list): List of tuples. Each tuple consists of class_name (str) and args (dict).

        Returns:
            List of objects created or fetched.
        """
        created_objects = []

        with self.driver.session() as session:
            tx = session.begin_transaction()
            try:
                for class_name, args in objects_to_create:
                    obj = self.create_object(class_name, args, tx=tx)
                    created_objects.append(obj)
                tx.commit()
            except:
                tx.rollback()
                raise

        return created_objects

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
        # 1. Preparations
        # Object Lookup
        obj = self.get_object(class_name, key)
        if not obj:
            raise ValueError(f"No object of type {class_name} with key {key} found.")
        # Check if trying to update the key
        key_name = self.model_specs.get_key_attribute(class_name)
        if key_name in args or 'key' in args:
            raise ValueError("Updating the object's key is not allowed.")
        # Validate arguments
        if not self.model_specs.validate_arguments(class_name, args, strict=False):
            raise ValueError(f'Invalid Update Arguments for class {class_name}: {str(args)}')
        # Separate attributes from references and prepare queries
        attrs, refs = self.model_specs.separate_attrs_refs(class_name, args)
        query, query_params = self._construct_update_node_query(class_name, key, attrs)
        detach_query, attach_query = self._construct_update_relationships_query(class_name, key, refs)

        with self.driver.session() as session:
            tx = session.begin_transaction()
            try:
                # 2. Update Database
                tx.run(query, query_params)
                tx.run(detach_query)
                tx.run(attach_query)
                
                tx.commit()
            except Exception as e:
                tx.rollback()
                raise RuntimeError(f"Failed to update object of type {class_name} with key {key}. Reason: {str(e)}")

        # 3. Update Python Object
        # Update attributes
        for attr_name, value in attrs.items():
            setattr(obj, attr_name, value)
        # Update relationships
        for rel_name, rel_object in refs.items():
            setattr(obj, rel_name, rel_object)

        # 4. Return the updated object
        return obj

    def add_object(self, obj_instance, tx=None) -> bool:
        """
        Synchronizes a given program object instance to the database.
        If an object with the same key already exists in the database, it updates the existing object.
        If not, it creates a new object in the database.

        Parameters:
            obj_instance: An instance of a model object.
            tx: Optional transaction to run the database query.

        Returns:
            bool: True if the operation succeeded, False otherwise.
        """
        
        def core_logic(transaction):
            def prepare_reference(ref_name, ref_value):
                """
                Helper function to process a reference (either mono or multi).
                Returns True if successful, False otherwise.
                """
                # Handle multi-references
                if isinstance(ref_value, list):
                    for item in ref_value:
                        prepare_single_reference(ref_name, item)
                # Handle mono-references
                else:
                    prepare_single_reference(ref_name, ref_value)

            def prepare_single_reference(ref_name, ref_instance):
                """
                Helper function to process a single reference.
                Returns True if successful, False otherwise.
                """
                ref_class_name = type(ref_instance).__name__
                if ref_class_name not in self.model_specs.get_class_names():
                    raise ValueError(f"Invalid object type in reference for {ref_name}.")
                ref_obj = self.get_object(ref_class_name, ref_instance.key)
                if not ref_obj:
                    # Check for inverse relationships
                    inverse_rel = self.loaded_module.INVERSE_RELATIONSHIPS.get(ref_name, "")
                    if inverse_rel:
                        # Alert the caller
                        raise ValueError(f"Inverse relationship found for {ref_name}. Can't handle this for now.")
                    # If the referenced object doesn't exist, add it recursively
                    try:
                        self.add_object(ref_instance, transaction)
                    except Exception as e:
                        raise ReferenceError(f"Failed to make sure required referenced object {str(ref_instance)} exists because of:\r\n{e}\r\nAborting...")
            class_name = type(obj_instance).__name__
            
            # Validate if the instance is of a recognized model object type
            if class_name not in self.model_specs.get_class_names():
                raise ValueError(f"Add object call on wrong object type. Needs to be representing a valid model object class.")
            
            key_name = self.model_specs.get_key_attribute(class_name)
            key_value = obj_instance.key
        
            # Check for existing object in the database by key
            existing_object = self.get_object(class_name, key_value)
            if existing_object:
                if self._objects_match(obj_instance, existing_object):
                    return True
        
            # Compile arguments for object creation. Start with references
            args = {ref: getattr(obj_instance, ref) for ref in self.model_specs.get_references(class_name) if hasattr(obj_instance, ref)}
            
            # Handle references and ensure they exist in the database
            for ref, value in args.items():
                prepare_reference(ref, value)
            
            # also add attributes
            args.update({attr: getattr(obj_instance, attr) for attr in self.model_specs.get_attributes(class_name, indiv_key=False) if hasattr(obj_instance, attr)})

            # Construct the creation query
            attrs, refs = self.model_specs.separate_attrs_refs(class_name, args)
            query_create, expected_rel_created = self._construct_create_query(class_name, attrs, refs)
        
            # Execute the query
            counters = transaction.run(query_create).consume().counters
            if (counters.nodes_created != 1) or (counters.relationships_created != expected_rel_created):
                raise ValueError(f"Error creating node or relationships in Neo4j. Expected 1 node and {expected_rel_created} relationships but got {counters.nodes_created} nodes and {counters.relationships_created} relationships.")
                
            def process_single_reference(expected_type, ref_obj):
                if type(ref_obj).__name__ == expected_type:
                    return self.get_object(ref_type, ref_obj.key)
                return None

            # Make sure that object references to register objects and not some random copy
            for ref_name, ref_value in refs.items():
                ref_type = self.model_specs.get_reference_type(class_name, ref_name)
                is_multi = self.model_specs.is_multi_reference(class_name, ref_name)
                if is_multi:
                    if isinstance(ref_value, list):
                        if not ref_value: # if no objects are referenced, continue
                            continue
                        new_ref_list = []
                        for item in ref_value:
                            processed_item = process_single_reference(ref_type, item)
                            if processed_item:
                                new_ref_list.append(processed_item)
                            else:
                                raise ValueError(f"Unexpected Error: while post-processing the {ref_name} reference of {str(obj_instance)} the expected object {str(ref_value)} could not be acquired. Aborting...")
                        setattr(obj_instance, ref_name, new_ref_list)
                    else:
                        raise ValueError(f"Unexpected Error: while post-processing the expected multi {ref_name} reference of {str(obj_instance)} there was no list encountered. Aborting...")
                else:
                    # Single reference
                    processed_ref = process_single_reference(ref_type, ref_value)
                    if processed_ref:
                        setattr(obj_instance, ref_name, processed_ref)
                    else:
                        raise ValueError(f"Unexpected Error: while post-processing the {ref_name} reference of {str(obj_instance)} the expected object {str(ref_value)} could not be acquired. Aborting...")
            
            # Put added object in register
            self.get_register(class_name)[obj_instance.key] = obj_instance
        if tx:
            core_logic(tx)
        else:
            with self.driver.session() as session:
                result = session.write_transaction(core_logic)
                return result

    def add_multiple_objects(self, obj_instances: List, tx=None) -> bool:
        def do_work(transaction, obj_list):
            added_objects = []
            try:
                for obj in obj_list:
                    self.add_object(obj, transaction)
                    added_objects.append(obj)
                return True
            except Exception as e:
                print(f"Failed to add objects due to: {e}")
                # If an exception happened, rollback changes by removing added objects from register
                register = self.execution_scope["register"]
                for obj in added_objects:
                    del register[type(obj).__name__][obj.key]
                return False

        if tx:  # If a transaction is already provided, use it.
            return do_work(tx, obj_instances)

        else:  # If no transaction is provided, create a session and then a transaction.
            with self.driver.session() as session:
                tx = session.begin_transaction()
                success = do_work(tx, obj_instances)
                if success:
                    tx.commit()
                else:
                    tx.rollback()
                return success

    def delete_object(self, class_name: str, key: str, tx=None): # TODO: Test
        """
        Deletes an existing object of type class_name identified by the key.
        Deletes both the object's representation in the program and in the database.

        Parameters:
            class_name (str): The name of the object class.
            key (str): The key to identify the object.
            tx (Transaction, optional): An optional Neo4j transaction. If not provided, a new session and transaction will be started.
        
        Returns:
            str: A success or error message.
        """

        # 1. Object Lookup
        obj = self.get_object(class_name, key)
        if not obj:
            raise ValueError(f"No object of type {class_name} with key {key} found.")
        
        # 2. Generate Query to Detach Relationships and Delete Node
        query = f"""
        MATCH (n:{class_name} {{key: $key}})
        DETACH DELETE n
        """
        
        # 3. Execute Query and Check Result
        if tx:
            result = tx.run(query, {"key": key})
        else:
            with self.driver.session() as session:
                result = session.run(query, {"key": key})

        counters = result.consume().counters  # Get the counters
        if counters.nodes_deleted != 1:
            raise RuntimeError(f"Failed to delete object of type {class_name} with key {key}.")
        
        # 4. Delete from Register
        register = self.get_register(class_name)
        register.pop(key, None)  # Deletes the object if exists, otherwise does nothing
        
        return f"Object of type {class_name} with key {key} successfully deleted."
    
    def delete_multiple_objects(self, objects_to_delete: List[Tuple[str, str]]): # TODO: Test
        """
        Deletes multiple existing objects. Each object is identified by its class_name and key.
        Deletes both the object's representation in the program and in the database.

        Parameters:
            objects_to_delete (list): List of tuples. Each tuple consists of class_name (str) and key (str).

        Returns:
            List of success or error messages for each deleted object.
        """
        messages = []

        with self.driver.session() as session:
            tx = session.begin_transaction()
            try:
                for class_name, key in objects_to_delete:
                    message = self.delete_object(class_name, key, tx=tx)
                    messages.append(message)
                tx.commit()
            except:
                tx.rollback()
                raise

        return messages

    def clone_object(self, class_name: str, key: str, new_key: str):
        # Check if source object exists
        src_object = self.get_object(class_name, key)
        if not src_object:
            raise ValueError(f"No object of type {class_name} with key {key} found.")

        # Check for collision with new_key
        if self.get_object(class_name, new_key):
            raise ValueError(f"An object of type {class_name} with key {new_key} already exists.")

        # Extract the attributes and references from the source object
        class_info = self.model_specs.classes.get(class_name)
        attributes = [attr for attr, _ in class_info['attributes'].items() if attr != class_info['key']]
        references = [ref for ref, _ in class_info['references'].items()]

        args = {}
        for attr in attributes:
            value = getattr(src_object, attr)
            if value is not None:
                args[attr] = value
        for ref in references:
            value = getattr(src_object, ref)
            if value is not None:
                args[ref] = value

        # Update the key
        args['key'] = new_key

        # Create the new object using the existing functionality
        cloned_obj = self.create_object(class_name, args)

        return cloned_obj

# endregion

##########################
### REQUEST PROCESSING ###
##########################

    def _generate_response(self, message: str):
        return {"result": str(message), "objects": self.gather_objects()}

    def _interpret_input(self, input_str):
        # Recognize all @Class.Key mentions and replace accordingly
        pattern = r'@([\w]+)\.([\w]+)(?=\W|$)'  # This regex captures @Class.Key
        replacement = "self.get_object('\\1', '\\2')"  # Replacement pattern for the recognized mentions

        interpreted_input = re.sub(pattern, replacement, input_str)
        return interpreted_input

    def _generate_random_name(self, length=8):
        # Generate a random name for storing the result if no name is provided
        return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))

    def process_request(self, input_str: str):
        # Check if the input starts with a special command indicator ('>')
        if input_str.startswith('>'):
            result = self.process_command(input_str[1:].strip())  # Remove the '>' and pass the rest
        else:
            try:
                result = self.execute_expression(input_str)
            except Exception as e:
                result = f"Error occurred during execution of {input_str}:\r\n{str(e)}"
        return self._generate_response(str(result))

    def execute_expression(self, expression: str):
        exp = self._interpret_input(expression)
        # get execution scope
        self.execution_scope['self'] = self
        # If the expression contains '=', assume it's an assignment and use exec
        if '=' in exp:
            # Execute the assignment - TODO: make robust against malicious code execution
            exec(exp, self.execution_scope)
            # Parse the variable name and retrieve its value
            var_name = expression.split('=')[0].strip()
            result = self.execution_scope.get(var_name)
        else:
            # Otherwise, assume it's an expression and use eval
            result = eval(exp, self.execution_scope)
        return result

    def process_command(self, command_str):
        # Split the input to identify the command and its arguments
        parts = command_str.split(maxsplit=1)  # maxsplit ensures only the first space is considered
        command = parts[0]
        if not command in valid_commands:
            return f"Unknown command: {command}"
        arguments = parts[1] if len(parts) > 1 else ""

        # Determine which command to process
        if command == "add":
            return self.process_add(arguments)
        elif command == "create":
            return self.process_create(arguments)
        elif command == "get":
            return self.process_get(arguments)
        elif command == "io":
            return self.process_io(arguments)
        elif command == "help":
            return self.process_help(arguments)
        return f"Unknown command: {command}"

    def process_get(self, command_str: str) -> str:
        """
        Processes a 'get' command to retrieve model objects based on specified attributes.

        Parameters:
        - command_str (str): The command string, starting with the class name followed 
                            by a series of attribute=value pairs, optionally ending with 
                            'as <name>' to specify the name of the list or variable under 
                            which the result should be stored.

        Behavior:
        1. If the command contains only the class name and "-help", it returns a summary of 
        the available variables for that class.
        2. The command then processes the attribute=value pairs to build the filter criteria.
        3. If the keyword 'as' is encountered, the subsequent word is used as the name under 
        which the result will be stored. If not provided, a random name is generated.
        4. The command attempts to fetch model objects based on the filter criteria.
        5. If only one object is fetched, it is stored directly under the specified or 
        generated name. If multiple objects are fetched, they are stored as a list.

        Returns:
        - A string message indicating the outcome of the command, which could be an error 
        message, a summary of available variables, or a success message detailing the 
        number of objects retrieved and their storage name.

        Example usage:
        > get ClassName attribute1=value1 attribute2=value2 as result_name
        > get ClassName -help
        """
        # Split the arguments
        args = command_str.split()

        # Validate if the class name is provided
        if not args:
            return "Please specify the class name and the attributes to get an object."

        class_name = args[0]

        if len(args) > 1 and args[1] == "-help":
            return "\n".join(self.model_specs.get_variable_summary(class_name))

        # Process the attribute/reference specifications
        filter_args = {}
        list_name = None
        for arg in args[1:]:
            if arg == "as":
                # The next argument should be the name of the list
                try:
                    list_name = args[args.index(arg) + 1]
                except IndexError:
                    return "Expected a name after 'as'."
                break
            elif "=" in arg:
                key, value = arg.split("=", 1)
                filter_args[key] = self.execute_expression(value)
            else:
                return f"Invalid argument format: {arg}"

        # If no name is provided, generate a random one
        if not list_name:
            list_name = self._generate_random_name()

        # Fetch the objects using the filter arguments
        objects = self.find_objects(class_name, filter_args)

        if not objects:
            return f"No objects of type {class_name} matching the criteria found."

        # If only one object, store it directly. Otherwise, store as a list.
        if len(objects) == 1:
            self.execution_scope[list_name] = objects[0]
            return f"Object of type {class_name} added as {list_name}."
        else:
            self.execution_scope[list_name] = objects
            return f"{len(objects)} objects of type {class_name} added to {list_name}."

    def process_create(self, command_str: str) -> str:
        """
        Processes a 'create' command to instantiate a new model object based on provided attributes.

        Parameters:
        - command_str (str): The command string, starting with the class name followed 
                            by a series of attribute=value pairs.

        Behavior:
        1. Extracts the class name and validates its existence.
        2. Processes the attribute=value pairs to construct the model object.
        3. Calls the appropriate function (`self.create_object`) to instantiate the object.

        Returns:
        - A string message indicating the outcome of the command, which could be an error message, 
        a help message, or a success message with a representation of the created object.
        """
        
        # Split the arguments
        args = command_str.split()

        # Validate if the class name is provided and is known
        if not args:
            return "No arguments provided."
        
        class_name = args[0]
        if class_name not in self.model_specs.get_class_names():
            return "Unknown Object Type."

        # If only the class name is provided or if help is requested
        if len(args) == 1 or args[1] == "-help":
            return "\n".join(self.model_specs.get_variable_summary(class_name))

        # Process the attribute/reference specifications
        init_params = {}
        for arg in args[1:]:
            key, value_str = arg.split("=", 1)
            try:
                value = self.execute_expression(value_str)
                init_params[key] = value
            except Exception as e:
                return f"Error occurred during evaluation of {value_str}: {str(e)}"

        # Create the object
        try:
            obj = self.create_object(class_name, init_params)
            return str(obj)
        except Exception as e:
            return f"Error occurred during object creation: {str(e)}"

    def process_add(self, expression: str) -> str:
        """
        Processes an 'add' command to add an object or list of objects to the model.

        Parameters:
        - expression (str): A Python expression that evaluates to an object or a list of objects.

        Behavior:
        1. Evaluates the provided expression.
        2. Checks if the resulting object (or objects) are of a known model object type.
        3. Calls the appropriate function (`self.add_object` or `self.add_multiple_objects`) to add the object(s) to the model.

        Returns:
        - A string message indicating the outcome of the command, which could be an error message or a success message.
        """
        
        try:
            # Evaluate the expression
            result = self.execute_expression(expression)

            valid_classes = self.model_specs.get_class_names()
            # Check if the result is a list of known model objects
            if isinstance(result, list) and all(type(item).__name__ in valid_classes for item in result):
                if self.add_multiple_objects(result):
                    return "All objects added successfully."
                else:
                    return "Failed to add list of objects."
            
            # Check if the result is a singular known model object
            elif type(result).__name__ in valid_classes:
                try:
                    self.add_object(result)
                    return f"Object {result} added successfully."
                except Exception as e:
                    return f"Failed to add object: {result}"

            # If result is neither a list of known model objects nor a singular known model object
            else:
                return f"Expression does not evaluate to a recognized model object or list of model objects."

        except Exception as e:
            return f"Error occurred during evaluation: {str(e)}"
        
    def process_io(self, command: str) -> str:
        """
        Process IO commands related to the payload bay.

        Args:
            command (str): The input command string.

        Returns:
            str: The result or response to the command.
        """

        # Split the command into parts
        parts = command.split()

        # Check for valid commands
        if not parts:
            return "Invalid IO command."

        action = parts[0]

        # Handle 'list' action
        if action == "list":
            return self._list_payload_bay()

        # Handle 'read' action
        elif action == "read":
            filename = parts[1]
            var_name = parts[-1] if parts[-2] == "as" else None
            if len(parts) % 2 == 0:
                return self._read_file_to_variable(filename, var_name)
            else:
                class_method_str = parts[2]
                return self._read_and_process_file(filename, class_method_str, var_name)

        # Handle 'write' action (if you decide to implement it later)
        # elif action == "write":
        #     # Implementation here

        else:
            return "Unknown IO action."

    def process_help(self, command_str: str) -> str:
        if not command_str:
            return command_help

        param = command_str.lower()
        
        if param == "get":
            return """
Usage for 'get' command:
> get [class_name] [attribute/reference=value] ... [attribute/reference=value] optional: as [name of return list]
- Loads a model object or list of model objects of type class_name based on attribute/reference=value specifications. 
- Results can optionally be stored under a specific name.
            """
        
        elif param == "create":
            return """
Usage for 'create' command:
> create [class_name] -help
- Displays required and optional parameters for class_name.
> create [class_name] [attribute1=value1] ... [attributeN=valueN]
- Creates a new model object with the specified parameters in both program context and persistent storage.
            """
        
        elif param == "add":
            return """
Usage for 'add' command:
> add [expression that evaluates to a model object or list of model objects]
- Adds a model object or list of model objects created in program context to persistent storage.
            """

        else:
            return f"Unknown help topic: {param}\r\n" + command_help


    def gather_objects(self):
        response = {
            "model_objects": {},
            "runtime_objects": {
                "lists": [],
                "dicts": [],
                "variables": []
            }
        }
        
        # Handle the general_register (model objects)
        general_register = getattr(self.loaded_module, "register", {})
        for object_type, register in general_register.items():
            response["model_objects"][object_type] = [
                {"name": key, "content": str(value)}
                for key, value in register.items()
            ]
        
        # Handle other runtime objects
        for attr_name, value in self.execution_scope.items():
            if attr_name.startswith("_"):  # Exclude private members
                continue
            if attr_name == "self": # Exclude ModelInterpreter self
                continue
            if type(value).__name__ in ["type", "ABCMeta", "module", "function"]: # Exclude classes, modules and functions
                continue
            if str(value).startswith("typing."): # Exclude typing module members
                continue
            obj_repr = {"name": attr_name}
            if isinstance(value, list):
                obj_repr["content"] = [{"type": type(item).__name__, "value": str(item)} for i, item in enumerate(value)]
                response["runtime_objects"]["lists"].append(obj_repr)
            elif isinstance(value, dict):
                if attr_name in known_dicts:
                    continue
                obj_repr["content"] = [{"key": str(k), "type": type(v).__name__, "value": str(v)} for k, v in value.items()]
                response["runtime_objects"]["dicts"].append(obj_repr)
            else:
                obj_repr["type"] = type(value).__name__
                obj_repr["content"] = str(value)
                response["runtime_objects"]["variables"].append(obj_repr)
        
        return response

    def _list_payload_bay(self) -> str:
        """
        List the files in the payload bay.

        Returns:
            str: List of files in the payload bay.
        """
        files = os.listdir("payload_bay")
        if not files:
            return "Payload bay is empty."
        return "\n".join(files)

    def _read_file_to_variable(self, filename: str, var_name: str = None) -> str:
        """
        Read the file content and store it in a variable.

        Args:
            filename (str): Name of the file.
            var_name (str, optional): Name of the variable to store the content. Defaults to filename.

        Returns:
            str: Confirmation message.
        """
        with open(os.path.join("payload_bay", filename), 'r') as file:
            content = file.read()
        
        var_name = var_name or filename
        # Store the content in a variable
        self.execution_scope[var_name] = content
        
        return f"Content of {filename} has been stored in variable: {var_name}"
    
    def _read_and_process_file(self, filename: str, function_str: str, var_name: str = None) -> str:
        """
        Read the file content and process it using the specified class method.

        Args:
            filename (str): Name of the file.
            function_str (str): String representation of the function or class method to process the content.
            var_name (str, optional): Name of the variable to store the content. Defaults to filename.

        Returns:
            str: Result after processing the content.
        """
        # Check if function_str contains '.' indicating it's a class method
        if '.' in function_str:
            class_name, method_name = function_str.split('.')
            
            # Get the class and method from the loaded module
            target_class = getattr(self.loaded_module, class_name, None)
            if not target_class:
                return f"Error: {class_name} not found."
            
            target_function = getattr(target_class, method_name, None)
            if not target_function:
                return f"Error: {function_str} not found."
        else:
            # It's a function directly in the loaded module
            target_function = getattr(self.loaded_module, function_str, None)
            
            if not target_function:
                return f"Error: {function_str} not found."

        with open(os.path.join("payload_bay", filename), 'r') as file:
            content = file.read()

        # Process the content using the target function
        result = target_function(content)

        # calculate var name
        var_name = var_name if var_name else filename
        # Store the result in a runtime variable
        self.execution_scope[var_name] = result

        return f"Processed content of {filename} using {function_str} and stored the result in variable: {var_name}"
