import re
import json
from typing import List, Optional, Union
from abc import ABC
from datetime import datetime
from data_models.model_code.model_entity import ModelEntity

INVERSE_RELATIONSHIPS = {

}

register = {}

class AssetAccount(ModelEntity):

    def __init__(self,
                 key: str=None,
                 transactions: List['Tx']=[], *,
                   mini_mode=False):
        if not key:
            raise ValueError('Attribute key is required')
        super().__init__(key=key, mini_mode=mini_mode)
        if not mini_mode:
            self.transactions: List ['Tx'] = transactions

    def upgrade(self,
                transactions: List['Tx']=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False
        if transactions is not None:
            self.transactions.extend(transactions)
        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def name(self):
        return self.key

    def __str__(self) -> str:
        return self.key

class BudgetAccount(ModelEntity):

    def __init__(self,
                 yearly_budget: float=None,
                 key: str=None,
                 transactions: List['Tx']=[], *,
                   mini_mode=False):
        if not key:
            raise ValueError('Attribute key is required')
        super().__init__(key=key, mini_mode=mini_mode)
        if not mini_mode:
            self.yearly_budget: float = yearly_budget
            self.transactions: List ['Tx'] = transactions

    def upgrade(self,
                yearly_budget: float=None,
                transactions: List['Tx']=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False
        self.yearly_budget = yearly_budget if yearly_budget is not None else getattr(self, 'yearly_budget', None)
        if transactions is not None:
            self.transactions.extend(transactions)
        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def name(self):
        return self.key

    def __str__(self) -> str:
        return self.key

class Tx(ModelEntity):

    def __init__(self,
                 description: str=None,
                 amount: float=None,
                 time: datetime=None,
                 key: str=None, *,
                   mini_mode=False):
        if not key:
            raise ValueError('Attribute key is required')
        super().__init__(key=key, mini_mode=mini_mode)
        if not mini_mode:
            if description is None:
                raise ValueError('Attribute description is required')
            self.description: str = description
            if amount is None:
                raise ValueError('Attribute amount is required')
            self.amount: float = amount
            if time is None:
                raise ValueError('Attribute time is required')
            self.time: datetime = time

    def upgrade(self,
                description: str=None,
                amount: float=None,
                time: datetime=None):
        # Abort if object is already in full mode
        if not self._mini_mode:
            return False
        if description is None:
            raise ValueError('Attribute description is required for upgrade')
        self.description = description if description is not None else getattr(self, 'description', None)
        if amount is None:
            raise ValueError('Attribute amount is required for upgrade')
        self.amount = amount if amount is not None else getattr(self, 'amount', None)
        if time is None:
            raise ValueError('Attribute time is required for upgrade')
        self.time = time if time is not None else getattr(self, 'time', None)
        # Indicate successful upgrade
        self._mini_mode = False
        return True

    @property
    def identifier(self):
        return self.key

    def __str__(self) -> str:
        return f"{self.description} {self.time.strftime('%d.%m.')}"

def read_json(json_str: str) -> List[Union[AssetAccount, BudgetAccount]]:
    # Parse the JSON string
    data = json.loads(json_str)

    # List to hold the created objects
    created_objects = []

    # Process assets
    for asset_data in data.get("assets", []):
        txs = []
        for tx_data in asset_data.get("tx", []):
            tx_id = tx_data["d"] + tx_data["t"]  # Use description + timestamp as identifier
            tx_time = datetime.strptime(tx_data["t"], "%d.%m.%Y %H:%M")
            tx = Tx(description=tx_data["d"], amount=float(tx_data["a"]), time=tx_time, key=tx_id)
            txs.append(tx)
        asset_account = AssetAccount(key=asset_data["name"], transactions=txs)
        created_objects.append(asset_account)

    # Process budgets
    for budget_data in data.get("budgets", []):
        txs = []
        for tx_data in budget_data.get("tx", []):
            tx_id = tx_data["d"] + tx_data["t"]  # Use description + timestamp as identifier
            tx_time = datetime.strptime(tx_data["t"], "%d.%m.%Y %H:%M")
            tx = Tx(description=tx_data["d"], amount=float(tx_data["a"]), time=tx_time, key=tx_id)
            txs.append(tx)
        budget_account = BudgetAccount(yearly_budget=float(budget_data["budget_year"]), 
                                       key=budget_data["name"], transactions=txs)
        created_objects.append(budget_account)

    return created_objects