# Optional native Windows counterpart to uu-shell. No services or fallback.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    $rest = @($args)
    if (!$rest.Count -or $rest[0] -in @('-h','--help')) {
        Write-Output 'Usage: uu-shell PEER [arguments...] | --lazy PEER [SSH arguments...] | --native PEER [UU options...] | --list'
        exit 0
    }
    $root = Join-Path $env:USERPROFILE '.config\uu-ssh\peers'
    if ($rest[0] -eq '--list') {
        Get-ChildItem $root -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object {
            $p = Get-Content $_.FullName -Raw | ConvertFrom-Json
            Write-Output ($p.name + '  shell=' + $p.shell_transport)
        }
        exit 0
    }
    $selected = ''
    if ($rest[0] -in @('--lazy','--native')) {
        $selected = if ($rest[0] -eq '--lazy') {'lazytunnel'} else {'terminal'}
        $rest = @($rest | Select-Object -Skip 1)
    }
    if (!$rest.Count -or $rest[0] -notmatch '^[a-z0-9][a-z0-9-]{0,47}$') { throw 'Invalid or missing peer name' }
    $peer = [string]$rest[0]
    $options = @($rest | Select-Object -Skip 1)
    $file = Join-Path $root ($peer + '.json')
    $profile = if (Test-Path $file) {Get-Content $file -Raw | ConvertFrom-Json} else {$null}
    $transport = if ($selected) {$selected} elseif ($profile) {$profile.shell_transport} else {throw 'Unknown peer; configure an explicit route first'}
    if ($transport -eq 'lazytunnel') {
        $target = if (!$selected -and $profile.fleet_peer) {$profile.fleet_peer} else {$peer}
        if ($target -notmatch '^[a-z0-9][a-z0-9-]{0,47}$') {throw 'Invalid enrolled device name'}
        $fleet = Join-Path $env:USERPROFILE '.config\lazytunnel-fleet'
        $bundle = Get-Content (Join-Path $fleet 'bundle.json') -Raw | ConvertFrom-Json
        if ($bundle.aliases -cnotcontains $target) {throw 'Device is not enrolled in this LazyTunnel account'}
        [Console]::Error.WriteLine('uu-shell: LazyTunnel SSH -> ' + $target)
        & (Join-Path $fleet 'fleet-ssh.ps1') ('lazy-' + $target) @options
        exit $LASTEXITCODE
    }
    if ($transport -ne 'terminal') {throw 'Unsupported transport in Windows uu-shell profile'}
    if (!$profile.device_id -or $profile.device_id -notmatch '^[A-Za-z0-9-]{1,80}$') {throw 'Profile has no valid UU device ID'}
    $cli = Join-Path $env:ProgramFiles 'Netease\GameViewer\bin\uuyc-cli.exe'
    if (!(Test-Path $cli)) {throw 'Native UU CLI is not installed at its standard path'}
    $shell = if ($profile.terminal_shell) {$profile.terminal_shell} else {'powershell'}
    if ($shell -notin @('powershell','cmd','zsh','bash')) {throw 'Invalid terminal shell'}
    $call = @('term','--device-id',$profile.device_id)
    if (!($options | Where-Object {$_ -match '^--(session-id|list-sessions|kill-session|new-session)(=|$)'})) {$call += '--new-session'}
    if (!($options | Where-Object {$_ -match '^--shell(=|$)'})) {$call += @('--shell',$shell)}
    [Console]::Error.WriteLine('uu-shell: native UU Terminal -> ' + $peer)
    & $cli @call @options
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine('uu-shell: ' + $_.Exception.Message)
    exit 1
}
