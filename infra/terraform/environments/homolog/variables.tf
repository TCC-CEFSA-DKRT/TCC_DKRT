variable "region" {
  description = "Regiao AWS -- conta real (ADR-0018), sem restricao de regiao imposta pelo Academy Learner Lab (que este ambiente nao usa mais)."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "auditor-homolog"
}

variable "key_name" {
  description = "Key pair EC2 já existente na conta Academy para SSH (opcional)."
  type        = string
  default     = null
}

variable "ollama_model" {
  description = "Deve espelhar OLLAMA_MODEL em .env / Settings.ollama_model. Decisão do usuário: um SLM pequeno (Qwen 2.5 3B/4B ou equivalente) -- ver docs/decisions/0001-ollama-ec2-vs-bedrock.md."
  type        = string
  default     = "qwen2.5:3b-instruct"
}

variable "provision_ollama" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = { Project = "auditor-tcc", Environment = "homolog" }
}
