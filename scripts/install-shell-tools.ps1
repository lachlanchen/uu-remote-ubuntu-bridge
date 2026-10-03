param([Parameter(Mandatory=$true)][string]$Inventory)
$ErrorActionPreference='Stop'
$profiles=Get-Content $Inventory -Raw | ConvertFrom-Json
$needsFleet=@($profiles.PSObject.Properties|Where-Object {$_.Value.shell_transport -eq 'lazytunnel'}).Count -gt 0
$bundle=if($needsFleet){Get-Content "$env:USERPROFILE\.config\lazytunnel-fleet\bundle.json" -Raw | ConvertFrom-Json}else{$null}
foreach($entry in $profiles.PSObject.Properties) {
    $p=$entry.Value
    if($entry.Name -notmatch '^[a-z0-9][a-z0-9-]{0,47}$' -or $p.name -cne $entry.Name) {throw 'Invalid peer name'}
    foreach($field in $p.PSObject.Properties.Name) {
        if($field -notin @('name','fleet_peer','shell_transport','device_id','terminal_shell')) {throw 'Unexpected profile fields'}
    }
    if($p.shell_transport -notin @('lazytunnel','terminal')) {throw 'Invalid transport'}
    if($p.shell_transport -eq 'lazytunnel' -and $bundle.aliases -cnotcontains $p.fleet_peer) {throw 'Peer is not enrolled'}
    if($p.device_id -and $p.device_id -notmatch '^[A-Za-z0-9-]{1,80}$') {throw 'Invalid device ID'}
    if($p.terminal_shell -notin @('powershell','cmd','zsh','bash')) {throw 'Invalid terminal shell'}
}
$backup=Join-Path $env:USERPROFILE '.local\state\uu-shell-tools\backups'
function Write-ShellFile([string]$Path,[byte[]]$Data) {
    if(Test-Path $Path) {
        if((Get-Item $Path).Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Refusing reparse point'}
        $old=[IO.File]::ReadAllBytes($Path)
        if([Convert]::ToBase64String($old) -ceq [Convert]::ToBase64String($Data)) {return}
        New-Item -ItemType Directory -Force $backup | Out-Null
        $digest=(Get-FileHash -Algorithm SHA256 $Path).Hash.Substring(0,16)
        $saved=Join-Path $backup ((Split-Path -Leaf $Path)+'.'+$digest)
        if(!(Test-Path $saved)){[IO.File]::WriteAllBytes($saved,$old)}
    }
    New-Item -ItemType Directory -Force (Split-Path $Path) | Out-Null
    $tmp=$Path+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
    try {[IO.File]::WriteAllBytes($tmp,$Data);Move-Item -Force $tmp $Path}
    finally {if(Test-Path $tmp){Remove-Item $tmp}}
}
foreach($file in @('uu-shell.cmd','uu-shell.ps1')) {
    Write-ShellFile (Join-Path "$env:USERPROFILE\.local\bin" $file) ([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot $file)))
}
foreach($entry in $profiles.PSObject.Properties) {
    $path=Join-Path "$env:USERPROFILE\.config\uu-ssh\peers" ($entry.Name+'.json')
    $p=if(Test-Path $path){Get-Content $path -Raw|ConvertFrom-Json}else{[pscustomobject]@{}}
    foreach($field in $entry.Value.PSObject.Properties){$p|Add-Member -NotePropertyName $field.Name -NotePropertyValue $field.Value -Force}
    Write-ShellFile $path ([Text.Encoding]::UTF8.GetBytes(($p|ConvertTo-Json)+"`n"))
}
Write-Output ('Installed shell shortcuts and '+@($profiles.PSObject.Properties).Count+' reviewed profiles; no service changes.')
