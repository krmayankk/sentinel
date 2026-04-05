module "rds" {
  source         = "../../modules/rds"
  instance_class = "db.t3.medium"
  db_name        = "appdb_prod"
  username       = "admin"

  # This argument will break after the module variable is removed
  enable_performance_insights = true
}
