import re
with open("frontend/src/components/agents/shared/DeskMasthead.tsx", "r") as f:
    content = f.read()

# Make the title span wider since method is gone
content = content.replace('className="lg:col-span-8"', 'className="lg:col-span-12"')
# Remove the method block
content = re.sub(r'<div className="lg:col-span-4 lg:pt-3">\s*<MethodNote desk=\{desk\} />\s*</div>', '', content, flags=re.DOTALL)

with open("frontend/src/components/agents/shared/DeskMasthead.tsx", "w") as f:
    f.write(content)
