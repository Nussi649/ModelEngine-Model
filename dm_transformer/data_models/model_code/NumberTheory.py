from typing import List, Optional, Union
from abc import ABC
from datetime import datetime
from data_models.model_code.model_entity import ModelEntity
import math

INVERSE_RELATIONSHIPS = {

}

register = {}


class Number(ModelEntity):

    factors: List ['Number'] = []

    def __init__(self,
                 key: str=None,
                 prime: bool=None,
                 factors: List['Number']=None, *,
                   mini_mode=False):
        if not key:
            raise ValueError('Attribute key is required')
        super().__init__(key=key, mini_mode=mini_mode)
        if not mini_mode:
            if prime is None:
                raise ValueError('Attribute Prime is required')
            self.prime = prime
            self.factors = factors if factors is not None else []

    def upgrade(self,
                prime: bool=None,
                factors: List['Number']=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False
        if prime is None:
            raise ValueError('Attribute Prime is required for upgrade')
        self.prime = prime if prime is not None else getattr(self, 'Prime', None)
        if factors is not None:
            self.factors.extend(factors)
        # Indicate successful upgrade
        self._mini_mode = False
        return True
    
    @property
    def value(self) -> int:
        return int(self.key)

    def is_factor_of(self, other: 'Number') -> bool:
        return other.value % self.value == 0

    def is_multiple_of(self, other: 'Number') -> bool:
        return self.value % other.value == 0

    def __str__(self) -> str:
        if self.prime:
            return f"{self.key} (p)"
        else:
            return f"{self.key} (np, [{', '.join([fac.key for fac in self.factors])}])"

    @classmethod
    def is_prime(cls, value: int) -> bool:
        if value <= 1:
            return False
        for i in range(2, int(math.sqrt(value)) + 1):
            if value % i == 0:
                return False
        return True

    @classmethod
    def from_integer(cls, value: int) -> 'Number':
        return cls(str(value), cls.is_prime(value), factorize(value))


def factorize(value: int) -> List['Number']:
    factors_set = set()
    i = 2
    while i * i <= value:
        while value % i == 0:
            value //= i
            factors_set.add(i)
        i += 1

    # If no factors have been found, the number itself is prime. Only add last prime factor otherwise
    if not factors_set:
        return []
    if value > 1:
        factors_set.add(value)
        
    # Convert the unique factors in the set to Number objects
    factors = [Number(key=str(factor), prime=Number.is_prime(factor)) for factor in factors_set]
    return factors