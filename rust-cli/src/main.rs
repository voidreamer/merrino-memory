mod chunk;
mod config;
mod embed;
mod index;
mod search;

use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "agent-memory", version, about = "Agent-agnostic vector memory CLI")]
struct Cli {
    /// Path to config.yaml
    #[arg(short, long)]
    config: Option<String>,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Search memories semantically
    Search {
        /// Search query
        query: String,

        /// Number of results
        #[arg(short, long, default_value = "5")]
        top: i64,

        /// Output as JSON
        #[arg(long)]
        json: bool,
    },
    /// Full re-index of all configured sources
    Index,
    /// Incremental index (only new/modified files)
    IndexIncremental,
    /// Show health/stats
    Health,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let cfg = config::Config::load(cli.config.as_deref())?;

    match cli.command {
        Commands::Search { query, top, json } => {
            search::search(&cfg, &query, top, json).await?;
        }
        Commands::Index => {
            println!("🐑⚡ Full index for agent '{}'...\n", cfg.agent_id);
            index::run_full_index(&cfg).await?;
        }
        Commands::IndexIncremental => {
            println!("🐑⚡ Incremental index for agent '{}'...\n", cfg.agent_id);
            index::run_incremental_index(&cfg).await?;
        }
        Commands::Health => {
            health(&cfg).await?;
        }
    }

    Ok(())
}

async fn health(config: &config::Config) -> Result<()> {
    let (client, connection) =
        tokio_postgres::connect(&config.db_url, tokio_postgres::NoTls).await?;
    tokio::spawn(async move {
        if let Err(e) = connection.await {
            eprintln!("DB connection error: {}", e);
        }
    });

    let msgs = client
        .simple_query(&format!(
            "SELECT count(*) FROM {}.chunks WHERE agent_id = '{}'",
            config.schema, config.agent_id
        ))
        .await?;
    let count = if let Some(tokio_postgres::SimpleQueryMessage::Row(row)) = msgs.first() {
        row.get(0).unwrap_or("0")
    } else {
        "0"
    };

    let msgs2 = client
        .simple_query(&format!(
            "SELECT DISTINCT agent_id FROM {}.chunks ORDER BY agent_id",
            config.schema
        ))
        .await?;
    let agents: Vec<String> = msgs2
        .iter()
        .filter_map(|m| {
            if let tokio_postgres::SimpleQueryMessage::Row(row) = m {
                row.get(0).map(|s| s.to_string())
            } else {
                None
            }
        })
        .collect();

    println!("🐑⚡ Agent Memory — Health");
    println!("  Agent:  {}", config.agent_id);
    println!("  Chunks: {}", count);
    println!("  Schema: {}", config.schema);
    println!("  Agents: {}", agents.join(", "));
    println!("  Ollama: {}", config.ollama_url);
    println!("  Model:  {}", config.model);

    Ok(())
}
