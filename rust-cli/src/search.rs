use anyhow::Result;
use serde::Serialize;
use tokio_postgres::NoTls;

use crate::config::Config;
use crate::embed::get_embedding;

#[derive(Debug, Serialize)]
pub struct SearchResult {
    pub content: String,
    pub source: String,
    pub source_path: Option<String>,
    pub source_date: Option<String>,
    pub similarity: f64,
}

pub async fn search(config: &Config, query: &str, top_k: i64, json_output: bool) -> Result<()> {
    let embedding = get_embedding(&config.ollama_url, &config.model, query).await?;
    let embedding_str = format!(
        "[{}]",
        embedding
            .iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",")
    );

    let (client, connection) = tokio_postgres::connect(&config.db_url, NoTls).await?;
    tokio::spawn(async move {
        if let Err(e) = connection.await {
            eprintln!("DB connection error: {}", e);
        }
    });

    // Use simple_query to avoid prepared statement issues with Supabase pooler
    let query_sql = format!(
        "SELECT content, source, source_path, source_date::text,
                1 - (embedding <=> '{}'::vector) as similarity
         FROM {}.chunks
         WHERE agent_id = '{}'
         ORDER BY embedding <=> '{}'::vector
         LIMIT {}",
        embedding_str, config.schema, config.agent_id, embedding_str, top_k
    );

    let messages = client.simple_query(&query_sql).await?;

    let mut results: Vec<SearchResult> = Vec::new();
    for msg in &messages {
        if let tokio_postgres::SimpleQueryMessage::Row(row) = msg {
            let similarity: f64 = row.get(4).unwrap_or("0").parse().unwrap_or(0.0);
            results.push(SearchResult {
                content: row.get(0).unwrap_or("").to_string(),
                source: row.get(1).unwrap_or("").to_string(),
                source_path: row.get(2).map(|s| s.to_string()),
                source_date: row.get(3).map(|s| s.to_string()),
                similarity,
            });
        }
    }

    if json_output {
        println!("{}", serde_json::to_string_pretty(&results)?);
    } else {
        println!("🔍 Query: \"{}\" (top {})\n", query, top_k);
        for (i, r) in results.iter().enumerate() {
            println!(
                "--- [{}] sim={:.4} | {} | {} ---",
                i + 1,
                r.similarity,
                r.source,
                r.source_date.as_deref().unwrap_or("n/a")
            );
            let display: String = r.content.chars().take(500).collect();
            println!("{}\n", display);
        }
    }

    Ok(())
}
