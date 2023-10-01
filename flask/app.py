import os
import threading
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS ###################################### REMOVE FOR PRODUCTION #######################
from dotenv import load_dotenv
from neo4j import GraphDatabase
from werkzeug.utils import secure_filename
from src.runtime_manager import RuntimeManager
from src.model_interpreter import ModelInterpreter
from src.model_db import ModelDB
from src.dm_specs import ModelSpecifications
import logging


load_dotenv()
app = Flask(__name__, template_folder="templates")
CORS(app)                   ###################################### REMOVE FOR PRODUCTION #######################
URI = "neo4j://neo4j:7687"
AUTH = ("neo4j", os.getenv("NEO4J_PASSWORD"))
RESET_PASSWORD ="K€N0Bi"

DIRECTORY_SPECS = "/workspace/data_models/"
DIRECTORY_CODE = "/workspace/data_models/model_code/"
DIRECTORY_PAYLOAD = "/workspace/payload_bay/"
SPECIFICATIONS_FILE = "FinanceHelper.xml"
MODEL_CODE_FILE = "FinanceHelper_v1.py"

VALID_FILETYPES = {
    'specs': (DIRECTORY_SPECS, '.xml'),
    'code': (DIRECTORY_CODE, '.py'),
    'payload': (DIRECTORY_PAYLOAD, '*')
    }

RUNTIME_MANAGER = None
MODEL_SPECIFICATIONS = None
MODEL_DB = None
MODEL_INTERPRETER = None

# Function to handle terminal input
def terminal_input():
    while True:
        command = input("command: ")
        result = MODEL_INTERPRETER.process_request(command)
        print(result)

# Configure the logging level and format
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Create a separate thread to run the terminal_input function
terminal_thread = threading.Thread(target=terminal_input)
terminal_thread.start()

@app.route("/")
def status():
    return jsonify({"status": "ok", "password": "lol"}), 200

@app.route("/flask-health-check")
def flask_health_check():
    try:
        # Check the health status of the Flask application

        # Check if the Flask application is running
        if app and app.debug:
            # Check if the Flask application is in debug mode
            return jsonify({"status": "ok", "message": "Flask application is running in debug mode"}), 200
        else:
            # Check the health status of any other components or services used by the Flask application
            with GraphDatabase.driver("bolt://neo4j:7687") as driver:
                with driver.session() as session:
                    result = session.run("MATCH (n) RETURN count(n) as node_count")
                    node_count = result.single()["node_count"]

            # Provide custom health check logic here
            # You can check the status of databases, external services, etc.
            # If everything is fine, return a successful response
            return jsonify({"status": "ok", "message": f"Flask application is healthy. Node count in Neo4j: {node_count}"}), 200

    except Exception as e:
        # If there is an error, return a failure response
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/request", methods=["POST"])
def process_request():
    """
    relays request to ModelInterpreter instance and returns result
    """
    post_data = request.get_json()
    result = MODEL_INTERPRETER.process_request(post_data["command"])
    return jsonify({"status": "ok", "result": result["result"], "objects": result["objects"]})

@app.route("/terminal")
def terminal():
    return render_template('terminal.html')

############################################################
################### COMPONENT MANAGEMENT ###################
############################################################
#region component management
def start_component(component_name):
    global MODEL_INTERPRETER, MODEL_DB, MODEL_SPECIFICATIONS, RUNTIME_MANAGER
    
    if component_name == 'specs':
        logging.info('Starting specs component.')
        MODEL_SPECIFICATIONS = ModelSpecifications(xml_path=DIRECTORY_SPECS + SPECIFICATIONS_FILE,
                                                   xsd_path=DIRECTORY_SPECS + "format_specifications/dm_specification_schema.xsd")
    elif component_name == 'runtime':
        logging.info('Starting runtime component.')
        RUNTIME_MANAGER = RuntimeManager(DIRECTORY_CODE + MODEL_CODE_FILE)
    elif component_name == 'database':
        if MODEL_SPECIFICATIONS is None:
            logging.info('Specs component is not active. Starting specs component as it is a prerequisite for the database component.')
            start_component('specs')
        if RUNTIME_MANAGER is None:
            logging.info('Runtime component is not active. Starting runtime component as it is a prerequisite for the database component.')
            start_component('runtime')
        logging.info('Starting database component.')
        MODEL_DB = ModelDB(MODEL_SPECIFICATIONS, RUNTIME_MANAGER, URI, AUTH)
    elif component_name == 'interpreter':
        if MODEL_DB is None:
            logging.info('Database component is not active. Starting database component as it is a prerequisite for the interpreter component.')
            start_component('database')
        logging.info('Starting interpreter component.')
        MODEL_INTERPRETER = ModelInterpreter(RUNTIME_MANAGER, MODEL_SPECIFICATIONS, MODEL_DB)
    else:
        raise ValueError(f"Invalid component name: {component_name}")
    
