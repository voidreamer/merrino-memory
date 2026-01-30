use anyhow::Result;
use std::path::Path;
use tokio_postgres::Client;
use uuid::Uuid;

use crate::chunk;
use crate::config::{Config, Source};
use crate::embed::get_embedding;

pub async fn run_full_index(config: &Config) -> Result<()> {
    let (client, connection) = tokio_postgres::connect(&config.db_url, tokio_postgres::NoTls).await?;
    tokio::spawn(async move {
        if let Err(e) = connection.await {
            eprintln!("DB connection error: {}", e);
        }
    });

    let mut total_chunks = 0;

    for source in &config.sources {
        match source.source_type.as_str() {
            "markdown_dir" => {
                let n = index_markdown_dir(&client, config, source).await?;
                total_chunks += n;
            }
            "single_file" => {
                let label = source.source_label.as_deref().unwrap_or("single_file");
                let n = index_markdown_file(&client, config, &source.path, label).await?;
                total_chunks += n;
            }
            "transcript_dir" => {
                let n = index_transcript_dir(&client, config, source).await?;
                total_chunks += n;
            }
            other => {
                eprintln!("  ⚠️  Unknown source type: {}", other);
            }
        }
    }

    println!("\n✅ Indexed {} total chunks for agent '{}'", total_chunks, config.agent_id);
    Ok(())
}

pub async fn run_incremental_index(config: &Config) -> Result<()> {
    let (client, connection) = tokio_postgres::connect(&config.db_url, tokio_postgres::NoTls).await?;
    tokio::spawn(async move {
        if let Err(e) = connection.await {
            eprintln!("DB connection error: {}", e);
        }
    });

    // Get indexed state: source_path -> last indexed timestamp
    let indexed_state = get_indexed_state(&client, config).await?;

    let mut new_files = 0;
    let mut updated_files = 0;
    let mut chunks_added = 0;
    let mut chunks_deleted = 0;

    let all_files = collect_all_files(config);

    for (filepath, source_type, label) in &all_files {
        let path_str = filepath.to_string_lossy().to_string();
        let mtime = std::fs::metadata(filepath)
            .and_then(|m| m.modified())
            .ok();

        if let Some(last_indexed) = indexed_state.get(&path_str) {
            // File was indexed before — check if modified
            if let Some(mtime) = mtime {
                let mtime_secs = mtime
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs() as i64;
                if mtime_secs <= *last_indexed {
                    continue; // Not modified
                }
            } else {
                continue;
            }

            // Modified — delete old chunks and re-index
            let deleted = delete_chunks_for(&client, config, &path_str).await?;
            chunks_deleted += deleted;

            let n = if source_type == "transcript" {
                index_transcript_file(&client, config, filepath).await?
            } else {
                index_markdown_file(&client, config, filepath, label).await?
            };
            chunks_added += n;
            updated_files += 1;
            println!("  ♻️  {}: {} old → {} new chunks", filepath.display(), deleted, n);
        } else {
            // New file
            let n = if source_type == "transcript" {
                index_transcript_file(&client, config, filepath).await?
            } else {
                index_markdown_file(&client, config, filepath, label).await?
            };
            if n > 0 {
                chunks_added += n;
                new_files += 1;
                println!("  ✨ {}: {} chunks", filepath.display(), n);
            }
        }
    }

    if new_files == 0 && updated_files == 0 {
        println!("Nothing new to index.");
    } else {
        println!(
            "\n✅ {} new, {} updated | +{} chunks, -{} old",
            new_files, updated_files, chunks_added, chunks_deleted
        );
    }

    Ok(())
}

// --- Helpers ---

async fn index_markdown_dir(client: &Client, config: &Config, source: &Source) -> Result<usize> {
    let dir = &source.path;
    if !dir.exists() {
        eprintln!("  ⚠️  Directory not found: {}", dir.display());
        return Ok(0);
    }

    let label = source.source_label.as_deref().unwrap_or("daily_note");
    let mut total = 0;

    let mut entries: Vec<_> = std::fs::read_dir(dir)?
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map_or(false, |ext| ext == "md"))
        .collect();
    entries.sort_by_key(|e| e.path());

    for entry in entries {
        let n = index_markdown_file(client, config, &entry.path(), label).await?;
        println!("  {}: {} chunks", entry.file_name().to_string_lossy(), n);
        total += n;
    }
    Ok(total)
}

async fn index_markdown_file(
    client: &Client,
    config: &Config,
    filepath: &Path,
    source_label: &str,
) -> Result<usize> {
    let text = std::fs::read_to_string(filepath)?;
    if text.len() < 30 {
        return Ok(0);
    }

    let chunks = chunk::chunk_text(&text, 800);
    let source_date = chunk::extract_date(&filepath.file_name().unwrap_or_default().to_string_lossy());
    let path_str = filepath.to_string_lossy().to_string();
    let mut count = 0;

    for c in &chunks {
        let embedding = get_embedding(&config.ollama_url, &config.model, c).await?;
        let embedding_str = format!(
            "[{}]",
            embedding.iter().map(|v| v.to_string()).collect::<Vec<_>>().join(",")
        );
        let date_clause = match &source_date {
            Some(d) => format!("'{}'", d),
            None => "NULL".to_string(),
        };

        let sql = format!(
            "INSERT INTO {}.chunks (id, content, source, source_path, source_date, agent_id, embedding)
             VALUES ('{}', $escape${}$escape$, '{}', '{}', {}, '{}', '{}'::vector)",
            config.schema,
            Uuid::new_v4(),
            c,
            source_label,
            path_str,
            date_clause,
            config.agent_id,
            embedding_str,
        );
        client.simple_query(&sql).await?;
        count += 1;
    }

    Ok(count)
}

