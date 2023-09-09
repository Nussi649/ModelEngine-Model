import importlib.util
import re
import sys
import inspect
import json
from abc import ABC, ABCMeta
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

valid_commands = ["get", "create", "add", "assign", "eval", "help"]

known_dicts = ["INVERSE_RELATIONSHIPS", "register"]

command_help = """
_______ Available Commands _______
help [command] - further information about usage of each command
get [class_name] [key]/[list of keys]/[attribute specification] optional: [name of return list] - loads a model object or list of model objects of type class_name that is either specified by its key(s) or an attribute/reference=value combination
create [class_name] -help - provides information about the required and optional parameters
create [class_name] [attribute/reference=value] ... [attribute/reference=value] - creates a new model object with the specified parameters both in program context as well as in persistent storage
add [expression that evaluates to a model object]/[list of model objects] - adds a model object or list of model objects that is/are created in program context to persistent storage
assign [name] [expression] - assigns an evaluated expression to a variable of arbitrary data type
eval [expression] - evaluates any expression
    """
    
def custom_split(input: str) -> List[Union[str, List]]:
    # Matches lists like [item1, item2, ...] and individual words
    pattern = r'\[([^\]]+)\]|([^ ]+)'
    matches = re.findall(pattern, input)
    args = []
    for match in matches:
        # Check if it's a list or a single word
        if match[0]:  # If it's a list
            arg = [val.strip() for val in match[0].split(',')]
            args.append(arg)
        else:
            arg = match[1].strip()
            args.append(arg)
    return args

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
        self.model_specs = ModelSpecifications(xml_path="/workspace/data_models/ResourceTransmission_v1.xml",
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
    
    def load_node(self, class_name: str, key: str, tx, include_related=True, reduced_object=None):
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
        if include_related:
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

            obj = self.object_from_node(class_name, records[0]['main_node'], records if include_related else None, reduced_object)
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
        node_attrs = ", ".join(f"{k}: {json.dumps(v)}" for k, v in attrs.items())
        query = [f"CREATE (a:{class_name} {{ {node_attrs} }})"]
        expected_rel_created = 0

        if refs:
            query.append("WITH a")
            for rel_name, rel_data in refs.items():
                # Check if the ref data is an object or a dictionary
                if isinstance(rel_data, dict):
                    related_class_name = rel_data['class_name']
                    related_key = rel_data['key']
                else:  # It's an object
                    related_class_name = type(rel_data).__name__
                    related_key = rel_data.key

                relationship_type = rel_name.upper()
                inv_rel_type = self.loaded_module.INVERSE_RELATIONSHIPS.get(rel_name, "").upper()
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
        register = self.get_register(class_name)

        # Check if object is available in loaded context aka object register
        obj = register.get(key, None)

        # If an object was found and it's in full mode or only reduced mode is required
        if obj and (not obj.mini_mode or reduced):
            return obj
        # Fetch the object data from the database because we have nothing loaded and need to know, if the object even exists
        with self.driver.session() as session:
            tx = session.begin_transaction()
            obj = self.load_node(class_name, key, tx, not reduced)
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
        valid_attributes = self.model_specs.get_attributes(class_name)
        valid_references = self.model_specs.get_references(class_name)
        property_filters = []
        relationship_filters = []

        for key, value in args.items():
            if key in valid_attributes:
                property_filters.append(f"n.{key} = ${key}")
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
                    obj = self.load_node(class_name, key, tx, include_related=True, reduced_object=obj)
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
            class_name = type(obj_instance).__name__
            
            # Validate if the instance is of a recognized model object type
            if class_name not in self.model_specs.get_class_names():
                return False
            
            key_name = self.model_specs.get_key_attribute(class_name)
            key_value = obj_instance.key
        
            # Check for existing object in the database by key
            existing_object = self.get_object(class_name, key_value)
            if existing_object:
                if self._objects_match(obj_instance, existing_object):
                    return True
        
            # Convert the object instance to a dictionary format suitable for database insertion
            args = {attr: getattr(obj_instance, attr) for attr in self.model_specs.get_attributes(class_name) if hasattr(obj_instance, attr)}
            args.update({ref: getattr(obj_instance, ref) for ref in self.model_specs.get_references(class_name) if hasattr(obj_instance, ref)})
            
            # Handle references and ensure they exist in the database
            for ref, value in args.items():
                ref_class_name = type(value).__name__
                if ref_class_name in self.model_specs.get_class_names():
                    ref_obj = self.get_object(ref_class_name, value.key)
                    if not ref_obj:
                        # Check for inverse relationships
                        inverse_rel = self.loaded_module.INVERSE_RELATIONSHIPS.get(ref, "")
                        if inverse_rel:
                            # Alert the caller
                            print(f"Inverse relationship found for {ref}. Ensure both nodes exist before adding a relationship.")
                            return False
                        # If the referenced object doesn't exist, add it recursively
                        added = self.add_object(value, transaction)
                        if not added:
                            return False  # Fail if we can't add the reference
            
            # Construct the creation query
            attrs, refs = self.model_specs.separate_attrs_refs(class_name, args)
            query_create, expected_rel_created = self._construct_create_query(class_name, attrs, refs)
        
            # Execute the query
            counters = transaction.run(query_create).consume().counters
            if (counters.nodes_created != 1) or (counters.relationships_created != expected_rel_created):
                raise ValueError(f"Error creating node or relationships in Neo4j. Expected 1 node and {expected_rel_created} relationships but got {counters.nodes_created} nodes and {counters.relationships_created} relationships.")
                
            return True

        if tx:
            result = core_logic(tx)
            if not result:
                # Rollback the transaction if the function didn't succeed
                tx.rollback()
            return result
        else:
            with self.driver.session() as session:
                result = session.write_transaction(core_logic)
                return result

    def add_multiple_objects(self, obj_instances: List, tx=None) -> bool:
        if tx:
            for obj in obj_instances:
                if not self.add_object(obj, tx):
                    return False
        else:
            with self.driver.session() as session:
                for obj in obj_instances:
                    if not session.write_transaction(self.add_object, obj):
                        return False
        return True

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

    def process_request(self, input: str):
        # Split input by space characters into a list of words
        words = custom_split(input)

        # If the input is empty, return an appropriate response
        if not words:
            return {"result": "No command provided", "objects": self.gather_objects()}

        # Validate the first word
        command = words[0].lower()  # Convert command to lowercase to ensure case-insensitivity
        if command not in valid_commands:
            return {"result": "Unknown command", "objects": self.gather_objects()}

        # Arguments for the command
        args = words[1:]

        try:
            # Depending on the command, call the corresponding function
            if command == "get":
                result = self.process_get(args)
            elif command == "create":
                result = self.process_create(args)
            elif command == "add":
                result = self.process_add(args)
            elif command == "assign":
                result = self.process_assign(args)
            elif command == "eval":
                result = self.process_eval(args)
            elif command == "help":
                result = self.process_help(args)
            else:
                result = "Invalid command"  # This should never happen due to the previous check, but it's good to have a fallback

        except Exception as e:
            result = f"Error: {e}"

        return {"result": str(result), "objects": self.gather_objects()}
    
    def process_get(self, args: List[Union[str, List[str]]]) -> str:
        # Initial validation of parameters
        if not args or len(args) < 2:
            return "Please specify the class name and key or attributes to get an object."
        
        class_name = self.resolve_single_exp(args[0])
        
        # Check for the second argument's type
        second_arg = args[1]

        if isinstance(second_arg, str):
            # It's a single object retrieval
            if '=' not in second_arg:  # It's a key
                if len(args) != 2:
                    return "Invalid arguments for the get command."
                
                key = self.resolve_single_exp(second_arg)
                obj = self.get_object(class_name, key)
                if obj:
                    return str(obj)
                else:
                    return f"No object of type {class_name} with key {key} found."
            
            else:  # It's an attribute/reference specification
                if len(args) > 3:
                    return "Invalid arguments for the get command."
                
                # Split attribute/reference name and value to look for
                split_args = second_arg.split('=')
                filter_args = {split_args[0]: self.resolve_single_exp(split_args[1])}
                objects = self.find_objects(class_name, filter_args)
                if not objects:
                    return f"No objects of type {class_name} matching the criteria found."
                
                if len(args) == 3:  # If there's a list name provided
                    list_name = self.resolve_single_exp(args[2])
                    setattr(self.loaded_module, list_name, objects)
                    return f"{len(objects)} objects of type {class_name} added to {list_name}."
                else:
                    return "\n".join([str(obj) for obj in objects])
        elif isinstance(second_arg, List):
            # It's a list of keys
            if len(args) != 3:
                return "Invalid arguments for the get command. Requires exactly three arguments if second argument is a list of keys."
            
            keys = [self.resolve_single_exp(key) for key in second_arg]
            objects = self.get_multiple_objects([(class_name, key) for key in keys])
            if not objects:
                return f"No objects of type {class_name} found for the given keys."

            list_name = self.resolve_single_exp(args[2])
            setattr(self.loaded_module, list_name, objects)
            return f"{len(objects)} objects of type {class_name} added to {list_name}."

        return "Invalid arguments for the get command."


    def process_create(self, args: List[Union[str, List[str]]]) -> str:
        if not args:
            return "No arguments provided."
        class_name = args[0]
        if class_name not in self.model_specs.get_class_names():
            return "Unknown Object Type."
        if len(args) < 2:
            return "Command requires at least 2 arguments. Call 'help create' for further information."
        if args[1] == "-help":
            return "\n".join(self.model_specs.get_variable_summary(class_name))
        init_params = {}
        for arg in args[1:]:
            parts = arg.split('=')
            init_params[parts[0]] = self.resolve_single_exp(parts[1])
        obj = self.create_object(class_name, init_params)
        return str(obj)

    def process_add(self, args: List[Union[str, List[str]]]) -> str:
        if not args:
            return "No arguments provided."

        # Resolve the provided expression to an object or list of objects
        resolved_obj = self.resolve_single_exp(args[0])
        
        if isinstance(resolved_obj, list):
            if self.add_multiple_objects(resolved_obj):
                return "All objects added successfully."
            return f"Failed to add list of objects."
        else:
            if self.add_object(resolved_obj):
                return f"Object {resolved_obj} added successfully."
            else:
                return f"Failed to add object: {resolved_obj}"

    def process_assign(self, args: List[Union[str, List[str]]]) -> str:
        if len(args) < 2:
            return "Command requires at least 2 arguments. Call 'help assign' for further information."

        var_name = args[0]
        expression = " ".join(args[1:])  # In case the expression was split into multiple args

        # Evaluate the expression
        try:
            # get execution scope
            self.execution_scope['self'] = self
            value = eval(expression, self.execution_scope)
        except Exception as e:
            return f"Error evaluating expression: {e}"

        # Assign the value to the variable in the loaded_module context
        setattr(self.loaded_module, var_name, value)
        return f"Assigned {value} to {var_name}."

    def process_eval(self, args: List[Union[str, List[str]]]) -> str:
        expression = " ".join(args)  # In case the expression was split into multiple args

        # Evaluate the expression
        try:
            # get execution scope
            self.execution_scope['self'] = self
            value = eval(expression, self.execution_scope)
        except Exception as e:
            return f"Error evaluating expression: {e}"
        
        return str(value)

    def process_help(self, args: List[Union[str, List[str]]]) -> str:
        valid_arguments = valid_commands[:-1]
        if not args:
            return command_help
        
        param = args[0].lower()
        if param not in valid_arguments:
            return "Unknown argument"

        if param == "get":
            return """
Usage for 'get' command:
1. Get by key: get [class_name] [key]
2. Get by property: get [class_name] [property=specific_value]
3. Get multiple by keys: get [class_name] [comma-separated-keys] [name of list]
4. Get multiple by property: get [class_name] [property=specific_value] [name of list]

property refers to both attributes and relationships. can be specified directly as string or indirectly through variables, which get recognized by a leading $ (e.g., $variable, $type.key).
            """

        elif param == "create":
            return """
Usage for 'create' command:
create [class_name] -help - Displays required and optional parameters for class_name.
create [class_name] [attribute1=value1] ... [attributeN=valueN] - Create an object of type class_name with specified attributes.
            """

        elif param == "add":
            return """
Usage for 'add' command:
1. Add a single object: add [expression that evaluates to a model object]
2. Add multiple objects: add [comma-separated list of model objects]
            """

        elif param == "assign":
            return """
Usage for 'assign' command:
assign [variable_name] [expression] - Assigns the result of the expression to the specified variable.
            """

        elif param == "eval":
            return """
Usage for 'eval' command:
eval [expression] - Evaluates the provided expression and returns the result.
            """
        return "this should not be reachable"

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
        for attr_name in dir(self.loaded_module):
            if attr_name.startswith("_"):  # Exclude private members
                continue
            value = getattr(self.loaded_module, attr_name)
            if isinstance(value, type) or isinstance(value, ABCMeta) or isinstance(value, _SpecialForm):
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

    def resolve_single_exp(self, expr: str):
        if " " in expr:
            raise ValueError("The expression should be a single word.")
        
        if expr.startswith("$"):
            if '.' in expr:
                type_name, key = expr[1:].split('.')
                # Fetch from the respective register
                register = self.get_register(type_name)
                return register.get(key)
            else:
                # Fetch from module context
                return getattr(self.loaded_module, expr[1:])
        # Check for potential number values
        try:
            return int(expr)
        except ValueError:
            pass

        try:
            return float(expr)
        except ValueError:
            pass
        
        # If it's not recognized as a variable, object, integer, or float, return as string
        return expr
    