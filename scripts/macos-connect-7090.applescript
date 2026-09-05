property targetName : "OptiPlex 7090"
property targetHost : "OptiPlex-7090.local"
property sshAlias : "glassagent-ubuntu"
property relayPort : 5922
property vncTunnelPort : 15922

on run
	set connectionModes to {"Current Desktop", "Separate Login (RDP)", "Terminal (SSH)", "Connection Test"}
	set selectedItems to choose from list connectionModes with title "Connect to 7090" with prompt "Choose a connection" default items {item 1 of connectionModes} OK button name "Open" cancel button name "Cancel"
	if selectedItems is false then return
	
	set selectedMode to item 1 of selectedItems
	if selectedMode is item 1 of connectionModes then
		my openCurrentDesktop()
	else if selectedMode is item 2 of connectionModes then
		my openRemoteLogin()
	else if selectedMode is item 3 of connectionModes then
		my openTerminal()
	else
		my showConnectionTest()
	end if
end run

on openCurrentDesktop()
	if not my portIsOpen(targetHost, 22) then
		my showUnavailable("SSH", 22)
		return
	end if
	
	if not my portIsOpen("localhost", vncTunnelPort) then
		set forwardSpec to (vncTunnelPort as text) & ":127.0.0.1:" & (relayPort as text)
		set remoteCommand to "~/.local/bin/uu-remote-console relay"
		set tunnelCommand to "/usr/bin/ssh -fn -o BatchMode=yes -o ExitOnForwardFailure=yes -o ConnectTimeout=8 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L " & quoted form of forwardSpec & " " & quoted form of sshAlias & " " & quoted form of remoteCommand & " >/dev/null 2>&1"
		try
			do shell script tunnelCommand
		on error errorText
			display alert "Current desktop relay could not start" message errorText as warning
			return
		end try
	end if
	
	repeat 30 times
		if my portIsOpen("localhost", vncTunnelPort) then exit repeat
		delay 0.2
	end repeat
	if not my portIsOpen("localhost", vncTunnelPort) then
		display alert "Current desktop relay is not ready" message "The SSH tunnel opened, but the Ubuntu desktop relay did not answer." as warning
		return
	end if
	
	set desktopUrl to "vnc://localhost:" & (vncTunnelPort as text)
	do shell script "/usr/bin/open " & quoted form of desktopUrl
end openCurrentDesktop

on openRemoteLogin()
	if not my portIsOpen(targetHost, 3389) then
		my showUnavailable("Remote login", 3389)
		return
	end if

	set rdpUri to "rdp://full%20address=s%3A" & targetHost & "%3A3389&username=s%3Alachlan&screen%20mode%20id=i%3A2&dynamic%20resolution=i%3A1&redirectclipboard=i%3A1&audiomode=i%3A0"
	if my applicationExists("/Applications/Windows App.app") then
		do shell script "/usr/bin/open -a " & quoted form of "Windows App" & " " & quoted form of rdpUri
	else if my applicationExists("/Applications/Microsoft Remote Desktop.app") then
		do shell script "/usr/bin/open -a " & quoted form of "Microsoft Remote Desktop" & " " & quoted form of rdpUri
	else if my applicationExists("/Applications/Royal TSX.app") then
		set lineFeed to ASCII character 10
		set rdpContents to "full address:s:" & targetHost & ":3389" & lineFeed & "username:s:lachlan" & lineFeed & "screen mode id:i:2" & lineFeed & "dynamic resolution:i:1" & lineFeed & "redirectclipboard:i:1" & lineFeed & "audiomode:i:0" & lineFeed
		set rdpPath to (POSIX path of (path to temporary items)) & "OptiPlex-7090.rdp"
		do shell script "/usr/bin/printf %s " & quoted form of rdpContents & " > " & quoted form of rdpPath
		do shell script "/usr/bin/open -a " & quoted form of "Royal TSX" & " " & quoted form of rdpPath
	else
		display alert "RDP client unavailable" message "Install Windows App, Microsoft Remote Desktop, or Royal TSX." as warning
	end if
end openRemoteLogin

on openTerminal()
	if not my portIsOpen(targetHost, 22) then
		my showUnavailable("SSH", 22)
		return
	end if
	tell application "Terminal"
		activate
		do script "exec ssh " & sshAlias
	end tell
end openTerminal

on showConnectionTest()
	set sshState to my stateLabel(my portIsOpen(targetHost, 22))
	set rdpState to my stateLabel(my portIsOpen(targetHost, 3389))
	set relayState to "Unavailable"
	try
		set remotePort to do shell script "/usr/bin/ssh -o BatchMode=yes -o ConnectTimeout=4 " & quoted form of sshAlias & " " & quoted form of "~/.local/bin/uu-remote-console relay-port"
		if remotePort is (relayPort as text) then set relayState to "Ready through SSH"
	end try
	display dialog "Current desktop: " & relayState & return & "SSH: " & sshState & return & "Separate RDP login: " & rdpState with title targetName buttons {"OK"} default button "OK" with icon note
end showConnectionTest

on portIsOpen(hostName, portNumber)
	try
		do shell script "/usr/bin/nc -G 2 -z " & quoted form of hostName & " " & (portNumber as text)
		return true
	on error
		return false
	end try
end portIsOpen

on stateLabel(isReady)
	if isReady then return "Ready"
	return "Unavailable"
end stateLabel

on applicationExists(applicationPath)
	try
		do shell script "/usr/bin/test -d " & quoted form of applicationPath
		return true
	on error
		return false
	end try
end applicationExists

on showUnavailable(serviceName, portNumber)
	display alert serviceName & " is unavailable" message targetName & " did not answer on port " & (portNumber as text) & "." as warning
end showUnavailable
