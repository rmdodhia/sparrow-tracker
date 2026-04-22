using './main.bicep'

param location = 'westus2'
param environment = 'prod'
param sqlAdminLogin = 'sparrowadmin'

// Set these at deploy time:
//   az deployment group create ... --parameters sqlAdminPassword='<password>'
//   Or use a Key Vault reference in production.
param sqlAdminPassword = '' // REQUIRED — pass via CLI or Key Vault
param appRegistrationClientId = '5f813bb9-d2c4-4246-ba36-3c394a0ade39'
param appRegistrationClientSecret = '' // Set after Rahul grants app reg access
