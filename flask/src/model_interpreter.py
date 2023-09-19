import re
import os
import random
import string
from src.runtime_manager import RuntimeManager
from src.dm_specs import ModelSpecifications
from src.model_db import ModelDB

valid_commands = ["get", "create", "add", "io", "help"]

command_help = """
_______ Command Usage _______

- Any input is directly evaluated as a Python expression unless it starts with the '>' character.
- Expressions starting with '>' are treated as special commands.

_______ Available Commands _______

> help [command] - Provides further information about the usage of each command.

> get [class_name] [attribute/reference=value] ... [attribute/reference=value] optional: as [name of return list] 
    - Loads a model object or list of model objects of type class_name based on attribute/reference=value specifications. 
    - Results can optionally be stored under a specific name.

> create [class_name] -help 
    - Provides information about the required and optional parameters for a specific class.

> create [class_name] [attribute/reference=value] ... [attribute/reference=value] 
    - Creates a new model object with the specified parameters in both program context and persistent storage.

> add [expression that evaluates to a model object or list of model objects] 
    - Adds a model object or list of model objects created in program context to persistent storage.

_______ Referring to Model Objects _______

- To refer to a specific model object within an expression, use the format: @Class.Key
- This format can be used anywhere within your expression to fetch and utilize model objects.

"""


BASIC_TYPES = {float, int, str}

class ModelInterpreter:
    class_types: dict

# region Constructor and @property Attributes

    def __init__(self, URI: str, AUTH: tuple, model_specification: str, model_code: str):
        self.runtime: RuntimeManager = RuntimeManager("/workspace/data_models/model_code/" + model_code)
        self.model_specs = ModelSpecifications(xml_path="/workspace/data_models/" + model_specification,
                                               xsd_path="/workspace/data_models/format_specifications/dm_specification_schema.xsd")
        self.db: ModelDB = ModelDB(self.model_specs, self.runtime, URI, AUTH)

# endregion

##########################
### REQUEST PROCESSING ###
##########################

    def _generate_response(self, message: str):
        return {"result": str(message), "objects": self.runtime.get_runtime_objects()}

    def _interpret_input(self, input_str):
        # Recognize all @Class.Key mentions and replace accordingly
        pattern = r'@([\w]+)\.([\w]+)(?=\W|$)'  # This regex captures @Class.Key
        replacement = '__get_model_object__("\\1", "\\2")'  # Replacement pattern for the recognized mentions

        interpreted_input = re.sub(pattern, replacement, input_str)
        return interpreted_input

    def _generate_random_name(self, length=8):
        # Generate a random name for storing the result if no name is provided
        return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))

    def process_request(self, input_str: str):
        # Check if the input starts with a special command indicator ('>')
        if input_str.startswith('>'):
            result = self.process_command(input_str[1:].strip())  # Remove the '>' and pass the rest
        else:
            try:
                result = self.execute_expression(input_str)
            except Exception as e:
                result = f"Error occurred during execution of {input_str}:\r\n{str(e)}"
        return self._generate_response(str(result))

    def execute_expression(self, expression: str):
        exp = self._interpret_input(expression)
        # If the expression contains '=', assume it's an assignment and use exec
        if '=' in exp:
            # Execute the assignment - TODO: make robust against malicious code execution
            self.runtime.execute(exp)
            # Parse the variable name and retrieve its value
            var_name = expression.split('=')[0].strip()
            result = self.runtime.get_from_scope(var_name)
        else:
            # Otherwise, assume it's an expression and use eval
            result = self.runtime.evaluate(exp)
        return result

    def process_command(self, command_str):
        # Split the input to identify the command and its arguments
        parts = command_str.split(maxsplit=1)  # maxsplit ensures only the first space is considered
        command = parts[0]
        if not command in valid_commands:
            return f"Unknown command: {command}"
        arguments = parts[1] if len(parts) > 1 else ""

        # Determine which command to process
        if command == "add":
            return self.process_add(arguments)
        elif command == "create":
            return self.process_create(arguments)
        elif command == "get":
            return self.process_get(arguments)
        elif command == "io":
            return self.process_io(arguments)
        elif command == "help":
            return self.process_help(arguments)
        return f"Unknown command: {command}"

