from typing import List, Optional, Union
from abc import ABC
from datetime import datetime
from model_entity import ModelEntity

INVERSE_RELATIONSHIPS = {

}

register = {}

class PayAcc(ModelEntity):

    def __init__(self,
                 key: str=None,
                 Transactions: List['Tx']=[],
                 Balances: List['TimeSeriesPoint']=[], *,
                   mini_mode=False):
        if not key:
            raise ValueError('Attribute key is required')
        super().__init__(key=key, mini_mode=mini_mode)
        if not mini_mode:
            self.Transactions: List ['Tx'] = Transactions
            self.Balances: List ['TimeSeriesPoint'] = Balances

    def upgrade(self,
                Transactions: List['Tx']=None,
                Balances: List['TimeSeriesPoint']=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False
        if Transactions is not None:
            self.Transactions.extend(Transactions)
        if Balances is not None:
            self.Balances.extend(Balances)
        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def Name(self):
        return self.key

class InvAcc(ModelEntity):

    def __init__(self,
                 key: str=None,
                 Transactions: List['Tx']=[],
                 Sums: List['TimeSeriesPoint']=[], *,
                   mini_mode=False):
        if not key:
            raise ValueError('Attribute key is required')
        super().__init__(key=key, mini_mode=mini_mode)
        if not mini_mode:
            self.Transactions: List ['Tx'] = Transactions
            self.Sums: List ['TimeSeriesPoint'] = Sums

    def upgrade(self,
                Transactions: List['Tx']=None,
                Sums: List['TimeSeriesPoint']=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False
        if Transactions is not None:
            self.Transactions.extend(Transactions)
        if Sums is not None:
            self.Sums.extend(Sums)
        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def Name(self):
        return self.key

class Tx(ModelEntity):

    def __init__(self,
                 Amount: float=None,
                 Description: str=None,
                 Timestamp: datetime=None,
                 key: str=None, *,
                   mini_mode=False):
        if not key:
            raise ValueError('Attribute key is required')
        super().__init__(key=key, mini_mode=mini_mode)
        if not mini_mode:
            if Amount is None:
                raise ValueError('Attribute Amount is required')
            self.Amount: float = Amount
            if Description is None:
                raise ValueError('Attribute Description is required')
            self.Description: str = Description
            if Timestamp is None:
                raise ValueError('Attribute Timestamp is required')
            self.Timestamp: datetime = Timestamp

    def upgrade(self,
                Amount: float=None,
                Description: str=None,
                Timestamp: datetime=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False
        if Amount is None:
            raise ValueError('Attribute Amount is required for upgrade')
        self.Amount = Amount if Amount is not None else getattr(self, 'Amount', None)
        if Description is None:
            raise ValueError('Attribute Description is required for upgrade')
        self.Description = Description if Description is not None else getattr(self, 'Description', None)
        if Timestamp is None:
            raise ValueError('Attribute Timestamp is required for upgrade')
        self.Timestamp = Timestamp if Timestamp is not None else getattr(self, 'Timestamp', None)
        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def UUID(self):
        return self.key

class TimeSeriesPoint(ModelEntity):

    def __init__(self,
                 Value: float=None,
                 Timestamp: datetime=None,
                 key: str=None, *,
                   mini_mode=False):
        if not key:
            raise ValueError('Attribute key is required')
        super().__init__(key=key, mini_mode=mini_mode)
        if not mini_mode:
            if Value is None:
                raise ValueError('Attribute Value is required')
            self.Value: float = Value
            if Timestamp is None:
                raise ValueError('Attribute Timestamp is required')
            self.Timestamp: datetime = Timestamp

    def upgrade(self,
                Value: float=None,
                Timestamp: datetime=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False
        if Value is None:
            raise ValueError('Attribute Value is required for upgrade')
        self.Value = Value if Value is not None else getattr(self, 'Value', None)
        if Timestamp is None:
            raise ValueError('Attribute Timestamp is required for upgrade')
        self.Timestamp = Timestamp if Timestamp is not None else getattr(self, 'Timestamp', None)
        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def UUID(self):
        return self.key