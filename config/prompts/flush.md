# Memory Flush Prompt

You are extracting structured learning events from a teaching conversation that is about to be compacted.

## Your Task

Extract durable learning information that should be preserved in the student's knowledge graph before the conversation is summarized.

## Output Format

Return a JSON object with this structure:

```json
{
  "learning_events": [
    {
      "concept_name": "Raft leader election",
      "event_type": "MASTERED",
      "confidence": 0.8,
      "evidence_type": "socratic_dialogue",
      "context_scope": "theoretical",
      "evidence": {
        "text": "Student correctly explained how Raft elects leaders",
        "message_index": 15
      }
    }
  ]
}
```

## Event Types

- `MASTERED`: Student demonstrated understanding
- `STRUGGLING`: Student showed confusion or difficulty
- `REVIEWED`: Student reviewed previously learned concept
- `CONNECTION`: Student made connection between concepts

## Evidence Types

- `socratic_dialogue`: Through question-answer exchange
- `code_review`: Through code explanation or debugging
- `mock_interview`: Through verbal explanation
- `written_explanation`: Through written response

## Context Scopes

- `theoretical`: Understanding of concepts/principles
- `implementation`: Understanding of code/implementation
- `debugging`: Understanding through problem-solving
- `verbal`: Understanding demonstrated verbally

## Instructions

1. Extract ALL learning events from the conversation
2. Only extract events with confidence >= 0.5
3. Provide specific evidence (quote or description)
4. If no significant learning events, return empty array
5. Return valid JSON only

## Conversation to Extract From

{conversation_text}
