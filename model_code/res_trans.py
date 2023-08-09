from typing import List
from abc import ABC
from datetime import datetime

class Unit:

    key_name = 'name'

    def __init__(self, name: str):
        self._name = name

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def name(self):
        return self._name
        
    def __str__(self) -> str:
        return f"(Unit) {self.key}"


class Value:

    key_name = 'identifier'
    value: float
    unit: 'Unit'

    def __init__(self, identifier: str, value: float, unit: Unit):
        self._identifier = identifier
        self.value = value
        self.unit = unit

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def identifier(self):
        return self._identifier


class Resource:

    key_name = 'name'
    unit_default: 'Unit'

    def __init__(self, name: str, unit_default: Unit):
        self._name = name
        self.unit_default = unit_default

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def name(self):
        return self._name


class ModelObject(ABC):

    active_from: datetime
    active_until: datetime


class Region(ModelObject):

    key_name = 'name'
    osm_id: int
    direct_constituents: List['Region'] = []
    parents: List['Region'] = []

    def __init__(self, name: str):
        self._name = name

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def name(self):
        return self._name


class Place(ModelObject):

    key_name = 'identifier'
    osm_id: int
    location: tuple
    in_region: List['Region'] = []
    processed_resources: List['Resource'] = []
    conduits_in: List['Conduit'] = []
    conduits_out: List['Conduit'] = []

    def __init__(self, identifier: str, location: tuple):
        self._identifier = identifier
        self.location = location

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def identifier(self):
        return self._identifier


class Conduit(ModelObject):

    key_name = 'identifier'
    transmits_resource: 'Resource'
    capacity: 'Value'
    origin: 'Place'
    target: 'Place'

    def __init__(self, identifier: str, transmits_resource: Resource, capacity: Value, origin: Place, target: Place):
        self._identifier = identifier
        self.transmits_resource = transmits_resource
        self.capacity = capacity
        self.origin = origin
        self.target = target

    @property
    def key(self):
        return getattr(self, self.key_name)

    @property
    def identifier(self):
        return self._identifier
