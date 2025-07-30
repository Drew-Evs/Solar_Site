import ast
import sys

def get_imports(filepath):
    with open(filepath, "r") as f:
        tree = ast.parse(f.read(), filename=filepath)

    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])

    return sorted(imports)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python list_imports.py <your_file.py>")
    else:
        imports = get_imports(sys.argv[1])
        print("\n".join(imports))
