[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $SubscriptionId,

    [Parameter(Mandatory = $true)]
    [string] $ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string] $Location,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[a-zA-Z0-9]{5,50}$")]
    [string] $RegistryName,

    [Parameter(Mandatory = $true)]
    [string] $ContainerAppsEnvironment,

    [Parameter(Mandatory = $true)]
    [string] $ContainerAppName
)

$ErrorActionPreference = "Stop"

az account set --subscription $SubscriptionId
az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.ContainerRegistry --wait

az group create `
    --name $ResourceGroup `
    --location $Location `
    --output none

$registryExists = az acr show `
    --name $RegistryName `
    --query name `
    --output tsv `
    2>$null

if (-not $registryExists) {
    az acr create `
        --resource-group $ResourceGroup `
        --name $RegistryName `
        --sku Basic `
        --admin-enabled false `
        --output none
}

$environmentExists = az containerapp env show `
    --resource-group $ResourceGroup `
    --name $ContainerAppsEnvironment `
    --query name `
    --output tsv `
    2>$null

if (-not $environmentExists) {
    az containerapp env create `
        --resource-group $ResourceGroup `
        --name $ContainerAppsEnvironment `
        --location $Location `
        --output none
}

$appExists = az containerapp show `
    --resource-group $ResourceGroup `
    --name $ContainerAppName `
    --query name `
    --output tsv `
    2>$null

if (-not $appExists) {
    az containerapp create `
        --resource-group $ResourceGroup `
        --name $ContainerAppName `
        --environment $ContainerAppsEnvironment `
        --image "mcr.microsoft.com/k8se/quickstart:latest" `
        --ingress external `
        --target-port 80 `
        --system-assigned `
        --min-replicas 1 `
        --max-replicas 3 `
        --output none
}
else {
    az containerapp identity assign `
        --resource-group $ResourceGroup `
        --name $ContainerAppName `
        --system-assigned `
        --output none
}

$principalId = az containerapp identity show `
    --resource-group $ResourceGroup `
    --name $ContainerAppName `
    --query principalId `
    --output tsv

$registryId = az acr show `
    --name $RegistryName `
    --query id `
    --output tsv

$existingAssignment = az role assignment list `
    --assignee-object-id $principalId `
    --scope $registryId `
    --role AcrPull `
    --query "[0].id" `
    --output tsv

if (-not $existingAssignment) {
    az role assignment create `
        --assignee-object-id $principalId `
        --assignee-principal-type ServicePrincipal `
        --scope $registryId `
        --role AcrPull `
        --output none
}

$registryServer = az acr show `
    --name $RegistryName `
    --query loginServer `
    --output tsv

az containerapp registry set `
    --resource-group $ResourceGroup `
    --name $ContainerAppName `
    --server $registryServer `
    --identity system `
    --output none

Write-Host ""
Write-Host "Azure Container Apps infrastructure is ready."
Write-Host "Resource group:             $ResourceGroup"
Write-Host "Registry:                   $RegistryName"
Write-Host "Container Apps environment: $ContainerAppsEnvironment"
Write-Host "Container App:              $ContainerAppName"
Write-Host ""
Write-Host "Add these names as GitHub environment variables, then run the deployment workflow."
