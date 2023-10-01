from typing import List, Optional, Union
from abc import ABC
from datetime import datetime
from src.core import *
import json

INVERSE_RELATIONSHIPS = {

}

register = {}

class PayAcc(ModelObject):

    def __init__(self,
                 key: str=None, *,
                   mini_mode=False):
        if not key:
            raise ValueError('Attribute key is required')
        super().__init__(key=key, mini_mode=mini_mode)
        self.transactions: 'Collection' = Collection(PayAcc, key, 'transactions', Tx)
        self.account_balance: 'Collection' = Collection(PayAcc, key, 'account_balance', TimeSeriesPoint)

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

class InvAcc(ModelObject):

    def __init__(self,
                 key: str=None, *,
                   mini_mode=False):
        if not key:
            raise ValueError('Attribute key is required')
        super().__init__(key=key, mini_mode=mini_mode)
        self.transactions: 'Collection' = Collection(InvAcc, key, 'transactions', Tx)
        self.expenses: 'Collection' = Collection(InvAcc, key, 'expenses', TimeSeriesPoint)

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

class Tx(Composite):
    def __init__(self, amount: float, description: str, timestamp: datetime):
        self.amount = amount
        self.description = description
        self.timestamp = timestamp

    def __str__(self) -> str:
        formatted_timestamp = self.timestamp.strftime("%d.%m.%y %H:%M")
        formatted_amount = "{:.2f}".format(self.amount).replace('.', ',')
        return f"{self.description}: {formatted_amount}€ ({formatted_timestamp})"


class TimeSeriesPoint(Composite):
    def __init__(self, value: float, timestamp: datetime):
        self.value = value
        self.timestamp = timestamp

def create_objects(file_content: str) -> list:
    """
    Parses the provided JSON content and creates the respective PayAcc and InvAcc objects.

    Args:
    - file_content (str): JSON content string containing the account information.

    Returns:
    - list: List of instantiated PayAcc and InvAcc objects.
    """

    data = json.loads(file_content)

    # List to store the created account objects
    account_objects = []

    # Create PayAcc objects
    for paccount in data.get("paccounts", []):
        name = paccount["name"]
        payacc_obj = PayAcc(key=name)
        account_objects.append(payacc_obj)

    # Create InvAcc objects
    for iaccount in data.get("iaccounts", []):
        name = iaccount["name"]
        invacc_obj = InvAcc(key=name)
        account_objects.append(invacc_obj)

    return account_objects

def populate_transactions(file_content: str):
    data = json.loads(file_content)
    
    # For PayAccs
    for acc in data["paccounts"]:
        if acc["entries"]:
            account_key = acc["name"]
            account_obj = register["PayAcc"][account_key]

            # Transform the list of JSON objects into a list of dictionaries
            tx_list = [{"amount": float(entry["a"]), 
                        "description": entry["d"], 
                        "timestamp": datetime.strptime(entry["t"], "%d.%m.%Y %H:%M")} 
                       for entry in acc["entries"]]
            
            # Add the composites
            account_obj.transactions.add(tx_list)

    # For InvAccs
    for acc in data["iaccounts"]:
        if acc["entries"]:
            account_key = acc["name"]
            account_obj = register["InvAcc"][account_key]

            # Transform the list of JSON objects into a list of dictionaries
            tx_list = [{"amount": float(entry["a"]), 
                        "description": entry["d"], 
                        "timestamp": datetime.strptime(entry["t"], "%d.%m.%Y %H:%M")} 
                       for entry in acc["entries"]]

            # Add the composites
            account_obj.transactions.add(tx_list)

    return True
