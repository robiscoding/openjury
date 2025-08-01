# Custom Voting Methods Example

This example demonstrates how to implement and use custom voting algorithms with OpenJury.

## Overview

Custom voting methods allow you to implement specialized decision-making logic beyond the built-in voting methods (majority, average, weighted, ranked, consensus). This is useful when you need:

- Domain-specific scoring logic
- Specialized confidence calculations
- Custom aggregation strategies
- Business rule enforcement

## How It Works

### 1. Define Custom Voting Methods

Create a class with static methods that implement your custom voting logic:

```python
from openjury.voting import VotingResult, VotingMethod

class CustomVotingMethods:
    @staticmethod
    def unanimous_priority(evaluations: List[JurorEvaluation]) -> VotingResult:
        # Your custom logic here
        return VotingResult(
            winner="response_1",
            method=VotingMethod.CUSTOM,
            custom_scores={"response_1": 10.0, "response_2": 5.0},
            custom_data={"confidence": 0.95, "unanimous": True}
        )
```

### 2. Configure Your Jury

Set the voting method to "custom" and specify which function to use:

```json
{
  "voting_method": "custom",
  "custom_voting_function": "unanimous_priority",
  "criteria": [...],
  "jurors": [...]
}
```

### 3. Load Configuration with Custom Class

Pass your custom voting class when loading the configuration:

```python
config = JuryConfig.from_json_file("config.json", CustomVotingMethods)
jury = OpenJury(config)
```

## Requirements

Custom voting methods must:

1. **Accept parameter**: `List[JurorEvaluation]`
2. **Return**: `VotingResult` object
3. **Be static methods** in a class
4. **Set method**: `VotingMethod.CUSTOM` in the result

## Example Methods

### unanimous_priority
Heavily weights unanimous decisions. If all jurors agree on the winner, confidence is boosted to 95%.

### confidence_weighted  
Considers how confident each juror seems based on score spread. Jurors with higher variance in scores are weighted more.

### margin_of_victory
Uses the margin between first and second place to calculate confidence. Larger margins result in higher confidence.

## Running the Example

```bash
export OPENROUTER_API_KEY="your-key-here"
python examples/custom_voting_method/custom_voting.py
```

This will test all three custom voting methods and compare their results.

## Custom Data

Use the `custom_data` field in `VotingResult` to store method-specific information:

```python
return VotingResult(
    winner="response_1",
    method=VotingMethod.CUSTOM,
    custom_scores=scores,
    custom_data={
        "confidence": 0.85,
        "method_name": "my_method",
        "additional_info": "..."
    }
)
```

This data will be available in the final verdict for analysis and debugging.