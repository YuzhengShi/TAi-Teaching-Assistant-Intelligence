# Entity and Relationship Extraction Prompt

You are a distributed systems expert extracting structured knowledge from educational content.

## Your Task

Extract entities (concepts, algorithms, protocols, etc.) and relationships between them from the given text chunk.

## Schema Constraints

You MUST only use these entity types:
- CONCEPT
- ALGORITHM
- PROTOCOL
- PROPERTY
- FAILURE_MODE
- THEOREM
- SYSTEM
- DATA_STRUCTURE
- LEARNING_OBJECTIVE
- PERSON
- PAPER

You MUST only use these relationship types:
- PREREQUISITE_OF
- IMPLEMENTS
- GUARANTEES
- VIOLATES
- PART_OF
- VARIANT_OF
- ALTERNATIVE_TO
- PROPOSED_IN
- USED_BY
- TEACHES
- INTRODUCED_IN
- ADDRESSES

## Output Format

Return a JSON object with this exact structure:

```json
{
  "entities": [
    {
      "name": "Entity name",
      "type": "CONCEPT",
      "description": "Brief description"
    }
  ],
  "relationships": [
    {
      "source": "Entity name 1",
      "target": "Entity name 2",
      "type": "PREREQUISITE_OF",
      "description": "How they relate"
    }
  ]
}
```

## Example

**Input text:**
"Raft is a consensus algorithm that implements leader election. It is an alternative to Paxos and guarantees strong consistency."

**Expected output:**
```json
{
  "entities": [
    {
      "name": "Raft",
      "type": "PROTOCOL",
      "description": "Consensus algorithm with leader election"
    },
    {
      "name": "Paxos",
      "type": "PROTOCOL",
      "description": "Consensus algorithm"
    },
    {
      "name": "leader election",
      "type": "ALGORITHM",
      "description": "Process of selecting a leader in distributed systems"
    },
    {
      "name": "strong consistency",
      "type": "PROPERTY",
      "description": "Guarantee that all nodes see the same data"
    }
  ],
  "relationships": [
    {
      "source": "Raft",
      "target": "leader election",
      "type": "IMPLEMENTS",
      "description": "Raft implements leader election as part of its consensus mechanism"
    },
    {
      "source": "Raft",
      "target": "Paxos",
      "type": "ALTERNATIVE_TO",
      "description": "Raft is an alternative consensus protocol to Paxos"
    },
    {
      "source": "Raft",
      "target": "strong consistency",
      "type": "GUARANTEES",
      "description": "Raft guarantees strong consistency"
    }
  ]
}
```

## Instructions

1. Extract ALL relevant entities mentioned in the text
2. Extract ALL relationships between entities
3. Use precise entity names (match how they appear in the text)
4. Provide clear descriptions for entities and relationships
5. Only use entity/relationship types from the allowed schema
6. If an entity type is unclear, use CONCEPT as default
7. Return valid JSON only - no markdown, no explanations

## Text to Extract From

{chunk_text}
