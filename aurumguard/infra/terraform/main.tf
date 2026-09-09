# Infrastructure-as-code skeleton (provider-agnostic module layout).
# The MVP runs on docker-compose; this skeleton documents the intended production shape:
#   - managed PostgreSQL (TimescaleDB extension optional), managed Redis
#   - two container services (api, web) behind an HTTPS load balancer
#   - object storage bucket for reports/model artefacts (versioned, private)
#   - secrets in the platform secret manager (never in tfvars committed to git)
# Fill in the provider block for the chosen cloud before use.
terraform {
  required_version = ">= 1.6"
}

variable "environment" {
  description = "development | staging | paper | production"
  type        = string
}

variable "region" {
  type = string
}

locals {
  name = "aurumguard-${var.environment}"
  tags = { project = "aurumguard", environment = var.environment, managed_by = "terraform" }
}

# module "network"   { source = "./modules/network"   name = local.name tags = local.tags }
# module "database"  { source = "./modules/postgres"  name = local.name tags = local.tags }
# module "cache"     { source = "./modules/redis"     name = local.name tags = local.tags }
# module "storage"   { source = "./modules/bucket"    name = local.name tags = local.tags versioning = true }
# module "api"       { source = "./modules/service"   name = "${local.name}-api" image = var.api_image  env = var.environment }
# module "web"       { source = "./modules/service"   name = "${local.name}-web" image = var.web_image  env = var.environment }

output "environment" { value = var.environment }
