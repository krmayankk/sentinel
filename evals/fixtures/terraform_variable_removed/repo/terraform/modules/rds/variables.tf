# Pre-PR state: variable still exists in the module
variable "enable_performance_insights" {
  description = "Enable Performance Insights for query diagnostics"
  type        = bool
  default     = false
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
}
