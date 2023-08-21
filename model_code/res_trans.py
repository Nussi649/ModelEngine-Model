from typing import List, Optional, Union
from abc import ABC
from datetime import datetime
from model_entity import ModelEntity

INVERSE_RELATIONSHIPS = {
    'direct_constituents': 'parents',
    'conduits_in': 'target',
    'conduits_out': 'origin',
    'origin': 'conduits_out',
    'target': 'conduits_in'
}

class ModelObject(ABC):

    active_from: datetime
    active_until: datetime


class Unit(ModelEntity):

    def __init__(self,
                 name: str=None, *,
                   mini_mode=False):
        if not name:
            raise ValueError('Attribute name is required')
        super().__init__(key=name, mini_mode=mini_mode)

    def upgrade(self):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False

        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def name(self):
        return self.key

class Value(ModelEntity):

    value: float
    unit: Unit
    used_in: ModelObject

    def __init__(self,
                 identifier: str=None,
                 value: float=None,
                 unit: Unit=None,
                 used_in: ModelObject=None, *,
                   mini_mode=False):
        if not identifier:
            raise ValueError('Attribute identifier is required')
        super().__init__(key=identifier, mini_mode=mini_mode)
        if not mini_mode:
            if value is None:
                raise ValueError('Attribute value is required')
            self.value = value
            if unit is None:
                raise ValueError('Reference unit is required')
            self.unit = unit
            self.used_in = used_in

    def upgrade(self,
                value: float=None,
                unit: Unit=None,
                used_in: ModelObject=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False

        # Validate provided parameters
        if value is None:
            raise ValueError('Attribute value is required for upgrade')
        if unit is None:
            raise ValueError('Reference unit is required for upgrade')

        # Assign attributes and references
        self.value = value if value is not None else self.value
        self.unit = unit if unit is not None else self.unit
        self.used_in = used_in if used_in is not None else self.used_in

        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def identifier(self):
        return self.key
    
    def __str__(self) -> str:
        return f"[Value - {self.key}] {self.value} {self.unit.name}"

class Resource(ModelEntity):

    unit_default: Unit

    def __init__(self,
                 name: str=None,
                 unit_default: Unit=None, *,
                   mini_mode=False):
        if not name:
            raise ValueError('Attribute name is required')
        super().__init__(key=name, mini_mode=mini_mode)
        if not mini_mode:
            if unit_default is None:
                raise ValueError('Reference unit_default is required')
            self.unit_default = unit_default

    def upgrade(self,
                unit_default: Unit=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False

        # Validate provided parameters
        if unit_default is None:
            raise ValueError('Reference unit_default is required for upgrade')

        # Assign attributes and references
        self.unit_default = unit_default if unit_default is not None else self.unit_default

        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def name(self):
        return self.key

class Region(ModelEntity, ModelObject):

    osm_id: int
    direct_constituents: List['Region']
    parents: List['Region']

    def __init__(self,
                 name: str=None,
                 osm_id: int=None,
                 direct_constituents: List['Region']=None,
                 parents: List['Region']=None, *,
                   mini_mode=False):
        if not name:
            raise ValueError('Attribute name is required')
        super().__init__(key=name, mini_mode=mini_mode)
        if not mini_mode:
            self.osm_id = osm_id
            self.direct_constituents.extend(direct_constituents)
            self.parents.extend(parents)

    def upgrade(self,
                osm_id: int=None,
                direct_constituents: List['Region']=None,
                parents: List['Region']=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False

        # Validate provided parameters

        # Assign attributes and references
        self.osm_id = osm_id if osm_id is not None else self.osm_id
        if direct_constituents is not None:
            self.direct_constituents.extend(direct_constituents)
        if parents is not None:
            self.parents.extend(parents)

        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def name(self):
        return self.key

class Place(ModelEntity, ModelObject):

    osm_id: int
    location: tuple
    in_region: List['Region']
    processed_resources: List['Resource']
    conduits_in: List['Conduit']
    conduits_out: List['Conduit']

    def __init__(self,
                 identifier: str=None,
                 osm_id: int=None,
                 location: tuple=None,
                 in_region: List['Region']=None,
                 processed_resources: List['Resource']=None,
                 conduits_in: List['Conduit']=None,
                 conduits_out: List['Conduit']=None, *,
                   mini_mode=False):
        if not identifier:
            raise ValueError('Attribute identifier is required')
        super().__init__(key=identifier, mini_mode=mini_mode)
        if not mini_mode:
            self.osm_id = osm_id
            if location is None:
                raise ValueError('Attribute location is required')
            self.location = location
            self.in_region.extend(in_region)
            self.processed_resources.extend(processed_resources)
            self.conduits_in.extend(conduits_in)
            self.conduits_out.extend(conduits_out)

    def upgrade(self,
                osm_id: int=None,
                location: tuple=None,
                in_region: List['Region']=None,
                processed_resources: List['Resource']=None,
                conduits_in: List['Conduit']=None,
                conduits_out: List['Conduit']=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False

        # Validate provided parameters
        if location is None:
            raise ValueError('Attribute location is required for upgrade')

        # Assign attributes and references
        self.osm_id = osm_id if osm_id is not None else self.osm_id
        self.location = location if location is not None else self.location
        if in_region is not None:
            self.in_region.extend(in_region)
        if processed_resources is not None:
            self.processed_resources.extend(processed_resources)
        if conduits_in is not None:
            self.conduits_in.extend(conduits_in)
        if conduits_out is not None:
            self.conduits_out.extend(conduits_out)

        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def identifier(self):
        return self.key

class Conduit(ModelEntity, ModelObject):

    transmits_resource: Resource
    capacity: Value
    origin: Place
    target: Place

    def __init__(self,
                 identifier: str=None,
                 transmits_resource: Resource=None,
                 capacity: Value=None,
                 origin: Place=None,
                 target: Place=None, *,
                   mini_mode=False):
        if not identifier:
            raise ValueError('Attribute identifier is required')
        super().__init__(key=identifier, mini_mode=mini_mode)
        if not mini_mode:
            if transmits_resource is None:
                raise ValueError('Reference transmits_resource is required')
            self.transmits_resource = transmits_resource
            if capacity is None:
                raise ValueError('Reference capacity is required')
            self.capacity = capacity
            if origin is None:
                raise ValueError('Reference origin is required')
            self.origin = origin
            if target is None:
                raise ValueError('Reference target is required')
            self.target = target

    def upgrade(self,
                transmits_resource: Resource=None,
                capacity: Value=None,
                origin: Place=None,
                target: Place=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False

        # Validate provided parameters
        if transmits_resource is None:
            raise ValueError('Reference transmits_resource is required for upgrade')
        if capacity is None:
            raise ValueError('Reference capacity is required for upgrade')
        if origin is None:
            raise ValueError('Reference origin is required for upgrade')
        if target is None:
            raise ValueError('Reference target is required for upgrade')

        # Assign attributes and references
        self.transmits_resource = transmits_resource if transmits_resource is not None else self.transmits_resource
        self.capacity = capacity if capacity is not None else self.capacity
        self.origin = origin if origin is not None else self.origin
        self.target = target if target is not None else self.target

        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def identifier(self):
        return self.key