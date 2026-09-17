import ast 
import os

def extract_functions(source_code: str, file_path: str = "") -> list[dict]:
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    chunks = []
    lines = source_code.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start_line = node.lineno - 1
            end_line = node.end_lineno
            chunk_lines = "\n".join(lines[start_line:end_line])
            docstring = ast.get_docstring(node)

            chunks.append({
                "text": chunk_lines,
                "function_name": node.name,
                "file_path": file_path,
                "language": "python",
                "start_line": node.lineno,
                "end_line": node.end_lineno,
                "docstring": docstring,
            })

    return chunks

def chunk_file(file_path: str) -> list[dict]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source_code = f.read()
    except (IOError, UnicodeDecodeError):
        return[]

    return extract_functions(source_code, file_path)

def chunk_directory(directory_path: str) -> list[dict]:
    
    all_chunks = []

    for root, dirs, files in os.walk(directory_path):
        dirs[:] = [d for d in dirs if d not in {"venv", ".git", "__pycache__", "node_modules", ".venv"}]

        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                chunks = chunk_file(file_path)
                all_chunks.extend(chunks)

    return all_chunks