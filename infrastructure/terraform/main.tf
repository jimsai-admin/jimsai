terraform {
  required_version = ">= 1.6.0"
}

variable "project_name" {
  type    = string
  default = "jims-ai"
}

output "next_steps" {
  value = "Wire managed Redis, Neo4j Aura, Supabase, Cloudflare R2, and Vectorize providers for the target cloud account."
}
