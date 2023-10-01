import importlib
import sys
import json
import os


class ModuleUnavailableError(RuntimeError):
    pass


known_dicts = ["INVERSE_RELATIONSHIPS", "register"]


class RuntimeManager:
    def __init__(self, module_path: str):
        self.module_path = ""
        self.module_name = ""
        self.loaded_module = None
        self.execution_scope = {}

        self.load_module(module_path)

    def _load_module(self):
        """Load the module from the given path."""
        # If a module is already loaded, unload it
        if self.loaded_module:
            self._unload_module()
        # Constructing the module spec
        spec = importlib.util.spec_from_file_location(self.module_name, self.module_path)
        self.loaded_module = importlib.util.module_from_spec(spec)
        sys.modules[self.module_name] = self.loaded_module
        spec.loader.exec_module(self.loaded_module)
        
        # Ensure the loaded module has a register, create one if not
        if not hasattr(self.loaded_module, "register"):
            setattr(self.loaded_module, "register", {})

        # add module members to execution scope
        self.execution_scope = dict(self.loaded_module.__dict__)

    def _unload_module(self):
        """Unload the currently loaded module."""
        if self.module_name in sys.modules:
            del sys.modules[self.module_name]
        self.loaded_module = None

    def get_status(self) -> bool:
        return not (self.loaded_module is None)

    def refresh_module(self):
        """Refresh the loaded module."""
        self._unload_module()
        self._load_module()

    def load_module(self, module_path: str):
        """Load a new module."""
        # Store the current state
        old_module_path = self.module_path
        old_module_name = self.module_name
        
        try:
            # Attempt to set new module_path and module_name
            self.module_path = module_path
            self.module_name = os.path.splitext(os.path.basename(module_path))[0].replace(".py", "")
            
            # Attempt to load the new module
            self._load_module()
            
        except Exception as e:
            # If an error occurs, restore the old state
            self.module_path = old_module_path
            self.module_name = old_module_name
            self._load_module()
            # Re-raise the error with additional information, if needed
            raise RuntimeError(f"Error loading module {module_path}: {str(e)}") from e

    def execute(self, code: str):
        """Execute a block of code within the managed scope."""
        try:
            exec(code, self.execution_scope)
        except Exception as e:
            return str(e)
        return "Code executed successfully."

    def evaluate(self, expression: str):
        """Evaluate an expression and return its result."""
        return eval(expression, self.execution_scope)
    
    def set_to_scope(self, attr_name: str, value):
        self.execution_scope[attr_name] = value

    def get_attr(self, attr_name: str):
        return getattr(self.loaded_module, attr_name, None)
    
    def get_from_scope(self, attr_name: str):
        return self.execution_scope.get(attr_name, None)

    def get_register(self) -> dict:
        """
        Get the entire register of model objects.

        Returns:
            dict: A dictionary containing all registered model objects.
        """
        return getattr(self.loaded_module, "register", {})

    def get_type_register(self, class_name: str) -> dict:
        """
        Get the register of model objects of a specific type. If the type doesn't exist, initialize it.

        Args:
            class_name (str): The name of the class type to filter by.

        Returns:
            dict: A dictionary containing model objects of the specified class type.
        """
        general_register = self.get_register()
        if class_name not in general_register:
            general_register[class_name] = {}
        return general_register[class_name]

    def get_runtime_objects(self):
        response = {
            "model_objects": {},
            "runtime_objects": {
                "lists": [],
                "dicts": [],
                "variables": []
            }
        }
        
        # Handle the general_register (model objects)
        general_register = getattr(self.loaded_module, "register", {})
        for object_type, register in general_register.items():
            response["model_objects"][object_type] = [
                {"name": key, "content": str(value)}
                for key, value in register.items()
            ]
        
        # Handle other runtime objects
        for attr_name, value in self.execution_scope.items():
            if attr_name.startswith("_"):  # Exclude private members
                continue
            if attr_name in known_dicts:
                continue
            if type(value).__name__ in ["type", "ABCMeta", "module", "function"]: # Exclude classes, modules and functions
                continue
            if str(value).startswith("typing."): # Exclude typing module members
                continue
            obj_repr = {"name": attr_name}
            if isinstance(value, list):
                obj_repr["content"] = [{"type": type(item).__name__, "value": str(item)} for i, item in enumerate(value)]
                response["runtime_objects"]["lists"].append(obj_repr)
            elif isinstance(value, dict):
                obj_repr["content"] = [{"key": str(k), "type": type(v).__name__, "value": str(v)} for k, v in value.items()]
                response["runtime_objects"]["dicts"].append(obj_repr)
            else:
                obj_repr["type"] = type(value).__name__
                obj_repr["content"] = str(value)
                response["runtime_objects"]["variables"].append(obj_repr)
        
        return response

    def __str__(self):
        return json.dumps(self.execution_scope, default=str, indent=4)
