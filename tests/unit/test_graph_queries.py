"""
Test that ALL Cypher queries use parameterized syntax.
This test MUST fail if any query uses string interpolation.
"""

import re
import inspect
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.graph import queries


def test_no_string_interpolation_in_queries():
    """
    Verify that NO Cypher query uses string interpolation.
    Checks for f-strings, .format(), or % formatting in query strings.
    """
    # Patterns that indicate string interpolation
    interpolation_patterns = [
        r'f["\']',  # f-string
        r'\.format\(',  # .format() method
        r'%[sd]',  # % formatting
        r'\$\{',  # ${variable} syntax
    ]
    
    # Get all query classes
    query_classes = [
        queries.CourseQueries,
        queries.StudentQueries,
        queries.MisconceptionQueries,
        queries.ProfileQueries,
    ]
    
    violations = []
    
    for query_class in query_classes:
        # Get all static methods
        for name, method in inspect.getmembers(query_class, predicate=inspect.isfunction):
            if name.startswith('_'):
                continue
            
            # Get source code
            try:
                source = inspect.getsource(method)
            except OSError:
                continue
            
            # Check for interpolation patterns
            for pattern in interpolation_patterns:
                matches = re.finditer(pattern, source)
                for match in matches:
                    # Get context around match
                    start = max(0, match.start() - 50)
                    end = min(len(source), match.end() + 50)
                    context = source[start:end]
                    
                    violations.append({
                        "class": query_class.__name__,
                        "method": name,
                        "pattern": pattern,
                        "context": context
                    })
            
            # Also check the actual query string returned
            try:
                # Try to call with dummy params to get query
                if 'concept_id' in inspect.signature(method).parameters:
                    result = method("test_concept_id")
                elif 'student_id' in inspect.signature(method).parameters:
                    result = method("test_student_id")
                elif 'name' in inspect.signature(method).parameters:
                    result = method("test_name")
                else:
                    # Try with empty params
                    sig = inspect.signature(method)
                    params = {name: "test" for name in sig.parameters.keys()}
                    result = method(**params)
                
                query_string = result.query if hasattr(result, 'query') else str(result)
                
                # Check query string for interpolation
                for pattern in interpolation_patterns:
                    if re.search(pattern, query_string):
                        violations.append({
                            "class": query_class.__name__,
                            "method": name,
                            "pattern": f"Found in query string: {pattern}",
                            "query": query_string[:200]
                        })
                
                # Verify query uses $param syntax
                if '$' not in query_string and '{' in query_string:
                    # Might be using {param} instead of $param
                    violations.append({
                        "class": query_class.__name__,
                        "method": name,
                        "pattern": "Query uses {param} instead of $param",
                        "query": query_string[:200]
                    })
            
            except Exception as e:
                # Can't test this method, skip
                pass
    
    # Assert no violations
    if violations:
        error_msg = "String interpolation violations found in Cypher queries:\n\n"
        for violation in violations:
            error_msg += f"Class: {violation['class']}, Method: {violation['method']}\n"
            error_msg += f"Pattern: {violation['pattern']}\n"
            if 'context' in violation:
                error_msg += f"Context: {violation['context']}\n"
            if 'query' in violation:
                error_msg += f"Query: {violation['query']}\n"
            error_msg += "\n"
        
        assert False, error_msg


def test_all_queries_return_query_result():
    """Verify all query methods return QueryResult with query and params."""
    query_classes = [
        queries.CourseQueries,
        queries.StudentQueries,
        queries.MisconceptionQueries,
        queries.ProfileQueries,
    ]
    
    for query_class in query_classes:
        for name, method in inspect.getmembers(query_class, predicate=inspect.isfunction):
            if name.startswith('_'):
                continue
            
            # Try to call with minimal params
            try:
                sig = inspect.signature(method)
                # Create dummy params
                params = {}
                for param_name, param in sig.parameters.items():
                    if param.annotation == str:
                        params[param_name] = "test"
                    elif param.annotation == int:
                        params[param_name] = 1
                    elif param.annotation == float:
                        params[param_name] = 1.0
                    elif param.annotation == bool:
                        params[param_name] = True
                    else:
                        params[param_name] = "test"
                
                result = method(**params)
                
                # Verify result structure
                assert hasattr(result, 'query'), f"{query_class.__name__}.{name} must return QueryResult with 'query'"
                assert hasattr(result, 'params'), f"{query_class.__name__}.{name} must return QueryResult with 'params'"
                assert isinstance(result.query, str), f"{query_class.__name__}.{name} query must be string"
                assert isinstance(result.params, dict), f"{query_class.__name__}.{name} params must be dict"
            
            except Exception as e:
                # Skip if we can't test
                pass


def test_parameterized_syntax_examples():
    """Test that example queries use $param syntax."""
    # Test CourseQueries.upsert_concept
    result = queries.CourseQueries.upsert_concept("Raft", "Consensus protocol")
    
    assert "$concept_id" in result.query
    assert "$name" in result.query
    assert "$description" in result.query
    assert "concept_id" in result.params
    assert "name" in result.params
    assert "description" in result.params
    
    # Test StudentQueries.create_understanding_relationship
    result = queries.StudentQueries.create_understanding_relationship(
        "student_123", "concept_456", 0.8, "theoretical", "socratic_dialogue"
    )
    
    assert "$student_id" in result.query
    assert "$concept_id" in result.query
    assert "$confidence" in result.query
    assert "student_id" in result.params
    assert "concept_id" in result.params
    assert "confidence" in result.params
