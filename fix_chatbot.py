import re

def fix_heuristic(file_path):
    with open(file_path, "r") as f:
        content = f.read()
    
    # Let's fix the substring matching bug
    # Change: any(token in text for token in ('xin chào', ...))
    # To use a helper function or regex
    
