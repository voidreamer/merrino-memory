variable "project_name" {
  type    = string
  default = "merrino-memory"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "aws_region" {
  type    = string
  default = "ca-central-1"
}

variable "database_url" {
  type      = string
  sensitive = true
}

variable "embedding_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "embedding_model" {
  type    = string
  default = "text-embedding-3-small"
}