# region command processing

    def process_get(self, command_str: str) -> str:
        """
        Processes a 'get' command to retrieve model objects based on specified attributes.

        Parameters:
        - command_str (str): The command string, starting with the class name followed 
                            by a series of attribute=value pairs, optionally ending with 
                            'as <name>' to specify the name of the list or variable under 
                            which the result should be stored.

        Behavior:
        1. If the command contains only the class name and "-help", it returns a summary of 
        the available variables for that class.
        2. The command then processes the attribute=value pairs to build the filter criteria.
        3. If the keyword 'as' is encountered, the subsequent word is used as the name under 
        which the result will be stored. If not provided, a random name is generated.
        4. The command attempts to fetch model objects based on the filter criteria.
        5. If only one object is fetched, it is stored directly under the specified or 
        generated name. If multiple objects are fetched, they are stored as a list.

        Returns:
        - A string message indicating the outcome of the command, which could be an error 
        message, a summary of available variables, or a success message detailing the 
        number of objects retrieved and their storage name.

        Example usage:
        > get ClassName attribute1=value1 attribute2=value2 as result_name
        > get ClassName -help
        """
        # Split the arguments
        args = command_str.split()

        # Validate if the class name is provided
        if not args:
            return "Please specify the class name and the attributes to get an object."

        class_name = args[0]

        if len(args) > 1 and args[1] == "-help":
            return "\n".join(self.model_specs.get_variable_summary(class_name))

        # Process the attribute/reference specifications
        filter_args = {}
        list_name = None
        for arg in args[1:]:
            if arg == "as":
                # The next argument should be the name of the list
                try:
                    list_name = args[args.index(arg) + 1]
                except IndexError:
                    return "Expected a name after 'as'."
                break
            elif "=" in arg:
                key, value = arg.split("=", 1)
                filter_args[key] = self.execute_expression(value)
            else:
                return f"Invalid argument format: {arg}"

        # If no name is provided, generate a random one
        if not list_name:
            list_name = self._generate_random_name()

        # Fetch the objects using the filter arguments
        objects = self.db.find_objects(class_name, filter_args)

        if not objects:
            return f"No objects of type {class_name} matching the criteria found."

        # If only one object, store it directly. Otherwise, store as a list.
        if len(objects) == 1:
            self.runtime.set_to_scope(list_name, objects[0])
            return f"Object of type {class_name} added as {list_name}."
        else:
            self.runtime.set_to_scope(list_name, objects)
            return f"{len(objects)} objects of type {class_name} added to {list_name}."

    def process_create(self, command_str: str) -> str:
        """
        Processes a 'create' command to instantiate a new model object based on provided attributes.

        Parameters:
        - command_str (str): The command string, starting with the class name followed 
                            by a series of attribute=value pairs.

        Behavior:
        1. Extracts the class name and validates its existence.
        2. Processes the attribute=value pairs to construct the model object.
        3. Calls the appropriate function (`self.create_object`) to instantiate the object.

        Returns:
        - A string message indicating the outcome of the command, which could be an error message, 
        a help message, or a success message with a representation of the created object.
        """
        
        # Split the arguments
        args = command_str.split()

        # Validate if the class name is provided and is known
        if not args:
            return "No arguments provided."
        
        class_name = args[0]
        if class_name not in self.model_specs.get_class_names():
            return "Unknown Object Type."

        # If only the class name is provided or if help is requested
        if len(args) == 1 or args[1] == "-help":
            return "\n".join(self.model_specs.get_variable_summary(class_name))

        # Process the attribute/reference specifications
        init_params = {}
        for arg in args[1:]:
            key, value_str = arg.split("=", 1)
            try:
                value = self.execute_expression(value_str)
                init_params[key] = value
            except Exception as e:
                return f"Error occurred during evaluation of {value_str}: {str(e)}"

        # Create the object
        try:
            obj = self.db.create_object(class_name, init_params)
            return str(obj)
        except Exception as e:
            return f"Error occurred during object creation: {str(e)}"

    def process_add(self, expression: str) -> str:
        """
        Processes an 'add' command to add an object or list of objects to the model.

        Parameters:
        - expression (str): A Python expression that evaluates to an object or a list of objects.

        Behavior:
        1. Evaluates the provided expression.
        2. Checks if the resulting object (or objects) are of a known model object type.
        3. Calls the appropriate function (`self.add_object` or `self.add_multiple_objects`) to add the object(s) to the model.

        Returns:
        - A string message indicating the outcome of the command, which could be an error message or a success message.
        """
        
        try:
            # Evaluate the expression
            result = self.execute_expression(expression)

            valid_classes = self.model_specs.get_class_names()
            # Check if the result is a list of known model objects
            if isinstance(result, list) and all(type(item).__name__ in valid_classes for item in result):
                if self.db.add_multiple_objects(result):
                    return "All objects added successfully."
                else:
                    return "Failed to add list of objects."
            
            # Check if the result is a singular known model object
            elif type(result).__name__ in valid_classes:
                try:
                    self.db.add_object(result)
                    return f"Object {result} added successfully."
                except Exception as e:
                    return f"Failed to add object: {result}"

            # If result is neither a list of known model objects nor a singular known model object
            else:
                return f"Expression does not evaluate to a recognized model object or list of model objects."

        except Exception as e:
            return f"Error occurred during evaluation: {str(e)}"
        
    def process_io(self, command: str) -> str:
        """
        Process IO commands related to the payload bay.

        Args:
            command (str): The input command string.

        Returns:
            str: The result or response to the command.
        """

        # Split the command into parts
        parts = command.split()

        # Check for valid commands
        if not parts:
            return "Invalid IO command."
        action = parts[0]

        # Handle 'list' action
        if action == "list":
            return self._list_payload_bay()

        # Handle 'read' action
        elif action == "read":
            filename = parts[1]
            var_name = parts[-1] if parts[-2] == "as" else None
            if len(parts) % 2 == 0:
                return self._read_file_to_variable(filename, var_name)
            else:
                class_method_str = parts[2]
                return self._read_and_process_file(filename, class_method_str, var_name)

        # Handle 'write' action
        elif action == "write":
            # Extract the expression, filename, and append flag
            expression = parts[1]
            filename = parts[2]
            append_flag = True if "-a" in parts else False
            return self._write_to_file(expression, filename, append_flag)

        else:
            return "Unknown IO action."

    def process_help(self, command_str: str) -> str:
        if not command_str:
            return command_help

        param = command_str.lower()
        
        if param == "get":
            return """
Usage for 'get' command:
> get [class_name] [attribute/reference=value] ... [attribute/reference=value] optional: as [name of return list]
- Loads a model object or list of model objects of type class_name based on attribute/reference=value specifications. 
- Results can optionally be stored under a specific name.
            """
        
        elif param == "create":
            return """
Usage for 'create' command:
> create [class_name] -help
- Displays required and optional parameters for class_name.
> create [class_name] [attribute1=value1] ... [attributeN=valueN]
- Creates a new model object with the specified parameters in both program context and persistent storage.
            """
        
        elif param == "add":
            return """
Usage for 'add' command:
> add [expression that evaluates to a model object or list of model objects]
- Adds a model object or list of model objects created in program context to persistent storage.
            """

        else:
            return f"Unknown help topic: {param}\r\n" + command_help

