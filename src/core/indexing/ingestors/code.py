"""
Ingestor for code solution repositories (Go/Python).
Extracts function signatures, docstrings, and comments.
"""

from pathlib import Path
from typing import List
import ast
import re

from src.core.indexing.ingestors.base import BaseIngestor, DocumentChunk


class CodeIngestor(BaseIngestor):
    """Ingest code files with AST parsing."""
    
    def can_ingest(self, path: Path) -> bool:
        """Check if file is Go or Python."""
        suffix = path.suffix.lower()
        return suffix in ['.go', '.py', '.pyx']
    
    def ingest(self, path: Path) -> List[DocumentChunk]:
        """Ingest code file."""
        suffix = path.suffix.lower()
        
        if suffix == '.go':
            return self._ingest_go(path)
        elif suffix == '.py':
            return self._ingest_python(path)
        else:
            raise ValueError(f"Unsupported code format: {suffix}")
    
    def _ingest_go(self, path: Path) -> List[DocumentChunk]:
        """Ingest Go code file."""
        chunks = []
        
        try:
            code = path.read_text(encoding='utf-8')
            source_name = path.stem
            
            # Extract function signatures
            func_pattern = r'func\s+(\w+)\s*\([^)]*\)\s*(?:\([^)]*\))?\s*(?:\{[^}]*\})?'
            functions = re.finditer(func_pattern, code, re.MULTILINE)
            
            # Extract struct definitions
            struct_pattern = r'type\s+(\w+)\s+struct\s*\{[^}]*\}'
            structs = re.finditer(struct_pattern, code, re.MULTILINE | re.DOTALL)
            
            # Extract comments and docstrings
            comment_pattern = r'//\s*(.+?)(?=\n|$)'
            comments = re.finditer(comment_pattern, code, re.MULTILINE)
            
            # Create chunks for functions
            for func_match in functions:
                func_name = func_match.group(1)
                func_text = func_match.group(0)
                
                # Find associated comments before function
                func_start = func_match.start()
                preceding_text = code[max(0, func_start - 500):func_start]
                doc_comment = self._extract_preceding_comment(preceding_text)
                
                chunk_text = f"{doc_comment}\n\n{func_text}" if doc_comment else func_text
                
                chunk = self._create_chunk(
                    text=chunk_text,
                    source_type="code_solution",
                    source_name=source_name,
                    language="go",
                    element_type="function",
                    element_name=func_name
                )
                chunks.append(chunk)
            
            # Create chunks for structs
            for struct_match in structs:
                struct_name = struct_match.group(1)
                struct_text = struct_match.group(0)
                
                chunk = self._create_chunk(
                    text=struct_text,
                    source_type="code_solution",
                    source_name=source_name,
                    language="go",
                    element_type="struct",
                    element_name=struct_name
                )
                chunks.append(chunk)
            
            # If no functions/structs found, create a general chunk
            if not chunks:
                # Extract top-level comments
                top_comments = []
                for comment_match in list(comments)[:10]:  # First 10 comments
                    top_comments.append(comment_match.group(1))
                
                if top_comments:
                    chunk_text = "// " + "\n// ".join(top_comments)
                    chunk = self._create_chunk(
                        text=chunk_text,
                        source_type="code_solution",
                        source_name=source_name,
                        language="go",
                        element_type="comments"
                    )
                    chunks.append(chunk)
        
        except Exception as e:
            raise ValueError(f"Failed to ingest Go code {path}: {str(e)}") from e
        
        return chunks
    
    def _ingest_python(self, path: Path) -> List[DocumentChunk]:
        """Ingest Python code file using AST."""
        chunks = []
        
        try:
            code = path.read_text(encoding='utf-8')
            source_name = path.stem
            
            # Parse AST
            tree = ast.parse(code)
            
            # Extract functions and classes
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Get function signature
                    func_name = node.name
                    args = [arg.arg for arg in node.args.args]
                    signature = f"def {func_name}({', '.join(args)})"
                    
                    # Get docstring
                    docstring = ast.get_docstring(node) or ""
                    
                    # Get function body (first few lines)
                    body_lines = []
                    for stmt in node.body[:5]:  # First 5 statements
                        body_lines.append(ast.unparse(stmt))
                    
                    chunk_text = f"{signature}\n\n{docstring}\n\n" + "\n".join(body_lines)
                    
                    chunk = self._create_chunk(
                        text=chunk_text,
                        source_type="code_solution",
                        source_name=source_name,
                        language="python",
                        element_type="function",
                        element_name=func_name
                    )
                    chunks.append(chunk)
                
                elif isinstance(node, ast.ClassDef):
                    # Get class definition
                    class_name = node.name
                    docstring = ast.get_docstring(node) or ""
                    
                    # Get class methods
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    
                    chunk_text = f"class {class_name}:\n\n{docstring}\n\nMethods: {', '.join(methods)}"
                    
                    chunk = self._create_chunk(
                        text=chunk_text,
                        source_type="code_solution",
                        source_name=source_name,
                        language="python",
                        element_type="class",
                        element_name=class_name
                    )
                    chunks.append(chunk)
            
            # If no functions/classes, create general chunk
            if not chunks:
                # Extract module-level docstring
                docstring = ast.get_docstring(tree) or ""
                if docstring:
                    chunk = self._create_chunk(
                        text=docstring,
                        source_type="code_solution",
                        source_name=source_name,
                        language="python",
                        element_type="module"
                    )
                    chunks.append(chunk)
        
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax in {path}: {str(e)}") from e
        except Exception as e:
            raise ValueError(f"Failed to ingest Python code {path}: {str(e)}") from e
        
        return chunks
    
    def _extract_preceding_comment(self, text: str) -> str:
        """Extract comment immediately preceding a function."""
        # Look for comment patterns
        comment_pattern = r'//\s*(.+?)(?=\n|$)'
        comments = re.findall(comment_pattern, text)
        if comments:
            return "// " + "\n// ".join(comments[-3:])  # Last 3 comments
        return ""
