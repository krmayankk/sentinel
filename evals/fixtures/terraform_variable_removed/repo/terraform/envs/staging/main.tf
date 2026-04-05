module "rds" {
  source         = "../../modules/rds"
  instance_class = "db.t3.small"
  db_name        = "appdb_staging"
  username       = "admin"

  enable_performance_insights = false
}
