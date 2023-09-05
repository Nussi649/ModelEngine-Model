from typing import List
from abc import ABC
from datetime import datetime

INV_REL_MAP = {
    'direct_constituents': 'parents',
    'conduits_in': 'target',
    'conduits_out': 'origin',
    'origin': 'conduits_out',
    'target': 'conduits_in'
}

class Unit:

    key_name = 'name'


    def __init__(self, name: str, *,
                   mini_mode=False):
        self._mini_mode = mini_mode
        self._name = name

    @classmethod
    def create_reduced(cls, name: str):
        instance = cls(name=name, mini_mode=True)
        return instance

    def upgrade(self):
        # abort if object is already in full mode
        if not self._mini_mode:
            return False
        self._mini_mode = False
        return True

    @property
    def mini_mode(self):
        return self._mini_mode

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def name(self):
        return self._name

    def __str__(self):
        return f'(Unit) {self.key}'


class Value:

    key_name = 'identifier'
    value: float
    unit: 'Unit'
    used_in: 'ModelObject'


    def __init__(self, identifier: str,
                 value: float = None,
                 unit: 'Unit' = None,
                 used_in: 'ModelObject' = None, *,
                   mini_mode=False):
        self._mini_mode = mini_mode
        self._identifier = identifier
        if not mini_mode:
            if value is None:
                raise ValueError('value is required')
            if unit is None:
                raise ValueError('unit is required')
            self.value = value
            self.unit = unit
            self.used_in = used_in

    @classmethod
    def create_reduced(cls, identifier: str):
        instance = cls(identifier=identifier, mini_mode=True)
        return instance

    def upgrade(self, value: float,
                unit: 'Unit',
                used_in: 'ModelObject' = None):
        # abort if object is already in full mode
        if not self._mini_mode:
            return False
        if value is None:
            raise ValueError('value is required')
        if unit is None:
            raise ValueError('unit is required')
        self._mini_mode = False
        if value:
              self.value = value
        if unit:
              self.unit = unit
        if used_in:
              self.used_in = used_in
        return True

    @property
    def mini_mode(self):
        return self._mini_mode

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def identifier(self):
        return self._identifier

    def __str__(self):
        return f'(Value) {self.key}'


class Resource:

    key_name = 'name'
    unit_default: 'Unit'


    def __init__(self, name: str,
                 unit_default: 'Unit' = None, *,
                   mini_mode=False):
        self._mini_mode = mini_mode
        self._name = name
        if not mini_mode:
            if unit_default is None:
                raise ValueError('unit_default is required')
            self.unit_default = unit_default

    @classmethod
    def create_reduced(cls, name: str):
        instance = cls(name=name, mini_mode=True)
        return instance

    def upgrade(self, unit_default: 'Unit'):
        # abort if object is already in full mode
        if not self._mini_mode:
            return False
        if unit_default is None:
            raise ValueError('unit_default is required')
        self._mini_mode = False
        if unit_default:
              self.unit_default = unit_default
        return True

    @property
    def mini_mode(self):
        return self._mini_mode

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def name(self):
        return self._name

    def __str__(self):
        return f'(Resource) {self.key}'


class ModelObject(ABC):

    active_from: datetime
    active_until: datetime


class Region(ModelObject):

    key_name = 'name'
    osm_id: int
    direct_constituents: List['Region'] = []
    parents: List['Region'] = []


    def __init__(self, name: str,
                 osm_id: int = None,
                 direct_constituents: 'Region' = [],
                 parents: 'Region' = [], *,
                   mini_mode=False):
        self._mini_mode = mini_mode
        self._name = name
        if not mini_mode:
            self.osm_id = osm_id
            if direct_constituents:
                self.direct_constituents.extend(direct_constituents)
            if parents:
                self.parents.extend(parents)

    @classmethod
    def create_reduced(cls, name: str):
        instance = cls(name=name, mini_mode=True)
        return instance

    def upgrade(self, osm_id: int = None,
                direct_constituents: 'Region' = [],
                parents: 'Region' = []):
        # abort if object is already in full mode
        if not self._mini_mode:
            return False
        self._mini_mode = False
        if osm_id:
              self.osm_id = osm_id
        if direct_constituents:
              self.direct_constituents = direct_constituents
        if parents:
              self.parents = parents
        return True

    @property
    def mini_mode(self):
        return self._mini_mode

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def name(self):
        return self._name

    def __str__(self):
        return f'(Region) {self.key}'


