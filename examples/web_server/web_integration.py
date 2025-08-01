#!/usr/bin/env python3
"""
OpenJury Web Integration Example

This example demonstrates how to integrate OpenJury into a web application
using Flask.

Usage:
    pip install flask
    export OPENROUTER_API_KEY="your-api-key-here"
    python examples/server/web_integration.py

Then test with:
    curl -X POST http://localhost:5000/evaluate \
      -H "Content-Type: application/json" \
      -d '{
        "prompt": "I just received a parking ticket in San Francisco for being 5 minutes over the meter. Is it worth contesting, and what's the process like?",
        "responses": [
          {
            "content": "Parking tickets in San Francisco are a common experience! If you believe the ticket was issued in error, or if there were extenuating circumstances (like a broken meter), you can contest it online, by mail, or in person. However, being a few minutes late is usually not enough to get it dismissed, unless you have evidence.
If you decide to contest, make sure to provide documentation or photos. For many, it's easier to just pay the fine unless you have a strong case. The city;s website has clear instructions for appeals.",
            "model_name": "groq/llama-3.1-8b-versatile"
          },
          {
            "content": "Ah, the infamous SF parking ticket—almost a rite of passage! If you were only 5 minutes over and don't have a specific reason (like a malfunctioning meter or unclear signs), contesting might be a long shot.
But if you want to try, the process is straightforward: you can appeal online and attach any evidence. Sometimes, persistence pays off! Just don't forget to pay if your appeal doesn;t work.",
            "model_name": "kimi-ai/kimi-dev-72b"
          },
          {
            "content": "In San Francisco, you have the right to contest a parking ticket within 21 days of issuance. For minor overtime, appeals are usually successful only if you can show the ticket was issued in error (such as meter problems or incorrect time on the ticket).
The process involves submitting a request and any evidence through the SFMTA website. If the ticket stands, you still have the option to request a hearing.",
            "model_name": "qwen/qwen3-4b:free"
          },
          {
            "content": "It's frustrating to get a ticket for just a few minutes! You can contest the ticket if you think there's a good reason or if you have proof the meter was wrong. Usually, though, being slightly over the time limit isn't enough for a successful appeal, but it might be worth a try if you have supporting evidence.
The city makes it easy to contest online, and it doesn't hurt to try if you feel it's unfair.",
            "model_name": "mistralai/devstral-small-2505:free"
          }
        ]
      }'
"""

import logging
import sys
from pathlib import Path

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openjury import JuryConfig, OpenJury, ResponseCandidate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

jury = None


def initialize_jury():
    global jury

    config = JuryConfig.from_json_file(f"{Path(__file__).parent}/config.json")

    jury = OpenJury(config)
    logger.info(f"Jury initialized with {len(jury.jurors)} jurors")


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "jury_initialized": jury is not None})


@app.route("/jury/info", methods=["GET"])
def jury_info():
    if not jury:
        return jsonify({"error": "Jury not initialized"}), 500

    summary = jury.get_summary()
    return jsonify(summary)


@app.route("/evaluate", methods=["POST"])
def evaluate_responses():

    if not jury:
        return jsonify({"error": "Jury not initialized"}), 500

    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON body required"}), 400

        if "prompt" not in data:
            return jsonify({"error": "prompt field is required"}), 400

        if "responses" not in data or not isinstance(data["responses"], list):
            return jsonify({"error": "responses field must be a list"}), 400
        try:
            response_candidates = [
                (
                    ResponseCandidate(**r)
                    if isinstance(r, dict)
                    else ResponseCandidate(content=str(r))
                )
                for r in data["responses"]
            ]
        except Exception as e:
            return jsonify({"error": f"Invalid response format: {e}"}), 400
        data["responses"] = response_candidates

        if len(data["responses"]) < 2:
            return jsonify({"error": "At least 2 responses are required"}), 400

        verdict = jury.evaluate(
            prompt=data["prompt"],
            responses=data["responses"],
        )

        if request.args.get("simple"):
            return jsonify(
                {
                    "winner": verdict.final_verdict.winner,
                    "confidence": verdict.final_verdict.confidence,
                }
            )

        response = {
            "winner": verdict.final_verdict.winner,
            "confidence": verdict.final_verdict.confidence,
            "voting_method": verdict.final_verdict.voting_method,
            "voting_details": verdict.final_verdict.voting_details,
            "summary": verdict.summary,
            "individual_verdicts": [
                {
                    "juror_name": jv.juror_name,
                    "juror_weight": jv.juror_weight,
                    "evaluations": [
                        {
                            "response_id": eval.response_id,
                            "total_score": eval.total_score,
                            "criteria_scores": eval.criteria_scores,
                        }
                        for eval in jv.evaluations
                    ],
                }
                for jv in verdict.juror_verdicts
            ],
        }

        return jsonify(response)

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500


def main():
    try:
        logger.info("🔧 Initializing OpenJury for web API...")
        initialize_jury()
        logger.info("✅ Jury initialized successfully!")

        logger.info(
            "\n🌐 Starting web server...\n"
            "Available endpoints:\n"
            "  GET  /health         - Health check\n"
            "  GET  /jury/info      - Jury configuration info\n"
            "  POST /evaluate       - Full evaluation with details (simple=true for simple response)\n"
            "\nExample curl command:\n"
            "curl -X POST http://localhost:5000/evaluate \\\n"
            '  -H "Content-Type: application/json" \\\n'
            '  -d \'{"prompt": "Explain AI", "simple": true, "responses": [{"content": "AI is...", "model_name": "gpt-4o"}, {"content": "Artificial intelligence...", "model_name": "gpt-4o"}]}\''
        )

        app.run(debug=True, host="0.0.0.0", port=5000)

    except Exception as e:
        logger.error(f"❌ Failed to start application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
