# ModelEngine-Model
System for Running a Model Instance and its Interpreter.

Contains Sub-Systems:

# Data Model Transformer
* Transforms an Ontology Schema file (XML) into the corresponding Model Code
* Defines ModelSpecifications class, which loads such a Schema file, validates it against its Meta-Schema and provides easily accessible information about the Ontology
* dm_transformer.py provides functions for the transformation into Model Code, using a ModelSpecifications object for validation and easy access to specifications structure

# Model Code
* Executable representation of the Data Model with Python classes for each model entity type
* Directory contains all Model Code files which are in use.
* Directory also contains ModelEntity class in model_entity.py: this serves as common super class for all model type representing classes implementing common functionality such as key attributes and create_reduced

# Flask
* App that serves as interface between outside requests and the Data Model Interpreter class
* Contains Data Model Interpreter, which interprets commands, handles program context and synchronizes object actions with the persistent database
