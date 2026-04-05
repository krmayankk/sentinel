module "rds" {
  source         = "../../modules/rds"
  instance_class = "db.t3.micro"
  db_name        = "appdb_dev"
  username       = "admin"

  enable_performance_insights = false
}
