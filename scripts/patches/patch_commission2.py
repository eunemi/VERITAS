import re

with open("frontend/src/components/CommissionPanel.tsx", "r") as f:
    content = f.read()

# Replace the specific block
pattern = r'\{inputType === "text" && \(\s*<>\s*<input[^>]+>\s*<button.*?</button>\s*</>\s*\)\}'

new_upload_btn = """              <>
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  className="hidden" 
                  accept={inputType === "text" ? ".pdf,.docx,.md" : inputType === "image" ? "image/*" : inputType === "audio" ? "audio/*" : "video/*"}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileUpload(file);
                  }}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isExtracting}
                  className="absolute bottom-4 right-4 z-20 font-mono-label text-xs uppercase tracking-wider text-ink-black/50 hover:text-ink-black transition-colors disabled:opacity-50"
                  title={`Upload ${inputType} file`}
                >
                  [ UPLOAD FILE ]
                </button>
              </>"""

content = re.sub(pattern, new_upload_btn, content, flags=re.DOTALL)

with open("frontend/src/components/CommissionPanel.tsx", "w") as f:
    f.write(content)
