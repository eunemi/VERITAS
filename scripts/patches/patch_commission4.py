import re

with open("frontend/src/components/CommissionPanel.tsx", "r") as f:
    content = f.read()

# Fix the routing payload
content = content.replace(
'''      const payload = inputType === "text" 
        ? { kind: "text" as const, content: text }
        : inputType === "video" 
          ? { kind: "audio" as const, url: text } // route video to audio
          : { kind: inputType, url: text };''',
'''      const payload = inputType === "text" 
        ? { kind: "text" as const, content: text }
        : { kind: inputType, url: text };'''
)

# Remove the visual analysis coming soon notices
content = re.sub(r'\{inputType === "video" && \(\s*<div className="bg-gold-foil/20 p-4 font-serif-body text-sm italic">\s*Notice: Visual content analysis is coming soon[^<]*</div>\s*\)\}', '', content, flags=re.DOTALL)

content = re.sub(r'\{inputType === "video" && \(\s*<div className="bg-gold-foil/20 p-3 font-serif-body text-sm italic">\s*Note: This result is based on audio track analysis only.[^<]*</div>\s*\)\}', '', content, flags=re.DOTALL)

with open("frontend/src/components/CommissionPanel.tsx", "w") as f:
    f.write(content)
