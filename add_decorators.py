import os
import re

# Define paths relative to examportal root
admin_views_path = "adminpanel/views.py"
examiner_views_path = "examinerpanel/views.py"

# Role decorators to insert
admin_decorator = "@role_required('ADMIN')"
examiner_decorator = "@role_required('EXAMINER')"

# Function to update a views.py with appropriate decorators
def add_role_decorators(filepath, role_decorator, output_filename):
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    updated_lines = []
    insert_next = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip already decorated lines
        if stripped.startswith('@'):
            updated_lines.append(line)
            continue

        # Detect top-level def statements
        if re.match(r'^def\s+\w+\(.*\):', stripped):
            if i == 0 or not lines[i-1].strip().startswith('@'):
                updated_lines.append(role_decorator + "\n")
        updated_lines.append(line)

    with open(output_filename, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)

    print(f"✅ Updated file written to {output_filename}")

# Run for both admin and examiner
add_role_decorators(admin_views_path, admin_decorator, "views_admin_updated.py")
add_role_decorators(examiner_views_path, examiner_decorator, "views_examiner_updated.py")
