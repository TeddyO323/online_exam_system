import os

# Directory where your Django project resides
BASE_DIR = 'C:/Users/omosh/Projects/examportal'  # adjust if needed
TARGET_IMPORTS = [
    'from core.models import Question',
    'from core.models import Option',
    'from core.models import MatchingPair',
    'from core.models import TrueFalseAnswer',
]

def find_outdated_imports(base_dir):
    print("🔎 Scanning for outdated imports...\n")
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, encoding='utf-8') as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines, start=1):
                        if any(target in line for target in TARGET_IMPORTS):
                            print(f"⚠️  Found outdated import in {path}, line {i}:")
                            print(f"    {line.strip()}\n")

find_outdated_imports(BASE_DIR)
