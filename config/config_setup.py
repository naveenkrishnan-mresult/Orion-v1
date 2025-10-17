import json
# Load JSON from a file
def read_json(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
    return data