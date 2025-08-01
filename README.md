# OpenJury 🏛️

**A Python SDK for evaluating and comparing multiple model outputs using configurable LLM-based jurors.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

---

## Overview

**OpenJury** is a post-inference ensemble framework that evaluates and compares multiple model outputs using configurable LLM-based jurors. It enables structured model assessment, ranking, and A/B testing directly into your Python apps, research workflows, or ML platforms.

At its core, OpenJury is a decision-level, LLM-driven evaluation system that aggregates juror scores using flexibile voting strategies (e.g. weighted, ranked, consensus, etc.). This makes it a powerful and extensible solution for nuanced, after-inference comparison of generated outputs across models, prompts, versions, or datasets.

### Why use an LLM Jury?

AI models can generate fluent, convincing outputs, but fluency != correctness. Whether you're building a customer service agent, a code review assist, or a content generator, you need to know which response is best, correct, or how models compare with quality and consistency. Human evaluation doesn't scale, which is why LLM-based jurors are widely used.

But relying on a single LLM (like GPT-4o) to evaluate model outputs, although common, is expensive and can introduce [intra-model bias](https://arxiv.org/abs/2404.13076). Research by Cohere [shows](https://arxiv.org/abs/2404.18796) that using a panel of smaller, diverse models not only cuts cost but also leads to more reliable and less biased evaluations.

OpenJury puts this into practice: instead of a single judge, it uses multiple jurors to score and explain outputs. The result? Better evlautions and lower costs, all configurable with a declarative interface.


---

## Key Features

- **Python SDK:** Simple integration, flexible configuration
- **Multi-Criteria Evaluation:** Define custom criteria with weights and scoring
- **Advanced Voting Methods:** Majority, average, weighted, ranked, consensus, or your own
- **Parallel Processing:** Evaluate at scale, concurrently
- **Rich Output:** Scores, explanations, voting breakdowns, and confidence metrics
- **Extensible:** Plug in your own jurors, voting logic, and evaluation strategies
- **Dev Experience:** One-command setup, Makefile workflow, and modern code quality tools

---

## Installation

**Requirements:** Python 3.11 or newer

### Recommended (PyPI)

```bash
pip install openjury
```

### From Source (for development/contribution)

```bash
git clone https://github.com/robiscoding/openjury.git
cd openjury
pip install -e .
uv pip install -e ".[dev]"     # (optional) dev dependencies
```

## Quick Start

### Set Environment Variables

```bash
export OPENROUTER_API_KEY="your-api-key"
```

or if you're using OpenAI:
```bash
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="your-api-key"
```

### Basic Usage

```python
from openjury import OpenJury, JuryConfig

config = JuryConfig.from_json_file("jury_config.json")
jury = OpenJury(config)
verdict = jury.evaluate(
    prompt="Write a Python function to reverse a string",
    responses=[
        "def reverse(s): return s[::-1]",
        "def reverse(s): return ''.join(reversed(s))"
    ]
)

print(f"Winner: {verdict.final_verdict.winner}")
print(f"Confidence: {verdict.final_verdict.confidence:.2%}")
```

### Configuration Example (jury_config.json)

```json
{
  "name": "Code Quality Jury",
  "criteria": [
    {"name": "correctness", "weight": 2.0, "max_score": 5},
    {"name": "readability", "weight": 1.5, "max_score": 5}
  ],
  "jurors": [
    {"name": "Senior Developer", "system_prompt": "You are a senior developer. You are tasked with reviewing the code and providing a score and explanation for the correctness and readability of the code.", "model_name": "qwen/qwen-2.5-coder-32b", "weight": 2.0},
    {"name": "Code Reviewer", "system_prompt": "You are a code reviewer. You are tasked with reviewing the code and providing a score and explanation for the correctness and readability of the code.", "model_name": "llama3/llama-3.1-8b-instruct", "weight": 1.0}
  ],
  "voting_method": "weighted"
}
```

### Examples

You can find more examples in the [examples](examples) directory.

### Use Cases

#### Model Evaluation & Comparison
- Compare outputs from different models (e.g., GPT-4 vs Claude vs custom models)
- Run A/B tests across prompt variations, fine-tuned models, or versions

#### Content & Response Quality
- Evaluate generated code for correctness and readability
- Score long-form content (blogs, papers, explanations) for clarity, tone, or coherence

#### Automated Grading & Assessment
- Grade student answers or interview responses at scale
- Score generated outputs against rubric-style criteria

#### Production Monitoring & QA
- Monitor output quality in production systems
- Detect degradation or drift between model versions

#### Custom Evaluation Workflows
- Integrate LLM-based judgment into human-in-the-loop pipelines
- Use configurable jurors and voting for domain-specific tasks

---

## License

OpenJury is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

---

## Contributing

Contributions are welcome! Please see the [CONTRIBUTING.md](CONTRIBUTING.md) file for details.