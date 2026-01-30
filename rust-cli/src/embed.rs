use anyhow::Result;
use serde::{Deserialize, Serialize};

#[derive(Serialize)]
struct EmbedRequest {
    model: String,
    prompt: String,
}

#[derive(Deserialize)]
struct EmbedResponse {
    embedding: Vec<f64>,
}

pub async fn get_embedding(ollama_url: &str, model: &str, text: &str) -> Result<Vec<f64>> {
    let client = reqwest::Client::new();
    let resp = client
        .post(ollama_url)
        .json(&EmbedRequest {
            model: model.to_string(),
            prompt: text.to_string(),
        })
        .send()
        .await?
        .json::<EmbedResponse>()
        .await?;
    Ok(resp.embedding)
}
