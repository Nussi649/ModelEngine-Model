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
DEFAULT_SPECS = "FinanceHelper.xml"
DEFAULT_CODE = "FinanceHelper_v1.py"

VALID_FILETYPES = {
    'specs': (DIRECTORY_SPECS, '.xml'),
    'code': (DIRECTORY_CODE, '.py'),
    'payload': (DIRECTORY_PAYLOAD, '*')
    }

RUNTIME_MANAGER = RuntimeManager(DIRECTORY_CODE + DEFAULT_CODE)
MODEL_SPECIFICATIONS = ModelSpecifications(xml_path=DIRECTORY_SPECS + DEFAULT_SPECS,
                                           xsd_path=DIRECTORY_SPECS + "format_specifications/dm_specification_schema.xsd")
MODEL_DB = ModelDB(MODEL_SPECIFICATIONS, RUNTIME_MANAGER, URI, AUTH)
MODEL_INTERPRETER = ModelInterpreter(RUNTIME_MANAGER, MODEL_SPECIFICATIONS, MODEL_DB)

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
    
    try:
        if filetype == "specs":
            MODEL_SPECIFICATIONS.load_file(xml_path=filepath)
        elif filetype == "code":
            RUNTIME_MANAGER.load_module(filepath)
        else:
            return
        return jsonify({"success": f"{filename} ({filetype}) activated successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=os.environ.get("FLASK_RUN_PORT", 5000),
        debug=True,
    )