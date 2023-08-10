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

    def __init__(self, name: str):
        self._name = name

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
                 value: float,
                 unit: 'Unit',
                 used_in: 'ModelObject' = None):
        self._identifier = identifier
        self.value = value
        self.unit = unit
        self.used_in = used_in

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
                 unit_default: 'Unit'):
        self._name = name
        self.unit_default = unit_default

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
                 direct_constituents: List['Region'] = [],
                 parents: List['Region'] = []):
        self._name = name
        self.osm_id = osm_id
        if direct_constituents:
            self.direct_constituents.extend(direct_constituents)
        if parents:
            self.parents.extend(parents)

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
                 location: tuple,
                 osm_id: int = None,
                 in_region: List['Region'] = [],
                 processed_resources: List['Resource'] = [],
                 conduits_in: List['Conduit'] = [],
                 conduits_out: List['Conduit'] = []):
        self._identifier = identifier
        self.osm_id = osm_id
        self.location = location
        if in_region:
            self.in_region.extend(in_region)
        if processed_resources:
            self.processed_resources.extend(processed_resources)
        if conduits_in:
            self.conduits_in.extend(conduits_in)
        if conduits_out:
            self.conduits_out.extend(conduits_out)

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
                 transmits_resource: 'Resource',
                 capacity: 'Value',
                 origin: 'Place',
                 target: 'Place'):
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

    def __str__(self):
        return f'(Conduit) {self.key}'
