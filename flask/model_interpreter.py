import importlib.util
import io
import sys
import inspect
import json
from abc import ABC
from neo4j import GraphDatabase
from types import ModuleType
from pathlib import Path
from collections import defaultdict
from dm_specs import ModelSpecifications
from typing import List, Tuple, Any, Iterable, get_args, get_type_hints

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
    
    def object_from_node(self, node, records=None, reduced_object=None):
        """
        Constructs a full Python object from a Neo4j node.

        Parameters:
            node: The Neo4j node.
            records (list): Optional list of related records.
            reduced_object (ModelEntity): Optional reduced object that can be upgraded to full object representation

        Returns:
            The corresponding Python object.
        """
        if reduced_object:
            obj_class = type(reduced_object)
            class_name = obj_class.__name__
        else:
            all_classes = set(self.model_specs.get_class_names())
            class_name = next((label for label in node.labels if label in all_classes), None)
            if not class_name:
                raise ValueError("No valid class name found in node labels.")
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

            obj = self.object_from_node(records[0]['n'], records if include_related else None, reduced_object)
            return obj

        except Exception as e:
            # TODO: Handle the error robustly
            raise e
        
    
    def _fetch_references_from_records(self, class_name, records):
        references = {}
        register_cache = {}  # Cache for object registers

        for record in records:
            relationship = record.get('relationship_type')
            rel_node = record.get('related_node_properties')
            if not relationship or not rel_node:
                continue
            
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
            for class_name, keys in grouped_pairs.items():
                for key in keys:
                    # First, try to get the object without hitting the database
                    obj = self.get_object(class_name, key, reduced=True)
                    if not obj or (obj.mini_mode and not reduced):
                        tx = session.begin_transaction()
                        obj = self.load_node(class_name, key, tx, reduced_object=obj, include_related=not reduced)
                        tx.commit()
                    objects.append(obj)

        return objects
    
    def find_object(self, class_name, args, reduced=False): # TODO: Test
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
            results = tx.run(query, args)
            
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
            result = e

        # Reset the standard output
        sys.stdout = sys.__stdout__

        # Get the captured output as a string
        output = captured_output.getvalue()

        return {"output": output, "result": str(result)}
    