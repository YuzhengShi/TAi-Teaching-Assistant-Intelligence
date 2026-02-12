# Misconception Classification Prompt

You are detecting misconceptions in student statements about distributed systems.

## Your Task

Classify whether a student statement contains a known misconception, identifies a misconception (correctly discussing it), or contains a new candidate misconception.

## Input

- Student statement: {student_statement}
- Topic: {topic}
- Known misconceptions: {known_misconceptions}

## Output Format

Return JSON:

```json
{
  "holds_known_misconception": false,
  "matched_misconception": null,
  "is_identifying_not_holding": false,
  "is_new_candidate": false,
  "new_candidate_description": null,
  "contradicts_concept": null
}
```

## Classification Rules

1. **holds_known_misconception**: Student believes something that matches a known misconception
2. **is_identifying_not_holding**: Student is correctly discussing/identifying a misconception (not holding it)
3. **is_new_candidate**: Student holds a misconception not in the known list
4. **new_candidate_description**: Description of the new misconception
5. **contradicts_concept**: Which concept does this misconception contradict?

## Example

**Student statement**: "Raft guarantees availability during network partitions"

**Known misconceptions**: ["Raft always available during partitions"]

**Output**:
```json
{
  "holds_known_misconception": true,
  "matched_misconception": "Raft always available during partitions",
  "is_identifying_not_holding": false,
  "is_new_candidate": false,
  "new_candidate_description": null,
  "contradicts_concept": "CAP theorem"
}
```

## Instructions

- Distinguish between HOLDING a misconception vs IDENTIFYING/DISCUSSING it
- Only flag new candidates if student is HOLDING the misconception
- Provide specific contradiction information
