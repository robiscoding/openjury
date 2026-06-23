#!/usr/bin/env python3
"""
OpenJury Web Integration Example

Wraps OpenJury in a Flask API. Clients POST a prompt and an endpoint spec;
the server fetches the agent's response and returns an AgentEvalResult.

Usage:
    pip install flask
    export OPENROUTER_API_KEY="..."
    python examples/web_server/web_integration.py

Test with curl:
    curl -X POST http://localhost:5000/evaluate \\
      -H "Content-Type: application/json" \\
      -d '{
        "prompt": "How do I reset my password?",
        "endpoint": {
          "url": "http://localhost:8080/v1/chat/completions",
          "alias": "my-agent",
          "headers": {"Authorization": "Bearer ${AGENT_API_KEY}"},
          "request_body_template": {
            "model": "my-model",
            "messages": [{"role": "user", "content": "{prompt}"}]
          },
          "response_path": "choices.0.message.content"
        }
      }'
"""

import logging
import sys
from pathlib import Path

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from openjury import JuryConfig, OpenJury
from openjury.endpoint_fetcher import AgentEndpoint, EndpointFetchError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

jury: OpenJury | None = None


def initialize_jury() -> None:
    global jury
    config = JuryConfig.from_json_file(str(Path(__file__).parent / "config.json"))
    jury = OpenJury(config)
    logger.info(
        "Jury initialized: %d jurors, %d criteria",
        len(jury.jurors),
        len(config.criteria),
    )


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "jury_initialized": jury is not None})


@app.route("/jury/info", methods=["GET"])
def jury_info():
    if not jury:
        return jsonify({"error": "Jury not initialized"}), 500
    return jsonify(jury.get_summary())


@app.route("/evaluate", methods=["POST"])
def evaluate():
    if not jury:
        return jsonify({"error": "Jury not initialized"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    prompt = data.get("prompt")
    if not prompt:
        return jsonify({"error": "'prompt' is required"}), 400

    endpoint_data = data.get("endpoint")
    if not endpoint_data or not isinstance(endpoint_data, dict):
        return jsonify({"error": "'endpoint' object is required"}), 400

    try:
        endpoint = AgentEndpoint.model_validate(endpoint_data)
    except Exception as e:
        return jsonify({"error": f"Invalid endpoint spec: {e}"}), 400

    references = data.get("references")
    case_rules = data.get("case_rules")

    try:
        result = jury.score_response(
            prompt=prompt,
            endpoint=endpoint,
            references=references,
            case_rules=case_rules,
        )
    except EndpointFetchError as e:
        return jsonify({"error": f"Endpoint fetch failed: {e}"}), 502
    except Exception as e:
        logger.exception("Evaluation failed")
        return jsonify({"error": str(e)}), 500

    if request.args.get("simple"):
        return jsonify(
            {
                "composite_score": result.composite_score,
                "normalized_composite_score": result.normalized_composite_score,
                "score_scale": result.score_scale,
            }
        )

    return jsonify(
        {
            "composite_score": result.composite_score,
            "normalized_composite_score": result.normalized_composite_score,
            "score_scale": result.score_scale,
            "scored_metrics": result.scored_metrics.model_dump(),
            "criteria_evaluations": {
                name: ce.model_dump()
                for name, ce in result.criteria_evaluations.items()
            },
            "juror_scores": [
                {
                    "juror_name": js.juror_name,
                    "juror_weight": js.juror_weight,
                    "criterion_scores": js.criterion_scores,
                }
                for js in result.juror_scores
            ],
            "consistency_result": (
                result.consistency_result.model_dump()
                if result.consistency_result
                else None
            ),
        }
    )


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500


def main() -> None:
    try:
        logger.info("Initializing OpenJury...")
        initialize_jury()
        logger.info(
            "\nStarting web server...\n"
            "  GET  /health        — health check\n"
            "  GET  /jury/info     — jury config summary\n"
            "  POST /evaluate      — evaluate a prompt\n"
            "  POST /evaluate?simple — composite score only\n"
        )
        app.run(debug=True, host="0.0.0.0", port=5000)
    except Exception as e:
        logger.error("Failed to start: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