async fn index_transcript_dir(client: &Client, config: &Config, source: &Source) -> Result<usize> {
    let dir = &source.path;
    if !dir.exists() {
        eprintln!("  ⚠️  Directory not found: {}", dir.display());
        return Ok(0);
    }

    let mut total = 0;
    let mut entries: Vec<_> = std::fs::read_dir(dir)?
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map_or(false, |ext| ext == "jsonl"))
        .collect();
    entries.sort_by_key(|e| e.path());

    for entry in entries {
        let n = index_transcript_file(client, config, &entry.path()).await?;
        println!("  {}: {} chunks", entry.file_name().to_string_lossy(), n);
        total += n;
    }
    Ok(total)
}

async fn index_transcript_file(client: &Client, config: &Config, filepath: &Path) -> Result<usize> {
    let text = std::fs::read_to_string(filepath)?;
    let chunks = chunk::parse_transcript(&text);
    let source_date = chunk::extract_date(&filepath.file_stem().unwrap_or_default().to_string_lossy());
    let path_str = filepath.to_string_lossy().to_string();
    let mut count = 0;

    for c in &chunks {
        let embedding = get_embedding(&config.ollama_url, &config.model, c).await?;
        let embedding_str = format!(
            "[{}]",
            embedding.iter().map(|v| v.to_string()).collect::<Vec<_>>().join(",")
        );
        let date_clause = match &source_date {
            Some(d) => format!("'{}'", d),
            None => "NULL".to_string(),
        };

        let sql = format!(
            "INSERT INTO {}.chunks (id, content, source, source_path, source_date, agent_id, embedding)
             VALUES ('{}', $escape${}$escape$, 'transcript', '{}', {}, '{}', '{}'::vector)",
            config.schema,
            Uuid::new_v4(),
            c,
            path_str,
            date_clause,
            config.agent_id,
            embedding_str,
        );
        client.simple_query(&sql).await?;
        count += 1;
    }

    Ok(count)
}

async fn get_indexed_state(client: &Client, config: &Config) -> Result<std::collections::HashMap<String, i64>> {
    let sql = format!(
        "SELECT source_path, EXTRACT(EPOCH FROM MAX(created_at))::bigint
         FROM {}.chunks WHERE agent_id = '{}' GROUP BY source_path",
        config.schema, config.agent_id
    );
    let msgs = client.simple_query(&sql).await?;
    let mut state = std::collections::HashMap::new();

    for msg in &msgs {
        if let tokio_postgres::SimpleQueryMessage::Row(row) = msg {
            if let (Some(path), Some(ts)) = (row.get(0), row.get(1)) {
                if let Ok(ts) = ts.parse::<i64>() {
                    state.insert(path.to_string(), ts);
                }
            }
        }
    }
    Ok(state)
}

async fn delete_chunks_for(client: &Client, config: &Config, source_path: &str) -> Result<usize> {
    let sql = format!(
        "DELETE FROM {}.chunks WHERE source_path = '{}' AND agent_id = '{}'",
        config.schema, source_path, config.agent_id
    );
    let msgs = client.simple_query(&sql).await?;
    // Count CommandComplete messages
    for msg in &msgs {
        if let tokio_postgres::SimpleQueryMessage::CommandComplete(n) = msg {
            return Ok(*n as usize);
        }
    }
    Ok(0)
}

fn collect_all_files(config: &Config) -> Vec<(std::path::PathBuf, String, String)> {
    let mut files = Vec::new();

    for source in &config.sources {
        match source.source_type.as_str() {
            "single_file" => {
                if source.path.exists() {
                    let label = source.source_label.as_deref().unwrap_or("single_file");
                    files.push((source.path.clone(), "markdown".to_string(), label.to_string()));
                }
            }
            "markdown_dir" => {
                if let Ok(entries) = std::fs::read_dir(&source.path) {
                    let label = source.source_label.as_deref().unwrap_or("daily_note");
                    for entry in entries.flatten() {
                        if entry.path().extension().map_or(false, |e| e == "md") {
                            files.push((entry.path(), "markdown".to_string(), label.to_string()));
                        }
                    }
                }
            }
            "transcript_dir" => {
                if let Ok(entries) = std::fs::read_dir(&source.path) {
                    for entry in entries.flatten() {
                        if entry.path().extension().map_or(false, |e| e == "jsonl") {
                            files.push((entry.path(), "transcript".to_string(), "transcript".to_string()));
                        }
                    }
                }
            }
            _ => {}
        }
    }
    files
}
