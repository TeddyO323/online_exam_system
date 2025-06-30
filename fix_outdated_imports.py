import os

BASE_DIR = 'C:/Users/omosh/Projects/examportal'  # Adjust if needed

# Mapping of old -> new imports
REPLACEMENTS = {
    'from core.models import Question': 'from core.models import Question',
    'from core.models import Option': 'from core.models import Option',
    'from core.models import MatchingPair': 'from core.models import MatchingPair',
    'from core.models import TrueFalseAnswer': 'from core.models import TrueFalseAnswer',
}

def fix_imports(base_dir):
    print("🔧 Auto-replacing outdated imports...\n")
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()

                original_content = content
                for old, new in REPLACEMENTS.items():
                    content = content.replace(old, new)

                if content != original_content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"✅ Updated imports in: {path}")

fix_imports(BASE_DIR)
