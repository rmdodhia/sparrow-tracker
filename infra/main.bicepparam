using './main.bicep'

param location = 'westus2'
param environment = 'prod'

// Azure AD admin for SQL Server — use your user/group object ID
// Find yours with: az ad signed-in-user show --query id -o tsv
param sqlAadAdminObjectId = '' // REQUIRED — your Azure AD object ID or group ID
param sqlAadAdminName = 'sparrow-tracker-admins'

param appRegistrationClientId = '5f813bb9-d2c4-4246-ba36-3c394a0ade39'
param appRegistrationClientSecret = '' // Set after Rahul grants app reg access