def stop_component(component_name):
    global MODEL_INTERPRETER, MODEL_DB, MODEL_SPECIFICATIONS, RUNTIME_MANAGER

    if component_name == 'specs':
        if MODEL_INTERPRETER is not None:
            logging.warning('Stopping interpreter as specs component is being stopped.')
            MODEL_INTERPRETER = None
        if MODEL_DB is not None:
            logging.warning('Stopping database as specs component is being stopped.')
            MODEL_DB = None
        logging.info('Stopping specs component.')
        MODEL_SPECIFICATIONS = None
    elif component_name == 'runtime':
        if MODEL_INTERPRETER is not None:
            logging.warning('Stopping interpreter as runtime component is being stopped.')
            MODEL_INTERPRETER = None
        if MODEL_DB is not None:
            logging.warning('Stopping database as runtime component is being stopped.')
            MODEL_DB = None
        logging.info('Stopping runtime component.')
        RUNTIME_MANAGER = None
    elif component_name == 'database':
        if MODEL_INTERPRETER is not None:
            logging.warning('Stopping interpreter as database component is being stopped.')
            MODEL_INTERPRETER = None
        logging.info('Stopping database component.')
        MODEL_DB = None
    elif component_name == 'interpreter':
        logging.info('Stopping interpreter component.')
        MODEL_INTERPRETER = None
    else:
        raise ValueError(f"Invalid component name: {component_name}")
    
@app.route('/component-status', methods=['POST'])
def component_status():
    try:
        # Extract the components whose status needs to be fetched from the request data.
        data = request.json
        components = data.get('components', [])
        
        status = {}
        
        for component in components:
            if component == 'specs':
                status['specsActive'] = MODEL_SPECIFICATIONS is not None
                status['specsFilename'] = SPECIFICATIONS_FILE  # This can be None
                
            elif component == 'runtime':
                status['runtimeActive'] = RUNTIME_MANAGER is not None
                status['codeFilename'] = MODEL_CODE_FILE  # This can be None
                
            elif component == 'database':
                status['databaseActive'] = MODEL_DB is not None
                if MODEL_DB:
                    db_stats = MODEL_DB.get_stats()
                    status.update(db_stats)  # Add additional database stats to the response
                    
            elif component == 'interpreter':
                status['interpreterActive'] = MODEL_INTERPRETER is not None
                
        return jsonify(status)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400  # Respond with an error message in case of an exception
    
@app.route('/component-set-state', methods=['POST'])
def set_component_state():
    try:
        actions = request.json
        if isinstance(actions, dict) and 'actions' in actions:
            actions = actions['actions']
        if not isinstance(actions, list):
            raise ValueError("Invalid input: Expected a list of actions")
        
        # return variable, gets filled with relevant status information
        status = {}
        
        for action in actions:
            component_name = action.get('component')
            action_type = action.get('action')
            
            if action_type == 'start':
                start_component(component_name)
            elif action_type == 'stop':
                stop_component(component_name)
            else:
                raise ValueError(f"Invalid action type: {action_type} for component {component_name}")
            
            # compile responses by adding the corresponding attributes
            if component_name == 'specs':
                status['specsActive'] = MODEL_SPECIFICATIONS is not None
                status['specsFilename'] = SPECIFICATIONS_FILE  # This can be None
                
            elif component_name == 'runtime':
                status['runtimeActive'] = RUNTIME_MANAGER is not None
                status['codeFilename'] = MODEL_CODE_FILE  # This can be None
                
            elif component_name == 'database':
                status['databaseActive'] = MODEL_DB is not None
                if MODEL_DB:
                    db_stats = MODEL_DB.get_stats()
                    status.update(db_stats)  # Add additional database stats to the response
                    
            elif component_name == 'interpreter':
                status['interpreterActive'] = MODEL_INTERPRETER is not None
        
        return jsonify(status)
    
    except ValueError as ve:
        response = jsonify({"error": str(ve)})
        response.status_code = 400
        return response
#endregion

@app.route('/model-state', methods=['GET'])
def get_model_state():
    # Fetching basic database stats
    stats = MODEL_DB.get_stats()

    # Fetching the currently loaded specifications' name
    specs_filepath = MODEL_SPECIFICATIONS.xml_path
    specs_filename = os.path.basename(specs_filepath)

    # Fetching the currently loaded code's name
    code_filepath = RUNTIME_MANAGER.module_path
    code_filename = os.path.basename(code_filepath)

    # Appending additional data to the stats dict
    stats['specsFilename'] = specs_filename
    stats['codeFilename'] = code_filename

    return jsonify(stats)

