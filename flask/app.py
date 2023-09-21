import os
import threading
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS ###################################### REMOVE FOR PRODUCTION #######################
from dotenv import load_dotenv
from neo4j import GraphDatabase
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
DEFAULT_SPECS = "FinanceHelper.xml"
DEFAULT_CODE = "FinanceHelper_v1.py"

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

    # Fetching the currently loaded specifications' name and content
    specs_filepath = MODEL_SPECIFICATIONS.xml_path
    specs_filename = os.path.basename(specs_filepath)
    with open(specs_filepath, 'r') as f:
        specs_content = f.read()

    # Fetching the currently loaded code's name and content
    code_filepath = RUNTIME_MANAGER.module_path
    code_filename = os.path.basename(code_filepath)
    with open(code_filepath, 'r') as f:
        code_content = f.read()

    # Appending additional data to the stats dict
    stats['specsFilename'] = specs_filename
    stats['specsContent'] = specs_content
    stats['codeFilename'] = code_filename
    stats['codeContent'] = code_content

    return jsonify(stats)

@app.route('/filelist/<filetype>', methods=['GET'])
def get_file_list(filetype):
    if filetype == "specs":
        files = [f for f in os.listdir(DIRECTORY_SPECS) if f.endswith('.xml')]
        return jsonify(files)
    elif filetype == "code":
        files = [f for f in os.listdir(DIRECTORY_CODE) if f.endswith('.py') and f != 'core.py']
        return jsonify(files)
    else:
        return jsonify({"error": "Invalid file type"}), 400

@app.route('/file-content/<filetype>/<filename>', methods=['GET'])
def get_file_content(filetype, filename):
    # For specs
    if filetype == "specs":
        if not filename.endswith('.xml'):
            return jsonify({"error": "Invalid file type"}), 400

        filepath = os.path.join(DIRECTORY_SPECS, filename)

    # For code
    elif filetype == "code":
        if not filename.endswith('.py'):
            return jsonify({"error": "Invalid file type"}), 400
        if filename == 'core.py':
            return jsonify({"error": "Restricted file"}), 400

        filepath = os.path.join(DIRECTORY_CODE, filename)

    # If the filetype doesn't match any known types
    else:
        return jsonify({"error": "Invalid file type"}), 400

    # Fetching the content
    try:
        with open(filepath, 'r') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
    
@app.route('/upload-file/<filetype>', methods=['POST'])
def upload_file(filetype):
    # Check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']

    # If the user does not select a file, the browser submits an empty part without a filename.
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Get the load flag from the request parameters
    load_flag = request.args.get('load', default='false').lower() == 'true'

    # Check for valid file type and save accordingly
    if filetype == "specs":
        if not file.filename.endswith('.xml'):
            return jsonify({"error": "Invalid file type"}), 400
        filepath = os.path.join(DIRECTORY_SPECS, file.filename)

    elif filetype == "code":
        if not file.filename.endswith('.py'):
            return jsonify({"error": "Invalid file type"}), 400
        if file.filename == 'core.py':
            return jsonify({"error": "Restricted file"}), 400
        filepath = os.path.join(DIRECTORY_CODE, file.filename)

    else:
        return jsonify({"error": "Invalid file type"}), 400

    # Save the file
    file.save(filepath)

    # check if the file should be loaded
    if load_flag:
        if filetype == "specs":
            MODEL_SPECIFICATIONS.load_file(filepath)
            pass
        else: # can be assumed to be "code"
            RUNTIME_MANAGER.load_module(filepath)
    return jsonify({"success": f"{file.filename} uploaded successfully!"})

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=os.environ.get("FLASK_RUN_PORT", 5000),
        debug=True,
    )