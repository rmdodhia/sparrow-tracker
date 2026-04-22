#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# deploy.sh — Deploy sparrow-tracker infrastructure to Azure
#
# Prerequisites:
#   - Azure CLI authenticated (az login --tenant 72f988bf-86f1-41af-91ab-2d7cd011db47)
#   - PIM activated for CELA Data Science Team subscription
#
# Usage:
#   ./infra/deploy.sh <sql-admin-password>
#   ./infra/deploy.sh <sql-admin-password> <graph-client-secret>
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SUBSCRIPTION="55a24be0-d9c3-4ecd-86b6-566c7aac2512"  # CELA Data Science Team
RESOURCE_GROUP="ai4gl-sparrow-prod-rg"
LOCATION="eastus2"
TEMPLATE="$(dirname "$0")/main.bicep"

SQL_PASSWORD="${1:?Usage: $0 <sql-admin-password> [graph-client-secret]}"
GRAPH_SECRET="${2:-}"

echo "==> Setting subscription to CELA Data Science Team..."
az account set --subscription "$SUBSCRIPTION"

echo "==> Creating resource group ${RESOURCE_GROUP}..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags project=sparrow-tracker environment=prod owner=rmdodhia endDate=2027-06-30 \
  --output none

echo "==> Deploying Bicep template..."
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "$TEMPLATE" \
  --parameters \
    sqlAdminPassword="$SQL_PASSWORD" \
    appRegistrationClientSecret="$GRAPH_SECRET" \
  --output json \
  --query "properties.outputs"

echo ""
echo "==> Deployment complete!"
echo "    Web App: https://sparrow-tracker.azurewebsites.net"
echo ""
echo "Next steps:"
echo "  1. Deploy app code:  az webapp deploy --resource-group $RESOURCE_GROUP --name sparrow-tracker --src-path <zip>"
echo "  2. Set OpenAI keys:  az webapp config appsettings set --resource-group $RESOURCE_GROUP --name sparrow-tracker --settings AZURE_OPENAI_ENDPOINT=... AZURE_OPENAI_API_KEY=..."
echo "  3. Initialize the SQL database schema (run db.py init against Azure SQL)"
