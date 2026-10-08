import re

with open("frontend/src/components/agents/shared/Determination.tsx", "r") as f:
    content = f.read()

# Replace the titleText logic
old_logic = """  const isTrue = ["SUPPORTED", "CONSISTENT", "CLEAR"].includes(verdict.determination);
  const isFalse = ["CONTRADICTED", "CONTESTED", "ANOMALOUS", "SYNTHETIC"].includes(verdict.determination);
  const titleText = isTrue ? "✅ TRUE" : isFalse ? "❌ FALSE" : "⚠️ UNVERIFIED";"""

new_logic = """  const isTrue = ["SUPPORTED", "CONSISTENT", "CLEAR"].includes(verdict.determination);
  const isFalse = ["CONTRADICTED", "CONTESTED", "ANOMALOUS", "SYNTHETIC"].includes(verdict.determination);
  
  let titleText = isTrue ? "✅ TRUE" : isFalse ? "❌ FALSE" : "⚠️ UNVERIFIED";
  
  // If this is an extraction desk (not the final fact-check or decision desk), 
  // REQUIRES VERIFICATION means it successfully extracted claims.
  const isExtractionDesk = !signedBy.includes("decision core") && !signedBy.includes("source desk");
  if (isExtractionDesk) {
    if (verdict.determination === "REQUIRES VERIFICATION") {
      titleText = "✅ EXTRACTION COMPLETE";
    } else if (verdict.determination === "INSUFFICIENT") {
      titleText = "⚠️ NO CLAIMS FOUND";
    }
  }
"""

content = content.replace(old_logic, new_logic)

# Remove the Confidence score if it's an extraction desk AND confidence is 0%
# The user complained about 0% confidence, but on extraction desks it's ALWAYS 0% which is confusing.
# Wait, let's just leave Confidence as is, but maybe change the label to "Extraction Confidence" or something?
# No, let's just hide Confidence if it's an extraction desk because extraction desks don't have a truth confidence.
old_conf = """        <div className="text-lg font-serif-body font-bold text-ink-black">
          Confidence: {verdict.confidence}
        </div>"""

new_conf = """        {!isExtractionDesk && (
          <div className="text-lg font-serif-body font-bold text-ink-black">
            Confidence: {verdict.confidence}
          </div>
        )}"""

content = content.replace(old_conf, new_conf)

with open("frontend/src/components/agents/shared/Determination.tsx", "w") as f:
    f.write(content)