class Place(ModelObject):

    key_name = 'identifier'
    osm_id: int
    location: tuple
    in_region: List['Region'] = []
    processed_resources: List['Resource'] = []
    conduits_in: List['Conduit'] = []
    conduits_out: List['Conduit'] = []


    def __init__(self, identifier: str,
                 location: tuple = None,
                 osm_id: int = None,
                 in_region: 'Region' = [],
                 processed_resources: 'Resource' = [],
                 conduits_in: 'Conduit' = [],
                 conduits_out: 'Conduit' = [], *,
                   mini_mode=False):
        self._mini_mode = mini_mode
        self._identifier = identifier
        if not mini_mode:
            if location is None:
                raise ValueError('location is required')
            self.location = location
            self.osm_id = osm_id
            if in_region:
                self.in_region.extend(in_region)
            if processed_resources:
                self.processed_resources.extend(processed_resources)
            if conduits_in:
                self.conduits_in.extend(conduits_in)
            if conduits_out:
                self.conduits_out.extend(conduits_out)

    @classmethod
    def create_reduced(cls, identifier: str):
        instance = cls(identifier=identifier, mini_mode=True)
        return instance

    def upgrade(self, location: tuple,
                osm_id: int = None,
                in_region: 'Region' = [],
                processed_resources: 'Resource' = [],
                conduits_in: 'Conduit' = [],
                conduits_out: 'Conduit' = []):
        # abort if object is already in full mode
        if not self._mini_mode:
            return False
        if location is None:
            raise ValueError('location is required')
        self._mini_mode = False
        if location:
              self.location = location
        if osm_id:
              self.osm_id = osm_id
        if in_region:
              self.in_region = in_region
        if processed_resources:
              self.processed_resources = processed_resources
        if conduits_in:
              self.conduits_in = conduits_in
        if conduits_out:
              self.conduits_out = conduits_out
        return True

    @property
    def mini_mode(self):
        return self._mini_mode

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def identifier(self):
        return self._identifier

    def __str__(self):
        return f'(Place) {self.key}'


class Conduit(ModelObject):

    key_name = 'identifier'
    transmits_resource: 'Resource'
    capacity: 'Value'
    origin: 'Place'
    target: 'Place'


    def __init__(self, identifier: str,
                 transmits_resource: 'Resource' = None,
                 capacity: 'Value' = None,
                 origin: 'Place' = None,
                 target: 'Place' = None, *,
                   mini_mode=False):
        self._mini_mode = mini_mode
        self._identifier = identifier
        if not mini_mode:
            if transmits_resource is None:
                raise ValueError('transmits_resource is required')
            if capacity is None:
                raise ValueError('capacity is required')
            if origin is None:
                raise ValueError('origin is required')
            if target is None:
                raise ValueError('target is required')
            self.transmits_resource = transmits_resource
            self.capacity = capacity
            self.origin = origin
            self.target = target

    @classmethod
    def create_reduced(cls, identifier: str):
        instance = cls(identifier=identifier, mini_mode=True)
        return instance

    def upgrade(self, transmits_resource: 'Resource',
                capacity: 'Value',
                origin: 'Place',
                target: 'Place'):
        # abort if object is already in full mode
        if not self._mini_mode:
            return False
        if transmits_resource is None:
            raise ValueError('transmits_resource is required')
        if capacity is None:
            raise ValueError('capacity is required')
        if origin is None:
            raise ValueError('origin is required')
        if target is None:
            raise ValueError('target is required')
        self._mini_mode = False
        if transmits_resource:
              self.transmits_resource = transmits_resource
        if capacity:
              self.capacity = capacity
        if origin:
              self.origin = origin
        if target:
              self.target = target
        return True

    @property
    def mini_mode(self):
        return self._mini_mode

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def identifier(self):
        return self._identifier

    def __str__(self):
        return f'(Conduit) {self.key}'
