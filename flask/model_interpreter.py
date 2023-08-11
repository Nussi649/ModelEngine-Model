import importlib.util
import io
import sys
import inspect
from abc import ABC
from neo4j import GraphDatabase
from types import ModuleType
from pathlib import Path
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
        self.cache_class_types()

    def resolve_class_name(self, class_name: str):
        if self.loaded_module is None:
            raise ModuleUnavailableError("No model code loaded.")
        target_class = getattr(self.loaded_module, class_name)
        if target_class is None:
            raise ValueError(f"Error while trying to resolve Class {class_name}: Class not found.")
        return target_class
    
    def cache_class_types(self):
        self.class_types = {}
        # Iterate over the attributes of the module
        for name, obj in inspect.getmembers(self.loaded_module):
            # Check if the attribute is a class
            if inspect.isclass(obj):
                # Check if class is abstract
                if not (issubclass(type(obj), ABC) or hasattr(obj, '__abstractmethods__')):
                    # Get the resolved type hints for the class
                    type_hints = get_type_hints(obj)
                    # Dictionary to hold the attribute types for this class
                    attribute_types = {}

                    # Iterate over the type hints
                    for attr_name, attr_type in type_hints.items():
                        # Check if the attribute type is a generic type (e.g., List[Class])
                        if hasattr(attr_type, '__origin__'):
                            attr_type = get_args(attr_type)[0]

                        # Store the attribute type in the dictionary
                        attribute_types[attr_name] = attr_type

                    # Store the attribute types for this class in the main dictionary
                    self.class_types[name] = attribute_types

# endregion                    

# region CRUD related

    def create_object(self, class_name: str, args:dict):
        """
        FUNCTION: create_object
        creates a new object of type class_name. checks if object with same key already exists: if so, then returns the object, else creates a new one according to parameters
        PARAMS:
        class_name (str): name of the object class
        args (dict): dictionary of constructor parameters
        RETURNS:
        object of type class_name. either a preexisting object with the same key or the newly created object
        """
        # resolve target class, key_name and register
        target_class = self.resolve_class_name(class_name)
        key_name = getattr(target_class, 'key_name')
        register = getattr(self.loaded_module, f"objects_{class_name}")
        # try finding object
        existing_object = self.get_object(class_name, args[key_name])
        if existing_object is not None:
            return existing_object

        # object does not yet exist, create a new one
        object_instance = target_class(**args)

        # run query on database to store object as node
        query_create = create_object_query.format(class_name=class_name)
        # separate attributes from references. distinguishing property is whether the member has a "key" attribute (which only Class objects have)
        attrs = {k: v for k, v in args.items() if not hasattr(v, 'key')}
        user_refs = {k: v for k, v in args.items() if hasattr(v, 'key')}
        refs = {}
        for ref_name, ref_object in user_refs.items():
            inv_rel = self.loaded_module.INV_REL_MAP.get(ref_name)
            refs[ref_name] = {'object': ref_object, 'inv_type': inv_rel}
        with self.driver.session() as session:
            creation_result = session.run(query_create, attributes=attrs)
            creation_summary = creation_result.consume()
            if creation_summary.counters.nodes_created != 1:
                raise RuntimeError(f"Failed to create a node for class {class_name} with properties {args}")
            # add relationships for references
            if refs.keys:
                # start creating query
                query_relate = f"MATCH (a:{class_name} {{{key_name}: '{args[key_name]}'}})"
                # continue by matching all involved nodes - assumed to be existent because otherwise there could be no program object representation of them
                for ref_name, ref_data in refs.items():
                    ref_class_name = type(ref_data['object']).__name__
                    ref_key_name = ref_data['object'].key_name
                    ref_key_value = ref_data['object'].key
                    query_relate += f"\nMATCH (b_{ref_name}:{ref_class_name} {{{ref_key_name}: '{ref_key_value}'}})"

                rel_count = 0
                # continue by creating relationships
                for ref_name, ref_data in refs.items():
                    relationship_type = ref_name.upper() # capitalize the variable name to match naming convention
                    inv_rel_type = ref_data['inv_type'].upper() if ref_data['inv_type'] is not None else "" # capitalize again
                    query_relate += f"\nCREATE (a)-[:{relationship_type}]->(b_{ref_name})"
                    rel_count += 1
                    if inv_rel_type:
                        query_relate += f"\nCREATE (b_{ref_name})-[:{inv_rel_type}]->(a)"
                        rel_count += 1
                relate_result = session.run(query_relate)
                relate_summary = relate_result.consume()
                rel_count_created = relate_summary.counters.relationships_created
                if rel_count_created != rel_count:
                    raise RuntimeError(f"Failed to create all intended relationships for new node {args[key_name]} of type {class_name}: {rel_count_created}/{rel_count}")

        # store object in register
        register[object_instance.key] = object_instance

        return object_instance

    def get_object(self, class_name: str, key: str):
        """
        FUNCTION: get_object
        finds object of type class_name with the specified key if it exists. looks first in already loaded objects, then queries the database. if neither yields a result, the object does not exist
        PARAMS:
        class_name (str): name of the object class
        key (str): value of key attribute of object to be identified by
        RETURNS:
        object of type class_name if it exists, None otherwise
        """
        target_class = self.resolve_class_name(class_name)

        # check if object is available in loaded context aka object register
        register = getattr(self.loaded_module, f"objects_{class_name}")
        if key in register:
            return register[key]
        # get key attribute name
        key_name = getattr(target_class, 'key_name')
        # check if object exists in database
        query = get_object_query.format(class_name=class_name, key_name=key_name, key_value=key)

        with self.driver.session() as session:
            result = session.run(query)
            record = result.single()
            if record:
                # Node found in the database
                # Extract the attributes from the node
                attributes = {name: value for name, value in record['n'].items()}
                # Extract relationships by attribute name (using relationship_attributes)
                relationships = record['relationships']
                related_nodes = record['related_nodes']
                # Create an instance of the target class using the extracted attributes
                object_instance = target_class(**attributes, **relationships)

                # Store the object in the register and return it
                register[key] = object_instance
                return object_instance
            else:
                return None


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
    