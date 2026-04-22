// ──────────────────────────────────────────────────────────────────────────────
// Sparrow-Tracker — Azure Infrastructure (App Service + Azure SQL)
// Subscription: CELA Data Science Team (55a24be0-d9c3-4ecd-86b6-566c7aac2512)
// ──────────────────────────────────────────────────────────────────────────────

targetScope = 'resourceGroup'

@description('Azure region for all resources')
param location string = 'westus2'

@description('Environment name')
@allowed(['prod', 'dev'])
param environment string = 'prod'

@description('Azure AD admin object ID for SQL Server (use your own or the managed identity)')
param sqlAadAdminObjectId string

@description('Azure AD admin display name')
param sqlAadAdminName string = 'sparrow-tracker-admins'

@description('App registration client ID for Microsoft Graph')
param appRegistrationClientId string = '5f813bb9-d2c4-4246-ba36-3c394a0ade39'

@secure()
@description('App registration client secret for Microsoft Graph')
param appRegistrationClientSecret string = ''

// ── Tags (required by lab convention) ────────────────────────────────────────

var tags = {
  project: 'sparrow-tracker'
  environment: environment
  owner: 'rmdodhia'
  endDate: '2027-06-30'
}

// ── App Service Plan ─────────────────────────────────────────────────────────

resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'ai4gl-sparrow-${environment}-plan'
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true // required for Linux
  }
}

// ── Web App ──────────────────────────────────────────────────────────────────

resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: 'sparrow-tracker' // exact name for sparrow-tracker.azurewebsites.net
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: 'python -m streamlit run app.py --server.port 8000 --server.headless true --server.address 0.0.0.0'
      alwaysOn: true
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: [
        { name: 'WEBSITES_PORT', value: '8000' }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        // Azure OpenAI — set actual values in App Service Configuration
        { name: 'AZURE_OPENAI_ENDPOINT', value: '' }
        { name: 'AZURE_OPENAI_DEPLOYMENT', value: '' }
        { name: 'AZURE_OPENAI_API_KEY', value: '' }
        // Azure SQL — managed identity auth (Entra-only, no SQL password)
        {
          name: 'AZURE_SQL_CONNECTION_STRING'
          value: 'Driver={ODBC Driver 18 for SQL Server};Server=tcp:${sqlServer.properties.fullyQualifiedDomainName},1433;Database=${sqlDatabase.name};Authentication=ActiveDirectoryMsi;Encrypt=yes;TrustServerCertificate=no;'
        }
        // Microsoft Graph (for email ingestion)
        { name: 'GRAPH_CLIENT_ID', value: appRegistrationClientId }
        { name: 'GRAPH_CLIENT_SECRET', value: appRegistrationClientSecret }
        { name: 'GRAPH_TENANT_ID', value: '72f988bf-86f1-41af-91ab-2d7cd011db47' }
        { name: 'GRAPH_USER_EMAIL', value: 'sparrow-tracker@microsoft.com' }
        // Azure DevOps
        { name: 'AZURE_DEVOPS_ORG', value: 'onecela' }
        { name: 'AZURE_DEVOPS_PROJECT', value: 'AI For Good Lab' }
      ]
    }
  }
}

// ── Azure SQL Server ─────────────────────────────────────────────────────────

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: 'ai4gl-sparrow-${environment}-sql'
  location: location
  tags: tags
  properties: {
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'Group'
      login: sqlAadAdminName
      sid: sqlAadAdminObjectId
      tenantId: '72f988bf-86f1-41af-91ab-2d7cd011db47'
      azureADOnlyAuthentication: true
    }
  }
}

// Allow Azure services to access SQL Server
resource sqlFirewallAllowAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ── Azure SQL Database ───────────────────────────────────────────────────────

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: 'sparrow-tracker-db'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
    tier: 'Basic'
    capacity: 5
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    maxSizeBytes: 2147483648 // 2 GB
  }
}

// ── Outputs ──────────────────────────────────────────────────────────────────

output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output webAppName string = webApp.name
output webAppPrincipalId string = webApp.identity.principalId
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabaseName string = sqlDatabase.name
