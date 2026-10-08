import re
import glob

files = ["frontend/src/app/intel/audio/page.tsx", "frontend/src/app/intel/decision/page.tsx", "frontend/src/app/intel/fact-check/page.tsx"]

for file_path in files:
    with open(file_path, "r") as f:
        content = f.read()

    # Remove the empty ternary
    content = re.sub(r'\s*\{record\.signals\.length \? \(\s*\) : null\}', '', content)

    with open(file_path, "w") as f:
        f.write(content)
