import re

with open("backend/app/desks/text.py", "r") as f:
    content = f.read()

# Change note
content = content.replace(
    'note="Checkable assertion; passed on for checking."',
    'note="Identified as a factual claim that requires verification."'
)
content = content.replace(
    'note="Not verifiable as stated; passed over."',
    'note="Not verifiable as stated; skipped."'
)

# Remove Named entities and Subject terms from ledger
def replace_ledger(content):
    pattern = r'    if extraction\.entities:.*?    return tuple\(entries\)'
    replacement = '    return tuple(entries)'
    return re.sub(pattern, replacement, content, flags=re.DOTALL)

content = replace_ledger(content)

with open("backend/app/desks/text.py", "w") as f:
    f.write(content)
