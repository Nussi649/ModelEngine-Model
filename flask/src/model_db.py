import json
from src.runtime_manager import RuntimeManager, ModuleUnavailableError
from src.dm_specs import ModelSpecifications
from neo4j import GraphDatabase
from collections import defaultdict
from typing import List, Tuple, Any
from datetime import datetime


create_object_query = "CREATE (n:{class_name}) SET n = $attributes"
get_object_query = """
    MATCH (n:{class_name}) WHERE n.{key_name} = '{key_value}'
    OPTIONAL MATCH (n)-[r]->(related)
    RETURN n, collect(r) as relationships, collect(related) as related_nodes
    """


class ModelDB:
    def __init__(self, model_specs: ModelSpecifications, runtime_manager: RuntimeManager, URI: str, AUTH: tuple):
        self._URI = URI
        self._AUTH = AUTH
        self.model_specs = model_specs
        self.runtime = runtime_manager
        self.runtime.set_to_scope("__get_model_object__", self.get_object)
        self.driver = GraphDatabase.driver(URI, auth=AUTH)

    @property
    def URI(self):
        return self._URI
    
    @property
    def AUTH(self):
        return self._AUTH

    def close(self):
        """
        Close the Neo4j database connection.
        """
        self.driver.close()

# region Helper functions

    def get_type_register(self, class_name: str):
        """
        Get the type-specific register for a given class name.
        """
        return self.runtime.get_type_register(class_name)

    def resolve_class_name(self, class_name):
        if not self.runtime.get_status():
            raise ModuleUnavailableError("No model code loaded.")
        if class_name not in self.model_specs.classes:
            raise ValueError(f"Class {class_name} not recognized.")
        return self.runtime.get_attr(class_name)

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
                register_cache[rel_class_name] = self.get_type_register(rel_class_name)
            
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
                inv_rel_type = self.runtime.get_from_scope("INVERSE_RELATIONSHIPS").get(rel_name, "").upper()

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
            inv_rel_type = self.runtime.get_from_scope("INVERSE_RELATIONSHIPS").get(rel_name, "").upper()

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

        register = self.get_type_register(class_name)
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
        register = self.get_type_register(class_name)

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
                register = self.get_type_register(class_name)
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
                register = self.get_type_register(class_name)
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
        register = self.get_type_register(class_name)

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
            self.get_type_register(class_name)[obj_instance.key] = obj_instance
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
                register = self.runtime.get_register()
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
        register = self.get_type_register(class_name)
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