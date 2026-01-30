/// Text chunking logic — splits markdown and transcripts into embeddable pieces.

pub fn chunk_text(text: &str, max_chars: usize) -> Vec<String> {
    let paragraphs: Vec<&str> = text.split("\n\n").collect();
    let mut chunks: Vec<String> = Vec::new();
    let mut current = String::new();

    for para in paragraphs {
        let para = para.trim();
        if para.is_empty() {
            continue;
        }
        if !current.is_empty() && current.len() + para.len() + 2 > max_chars {
            chunks.push(current.trim().to_string());
            current = para.to_string();
        } else {
            if !current.is_empty() {
                current.push_str("\n\n");
            }
            current.push_str(para);
        }
    }

    if !current.trim().is_empty() {
        chunks.push(current.trim().to_string());
    }

    // Skip tiny chunks
    chunks.into_iter().filter(|c| c.len() > 20).collect()
}

/// Extract date from a filename like "2026-01-30.md"
pub fn extract_date(filename: &str) -> Option<String> {
    let re = regex::Regex::new(r"(\d{4}-\d{2}-\d{2})").ok()?;
    re.captures(filename).map(|c| c[1].to_string())
}

/// Parse JSONL transcript into conversation chunks.
/// Handles two formats:
///   {"role": "user", "content": "..."}
///   {"type": "message", "message": {"role": "...", "content": [{"type":"text","text":"..."}]}}
pub fn parse_transcript(text: &str) -> Vec<String> {
    let mut messages: Vec<String> = Vec::new();

    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Ok(entry) = serde_json::from_str::<serde_json::Value>(line) else {
            continue;
        };

        let (role, content) = if entry.get("type").and_then(|t| t.as_str()) == Some("message") {
            // Nested format
            let msg = entry.get("message").unwrap_or(&entry);
            let role = msg.get("role").and_then(|r| r.as_str()).unwrap_or("");
            let content = match msg.get("content") {
                Some(serde_json::Value::String(s)) => s.clone(),
                Some(serde_json::Value::Array(arr)) => arr
                    .iter()
                    .filter_map(|c| {
                        if c.get("type").and_then(|t| t.as_str()) == Some("text") {
                            c.get("text").and_then(|t| t.as_str()).map(|s| s.to_string())
                        } else {
                            None
                        }
                    })
                    .collect::<Vec<_>>()
                    .join(" "),
                _ => String::new(),
            };
            (role.to_string(), content)
        } else {
            // Simple format
            let role = entry.get("role").and_then(|r| r.as_str()).unwrap_or("");
            let content = match entry.get("content") {
                Some(serde_json::Value::String(s)) => s.clone(),
                Some(serde_json::Value::Array(arr)) => arr
                    .iter()
                    .filter_map(|c| {
                        if c.get("type").and_then(|t| t.as_str()) == Some("text") {
                            c.get("text").and_then(|t| t.as_str()).map(|s| s.to_string())
                        } else {
                            None
                        }
                    })
                    .collect::<Vec<_>>()
                    .join(" "),
                _ => String::new(),
            };
            (role.to_string(), content)
        };

        if (role == "user" || role == "assistant") && content.len() > 20 {
            messages.push(format!("[{}] {}", role, content));
        }
    }

    if messages.is_empty() {
        return Vec::new();
    }

    let full_text = messages.join("\n\n");
    chunk_text(&full_text, 1000)
}