# endregion

##########################
#### IO FUNCTIONALITY ####
##########################

    def _list_payload_bay(self) -> str:
        """
        List the files in the payload bay.

        Returns:
            str: List of files in the payload bay.
        """
        files = os.listdir("payload_bay")
        if not files:
            return "Payload bay is empty."
        return "\n".join(files)

    def _read_file_to_variable(self, filename: str, var_name: str = None) -> str:
        """
        Read the file content and store it in a variable.

        Args:
            filename (str): Name of the file.
            var_name (str, optional): Name of the variable to store the content. Defaults to filename.

        Returns:
            str: Confirmation message.
        """
        with open(os.path.join("payload_bay", filename), 'r') as file:
            content = file.read()
        
        var_name = var_name or filename
        # Store the content in a variable
        self.runtime.set_to_scope(var_name, content)
        
        return f"Content of {filename} has been stored in variable: {var_name}"
    
    def _read_and_process_file(self, filename: str, function_str: str, var_name: str = None) -> str:
        """
        Read the file content and process it using the specified class method.

        Args:
            filename (str): Name of the file.
            function_str (str): String representation of the function or class method to process the content.
            var_name (str, optional): Name of the variable to store the content. Defaults to filename.

        Returns:
            str: Result after processing the content.
        """
        # Check if function_str contains '.' indicating it's a class method
        if '.' in function_str:
            class_name, method_name = function_str.split('.')
            
            # Get the class and method from the loaded module
            target_class = self.runtime.get_attr(class_name)
            if not target_class:
                return f"Error: {class_name} not found."
            
            target_function = getattr(target_class, method_name, None)
            if not target_function:
                return f"Error: {function_str} not found."
        else:
            # It's a function directly in the loaded module
            target_function = self.runtime.get_attr(function_str)
            
            if not target_function:
                return f"Error: {function_str} not found."

        with open(os.path.join("payload_bay", filename), 'r') as file:
            content = file.read()

        # Process the content using the target function
        result = target_function(content)

        # calculate var name
        var_name = var_name if var_name else filename
        # Store the result in a runtime variable
        self.runtime.set_to_scope(var_name, result)

        return f"Processed content of {filename} using {function_str} and stored the result in variable: {var_name}"
    
    def _write_to_file(self, expression: str, filename: str, append: bool) -> str:
        """
        Evaluate the expression and write the result to the specified file.

        Args:
            expression (str): The expression to evaluate.
            filename (str): The name of the target file.
            append (bool): If True, append to the file; otherwise, overwrite.

        Returns:
            str: A message indicating success or failure.
        """
        try:
            # Evaluate the expression
            content = self.runtime.evaluate(expression)
            if not isinstance(content, str):
                return f"Error: Expression did not evaluate to a string."

            # Write or append to the file
            mode = 'a' if append else 'w'
            with open(os.path.join("payload_bay", filename), mode) as file:
                file.write(content)
            return f"Content written to {filename} successfully."
        except Exception as e:
            return f"Error writing to file: {e}"
