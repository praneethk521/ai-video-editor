# Terraform

Production Terraform should provision:

- Private VPC or equivalent private networking.
- PostgreSQL with encryption at rest and automated backups.
- Redis or managed queue.
- Private object storage bucket with default encryption and public access blocked.
- KMS keys for media encryption.
- IAM roles using GitHub Actions OIDC.
- Secret manager entries for OAuth, AI provider, database, and n8n keys.
- Container runtime with locked-down task definitions or Kubernetes node policies.

This folder intentionally starts as a checklist stub because provider choice affects resource layout. Keep state remote and encrypted.

