terraform {
  required_version = ">= 1.7, < 2.0"
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.17"
    }
  }
}
variable "name" { type = string }
variable "namespace" { type = string }
variable "model" { type = string }
variable "existing_secret" { type = string }
variable "node_selector" {
  type    = map(string)
  default = {}
}
resource "helm_release" "vllm" {
  name             = var.name
  namespace        = var.namespace
  create_namespace = true
  chart            = "${path.module}/../../../helm/vllm"
  timeout          = 1200
  atomic           = true
  values = [yamlencode({
    model          = var.model
    existingSecret = var.existing_secret
    nodeSelector   = var.node_selector
  })]
}
output "service" {
  value = "http://${var.name}.${var.namespace}.svc.cluster.local:8000/v1"
}
