# Reuse existing EKS, AKS, and GKE GPU clusters; never creates billable clusters implicitly.
terraform {
  required_version = ">= 1.7, < 2.0"
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.17"
    }
  }
}
variable "kubeconfig" { type = string }
variable "aws_context" { type = string }
variable "azure_context" { type = string }
variable "gcp_context" { type = string }
variable "model" {
  type    = string
  default = "Qwen/Qwen2.5-0.5B-Instruct"
}
provider "helm" {
  alias = "aws"
  kubernetes {
    config_path    = var.kubeconfig
    config_context = var.aws_context
  }
}
provider "helm" {
  alias = "azure"
  kubernetes {
    config_path    = var.kubeconfig
    config_context = var.azure_context
  }
}
provider "helm" {
  alias = "gcp"
  kubernetes {
    config_path    = var.kubeconfig
    config_context = var.gcp_context
  }
}
module "aws" {
  source          = "../modules/serving"
  providers       = { helm = helm.aws }
  name            = "aws-vllm"
  namespace       = "inference"
  model           = var.model
  existing_secret = "vllm-secrets"
  node_selector   = { "inference-pool" = "gpu" }
}
module "azure" {
  source          = "../modules/serving"
  providers       = { helm = helm.azure }
  name            = "azure-vllm"
  namespace       = "inference"
  model           = var.model
  existing_secret = "vllm-secrets"
  node_selector   = { "inference-pool" = "gpu" }
}
module "gcp" {
  source          = "../modules/serving"
  providers       = { helm = helm.gcp }
  name            = "gcp-vllm"
  namespace       = "inference"
  model           = var.model
  existing_secret = "vllm-secrets"
  node_selector   = { "inference-pool" = "gpu" }
}
output "cluster_local_endpoints" {
  value = { aws = module.aws.service, azure = module.azure.service, gcp = module.gcp.service }
}
