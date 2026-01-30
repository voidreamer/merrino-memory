use anyhow::Result;
use serde::Deserialize;
use std::path::PathBuf;

#[derive(Debug, Deserialize)]
pub struct Config {
    pub agent_id: String,
    pub db_url: String,
    #[serde(default = "default_ollama_url")]
    pub ollama_url: String,
    #[serde(default = "default_model")]
    pub model: String,
    #[serde(default = "default_schema")]
    pub schema: String,
    #[serde(default)]
    pub sources: Vec<Source>,
}

#[derive(Debug, Deserialize)]
pub struct Source {
    pub path: PathBuf,
    #[serde(rename = "type")]
    pub source_type: String,
    pub source_label: Option<String>,
}

fn default_ollama_url() -> String {
    "http://localhost:11434/api/embeddings".to_string()
}

fn default_model() -> String {
    "nomic-embed-text".to_string()
}

fn default_schema() -> String {
    "agent_memory".to_string()
}

impl Config {
    pub fn load(path: Option<&str>) -> Result<Self> {
        let config_path = if let Some(p) = path {
            PathBuf::from(p)
        } else if let Ok(p) = std::env::var("AGENT_MEMORY_CONFIG") {
            PathBuf::from(p)
        } else {
            PathBuf::from("config.yaml")
        };

        let contents = std::fs::read_to_string(&config_path)
            .map_err(|e| anyhow::anyhow!("Cannot read config at {}: {}", config_path.display(), e))?;
        let config: Config = serde_yaml::from_str(&contents)?;
        Ok(config)
    }
}
