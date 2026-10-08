with open("frontend/src/components/agents/shared/Determination.tsx", "r") as f:
    content = f.read()

# Remove the conditional rendering for confidence
content = content.replace(
'''        {verdict.confidence !== "0%" && (
          <div className="text-lg font-serif-body font-bold text-ink-black">
            Confidence: {verdict.confidence}
          </div>
        )}''',
'''        <div className="text-lg font-serif-body font-bold text-ink-black">
          Confidence: {verdict.confidence}
        </div>'''
)

with open("frontend/src/components/agents/shared/Determination.tsx", "w") as f:
    f.write(content)
