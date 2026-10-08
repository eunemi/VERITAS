with open("frontend/src/components/CommissionPanel.tsx", "r") as f:
    content = f.read()

start_str = '{inputType === "text" && ('
end_str = ')}'

start_idx = content.find(start_str)
# Find the matching closing brace. Actually it's simple enough.
content = content.replace(
'''            {inputType === "text" && (
                <>
                  <input 
                    type="file" 
                    ref={fileInputRef} 
                    className="hidden" 
                    accept=".pdf,.docx,.md"
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
                    title="Upload .pdf, .docx, or .md"
                  >
                    [ UPLOAD FILE ]
                  </button>
                </>
              )}''',
'''              <>
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
              </>'''
)

with open("frontend/src/components/CommissionPanel.tsx", "w") as f:
    f.write(content)