###########################################################
##################### FILE MANAGEMENT #####################
###########################################################
# region file stuff
@app.route('/file-list/<contentType>', methods=['GET'])
def get_file_list(contentType):
    try:
        # Assigning the directory path and extension based on content type
        directory, extension = VALID_FILETYPES[contentType]

        # Getting the list of files
        if extension == '*':
            files = os.listdir(directory)
        else:
            files = [f for f in os.listdir(directory) if f.endswith(extension)]

        # Additional filter for code files
        if contentType == 'code':
            files = [f for f in files if f != 'core.py']

        return jsonify(files)

    except KeyError:
        return jsonify({"error": "Invalid content type"}), 400

@app.route('/file-content/<contentType>/<filename>', methods=['GET'])
def get_file_content(contentType, filename):
    try:
        # Assigning the directory path and extension based on content type
        directory, extension = VALID_FILETYPES[contentType]

        # Validating file extension
        if extension != '*' and not filename.endswith(extension):
            return jsonify({"error": "Invalid file type"}), 400

        # Validating restricted files
        if contentType == 'code' and filename == 'core.py':
            return jsonify({"error": "Restricted file"}), 400

        # Constructing the file path
        filepath = os.path.join(directory, filename)

        # Fetching the content
        with open(filepath, 'r') as file:
            content = file.read()
        return content

    except KeyError:
        return jsonify({"error": "Invalid content type"}), 400
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

@app.route('/upload-file/<contentType>', methods=['POST'])
def upload_file(contentType):
    try:
        # Validate content type and assign directory and extension
        directory, extension = VALID_FILETYPES[contentType]

        # Check if the post request has the file part
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        
        file = request.files['file']
        
        # If the user does not select a file, the browser submits an empty part without a filename.
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        
        # Validate the file extension
        if extension != '*' and not file.filename.endswith(extension):
            return jsonify({"error": "Invalid file type"}), 400
        
        # Constructing the file path
        filename = secure_filename(file.filename)
        filepath = os.path.join(directory, filename)
        
        # Check the overwrite flag
        overwrite = request.form.get('overwrite', 'false').lower() == 'true'
        
        # If the file exists and overwrite is False, return an error
        if os.path.exists(filepath) and not overwrite:
            return jsonify({"error": "File already exists"}), 409
        
        # Save the file
        file.save(filepath)
        
        return jsonify({"success": f"{filename} uploaded successfully!"}), 200
    
    except KeyError:
        return jsonify({"error": "Invalid content type"}), 400
    
@app.route('/delete-file/<filetype>/<filename>', methods=['DELETE'])
def delete_file(filetype, filename):
    # Verify that the filetype is valid
    if filetype not in VALID_FILETYPES:
        return jsonify({"error": "Invalid file type"}), 400
    
    directory, _ = VALID_FILETYPES[filetype]
    filepath = os.path.join(directory, filename)

    # Verify that the file exists
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    try:
        # Delete the file
        os.remove(filepath)
        return jsonify({"success": f"{filename} deleted successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/activate/<filetype>/<filename>', methods=['POST'])
def activate(filetype, filename):
    # Validate filetype and get the directory
    if filetype not in VALID_FILETYPES or filetype == 'payload':
        return jsonify({"error": "Invalid file type or action not allowed for payload"}), 400
    
    directory, _ = VALID_FILETYPES[filetype]
    filepath = os.path.join(directory, filename)
    
    # Check if the file exists
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    
    global SPECIFICATIONS_FILE, MODEL_CODE_FILE
    try:
        if filetype == "specs":
            SPECIFICATIONS_FILE = filename
            if MODEL_SPECIFICATIONS is not None:
                MODEL_SPECIFICATIONS.load_file(xml_path=filepath)
        elif filetype == "code":
            MODEL_CODE_FILE = filename
            if RUNTIME_MANAGER is not None:
                RUNTIME_MANAGER.load_module(filepath)
        else:
            return
        return jsonify({"success": f"{filename} ({filetype}) activated successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
#endregion

###########################################################
################### DATABASE MANAGEMENT ###################
###########################################################
# region database stuff
@app.route('/db-wipe', methods=['POST'])
def db_wipe():
    if MODEL_DB is not None:
        try:
            MODEL_DB.wipe_content()
            stats = MODEL_DB.get_stats()
            return jsonify(stats), 200
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error wiping the database: {str(e)}"}), 500
    else:
        return jsonify({"status": "error", "message": "Database component is not active!"}), 400


@app.route('/db-init', methods=['POST'])
def db_init():
    if MODEL_DB is not None:
        try:
            MODEL_DB.create_indexes()
            stats = MODEL_DB.get_stats()
            return jsonify(stats), 200
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error initializing the database: {str(e)}"}), 500
    else:
        return jsonify({"status": "error", "message": "Database component is not active!"}), 400
# endregion

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=os.environ.get("FLASK_RUN_PORT", 5000),
        debug=True,
    )