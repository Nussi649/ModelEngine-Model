from typing import Union, List, Dict, Optional
from datetime import datetime
import importlib

class ModelEntity:
    """ 
    Base class for all model entities. 
    """
    def __init__(self):
        pass


class ModelObject(ModelEntity):
    """
    Superclass for all ModelObject types. 
    Represents entities that have a unique identifier and can be loaded in full or reduced modes.
    """
    def __init__(self, key: str, mini_mode: bool = False):
        super().__init__()
        self._key = key
        self._mini_mode = mini_mode
    
    @classmethod
    def create_reduced(cls, key):
        instance = cls(key=key, mini_mode=True)
        return instance

    def upgrade(self):
        # abort if object is already in full mode
        if not self._mini_mode:
            return False
        self._mini_mode = False
        return True

    @property
    def key(self):
        return self._key

    @property
    def mini_mode(self):
        return self._mini_mode

    def __str__(self):
        return f'[{self.__class__.__name__}] {self.key}'


class Composite(ModelEntity):
    """
    Superclass for all Composite types.
    Represents entities that do not have a unique key and are often used as data points.
    """
    def __init__(self):
        super().__init__()


class Collection:

    def __init__(self, parent_type, parent_key, collection_name, composite_type):
        self.parent_type = parent_type
        self.parent_key = parent_key
        self.name = collection_name
        self.composite_type = composite_type
        self.load_callbacks()

    def load_callbacks(self):
        """
        Dynamically import the ModelDB class and retrieve the required functions.
        Cache these functions for future calls.
        """
        ModelDB = importlib.import_module('src.model_db').ModelDB
        model_db_instance = ModelDB.get_instance()  # Assuming a static method 'get_instance' that returns the singleton object
        self._query_callback = model_db_instance.get_composites
        self._add_callback = model_db_instance.add_composites

    def query(self, return_as_tuple=False, **filter_params):
        results = self._query_callback(self.parent_type.__name__,
                                       self.parent_key,
                                       self.name,
                                       self.composite_type.__name__,
                                        **filter_params)
        if return_as_tuple:
            return results  # Assuming the _query_callback directly returns a list of tuples
        else:
            return [self.composite_type(*result) for result in results]

    def add(self, composites: List):
        # Convert Composite objects to suitable data format for insertion, If already in dict format, pass on
        data = [composite.__dict__ if isinstance(composite, Composite) else composite for composite in composites]
        # Call the add function in ModelDB
        self._add_callback(self.parent_type.__name__, 
                           self.parent_key, 
                           self.name, 
                           self.composite_type.__name__, 
                           data)
