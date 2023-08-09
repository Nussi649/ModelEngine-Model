import os
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
from neo4j import GraphDatabase
from model_interpreter import ModelInterpreter
import logging


load_dotenv()
app = Flask(__name__, template_folder="templates")

URI = "neo4j://neo4j:7687"
AUTH = ("neo4j", os.getenv("NEO4J_PASSWORD"))
RESET_PASSWORD ="K€N0Bi"
MODEL_INTERPRETER = ModelInterpreter(URI, AUTH, "res_trans.py")

# Configure the logging level and format
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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
    return jsonify({"status": "ok", "msg": result})


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=os.environ.get("FLASK_RUN_PORT", 5000),
        debug=True,
    )