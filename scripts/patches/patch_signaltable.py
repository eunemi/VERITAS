import re
import glob

files = glob.glob("frontend/src/app/intel/*/page.tsx")

for file_path in files:
    with open(file_path, "r") as f:
        content = f.read()

    # Remove direct <SignalTable ... />
    content = re.sub(r'\s*<SignalTable signals=\{record\.signals\}[^>]*/>', '', content)
    # Remove {record.signals.length ? ( <SignalTable ... /> ) : null}
    content = re.sub(r'\s*\{record\.signals\.length \? \(\s*<SignalTable[^>]*/>\s*\) : null\}', '', content)

    with open(file_path, "w") as f:
        f.write(content)

