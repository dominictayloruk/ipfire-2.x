#!/usr/bin/perl
###############################################################################
#                                                                             #
# IPFire.org - A linux based firewall                                         #
# Copyright (C) 2007-2022  IPFire Team  <info@ipfire.org>                     #
#                                                                             #
# This program is free software: you can redistribute it and/or modify        #
# it under the terms of the GNU General Public License as published by        #
# the Free Software Foundation, either version 3 of the License, or           #
# (at your option) any later version.                                         #
#                                                                             #
# This program is distributed in the hope that it will be useful,             #
# but WITHOUT ANY WARRANTY; without even the implied warranty of              #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the               #
# GNU General Public License for more details.                                #
#                                                                             #
# You should have received a copy of the GNU General Public License           #
# along with this program.  If not, see <http://www.gnu.org/licenses/>.       #
#                                                                             #
###############################################################################

use strict;
use List::Util qw(any);
use URI;

# enable only the following on debugging purpose
#use warnings;
#use CGI::Carp 'fatalsToBrowser';

require '/var/ipfire/general-functions.pl';
require "${General::swroot}/lang.pl";
require "${General::swroot}/header.pl";
require "/opt/pakfire/lib/functions.pl";

my %cgiparams=();
my $errormessage = '';
my %color = ();
my %pakfiresettings = ();
my %mainsettings = ();

# The page mode is used to explictly switch between user interface functions:
my $PM_DEFAULT = 'default'; # Default user interface with command processing
my $PM_LOGREAD = 'logread'; # Log messages viewer (ignores all commands)
my $pagemode = $PM_DEFAULT;

# Get Pakfire status
my %pakfire_status = &Pakfire::status();

# Load general settings
&General::readhash("${General::swroot}/main/settings", \%mainsettings);
&General::readhash("${General::swroot}/pakfire/settings", \%pakfiresettings);
&General::readhash("/srv/web/ipfire/html/themes/ipfire/include/colors.txt", \%color);

# Get CGI POST request data
$cgiparams{'ACTION'} = '';
$cgiparams{'FORCE'} = '';

$cgiparams{'INSPAKS'} = '';
$cgiparams{'DELPAKS'} = '';

&Header::getcgihash(\%cgiparams);

# Get CGI GET request data (if available)
if($ENV{'QUERY_STRING'}) {
	my $uri = URI->new($ENV{'REQUEST_URI'});
	my %query = $uri->query_form;

	my $mode = lc($query{'mode'} // '');
	if(($mode eq $PM_DEFAULT) || ($mode eq $PM_LOGREAD)) {
		$pagemode = $mode; # Limit to existing modes
	}
}

### Process AJAX/JSON request ###
if($cgiparams{'ACTION'} eq 'json-getstatus') {
	# Send HTTP headers
	_start_json_output();

	# Read /var/log/messages backwards until a "Pakfire started" header is found,
	# to capture all messages of the last (i.e. current) Pakfire run
	my @messages = `tac /var/log/messages 2>/dev/null | sed -n '/pakfire:/{p;/Pakfire.*started/q}'`;

	# Test if the log contains an error message (fastest implementation, stops at first match)
	my $failure = any{ index($_, 'ERROR') != -1 } @messages;

	# Collect Pakfire status
	my %status = (
		'running' => &_is_pakfire_busy() || "0",
		'running_since' => &General::age("$Pakfire::lockfile") || "0s",
		'reboot' => ("$pakfire_status{'RebootRequired'}" eq "yes") || "0",
		'failure' => $failure || "0"
	);

	# Start JSON file
	print "{\n";

	foreach my $key (keys %status) {
		my $value = $status{$key};
		print qq{\t"$key": "$value",\n};
	}

	# Print sanitized messages in reverse order to undo previous "tac"
	print qq{\t"messages": [\n};
	for my $index (reverse (0 .. $#messages)) {
		my $line = $messages[$index];
		$line =~ s/[[:cntrl:]<>&\\]+//g;

		print qq{\t\t"$line"};
		print ",\n" unless $index < 1;
	}
	print "\n\t]\n";

	# Finalize JSON file & stop
	print "}";
	exit;
}

### Process Pakfire install/update commands ###
if(($cgiparams{'ACTION'} ne '') && ($pagemode eq $PM_DEFAULT)) {
	if(&_is_pakfire_busy()) {
		$errormessage = $Lang::tr{'pakfire already busy'};
		$pagemode = $PM_LOGREAD; # Running Pakfire instance found, switch to log viewer mode
	} elsif(($cgiparams{'ACTION'} eq $Lang::tr{'pakfire install'}) && ($cgiparams{'FORCE'} eq 'on')) {
		my @pkgs = split(/\|/, $cgiparams{'INSPAKS'});
		&General::system_background("/usr/local/bin/pakfire", "install", "--non-interactive", "--no-colors", @pkgs);
		&_http_pagemode_redirect($PM_LOGREAD, 1);
	} elsif(($cgiparams{'ACTION'} eq $Lang::tr{'remove'}) && ($cgiparams{'FORCE'} eq 'on')) {
		my @pkgs = split(/\|/, $cgiparams{'DELPAKS'});
		&General::system_background("/usr/local/bin/pakfire", "remove", "--non-interactive", "--no-colors", @pkgs);
		&_http_pagemode_redirect($PM_LOGREAD, 1);
	} elsif($cgiparams{'ACTION'} eq $Lang::tr{'pakfire refresh list'}) {
		&General::system_background("/usr/local/bin/pakfire", "update", "--force", "--no-colors");
		&_http_pagemode_redirect($PM_LOGREAD, 1);
	} elsif(($cgiparams{'ACTION'} eq $Lang::tr{'pakfire upgrade'}) && ($cgiparams{'FORCE'} eq 'on')) {
		&General::system_background("/usr/local/bin/pakfire", "upgrade", "-y", "--no-colors");
		&_http_pagemode_redirect($PM_LOGREAD, 1);
	} elsif($cgiparams{'ACTION'} eq $Lang::tr{'save'}) {
		$pakfiresettings{"TREE"} = $cgiparams{"TREE"};

		# Check for valid input
		if ($pakfiresettings{"TREE"} !~ m/^(stable|testing|unstable)$/) {
			$errormessage .= $Lang::tr{'pakfire invalid tree'};
		}

		unless ($errormessage) {
			&General::writehash("${General::swroot}/pakfire/settings", \%pakfiresettings);

			# Update lists
			&General::system_background("/usr/local/bin/pakfire", "update", "--force", "--no-colors");
			&_http_pagemode_redirect($PM_LOGREAD, 1);
		}
	}
}

### Start pakfire page ###
&Header::showhttpheaders();

###--- HTML HEAD ---###
my $extraHead = <<END
<style>
	/* Main screen */
	table#pfmain {
		width: 100%;
		table-layout: fixed;
		text-align: center;
	}
	#pfmain td {
		padding: 0px 20px;
	}
	#pfmain tr > td.heading {
		padding: 0;
		font-weight: bold;
		background-color: $color{'color20'};
	}

	.pflist {
		width: 100%;
		text-align: left;
		margin-bottom: 0.8em;
	}

	/* Pakfire log viewer */
	section#pflog-header {
		width: 100%;
		display: flex;
		text-align: left;
		align-items: center;
		column-gap: 20px;
	}
	#pflog-header > div:last-child {
		margin-left: auto;
		margin-right: 20px;
	}
	#pflog-header span {
		line-height: 1.3em;
	}
	#pflog-header span:empty::before {
		content: "\\200b"; /* zero width space */
	}

	pre#pflog-messages {
		margin-top: 0.7em;
		padding-top: 0.7em;
		border-top: 0.5px solid $Header::bordercolour;
		text-align: left;
		min-height: 15em;
		overflow-x: auto;
	}
</style>

<script src="/include/pakfire.js"></script>
<script>
	// Translations
	pakfire.i18n.load({
		'working': '$Lang::tr{'pakfire working'}',
		'finished': '$Lang::tr{'pakfire finished'}',
		'finished error': '$Lang::tr{'pakfire finished error'}',
		'since': '$Lang::tr{'since'}',

		'link_return': '<a href="$ENV{'SCRIPT_NAME'}">$Lang::tr{'pakfire return'}</a>',
		'link_reboot': '<a href="/cgi-bin/shutdown.cgi">$Lang::tr{'needreboot'}</a>'
	});

	// AJAX auto refresh interval (in ms, default: 1000)
	//pakfire.refreshInterval = 1000;

	// Enable returning to main screen (delay in ms)
	pakfire.setupPageReload(true, 3000);
</script>
END
;
###--- END HTML HEAD ---###

&Header::openpage($Lang::tr{'pakfire configuration'}, 1, $extraHead);
&Header::openbigbox('100%', 'left', '', $errormessage);

# Show error message
if ($errormessage) {
	&Header::openbox('100%', 'left', $Lang::tr{'error messages'});
	print "<font class='base'>$errormessage&nbsp;</font>\n";
	&Header::closebox();
}

# Show only log output while Pakfire is running and stop afterwards
if(($pagemode eq $PM_LOGREAD) || (&_is_pakfire_busy())) {
	&Header::openbox("100%", "center", "Pakfire");

	print <<END
<section id="pflog-header">
	<div><img src="/images/indicator.gif" alt="$Lang::tr{'active'}" title="$Lang::tr{'pagerefresh'}"></div>
	<div>
		<span id="pflog-status">$Lang::tr{'pakfire working'}</span><br>
		<span id="pflog-time"></span><br>
		<span id="pflog-action"></span>
	</div>
	<div><a href="$ENV{'SCRIPT_NAME'}"><img src="/images/view-refresh.png" alt="$Lang::tr{'refresh'}" title="$Lang::tr{'refresh'}"></a></div>
</section>

<!-- Pakfire log messages -->
<pre id="pflog-messages"></pre>
<script>
	// Start automatic log refresh
	pakfire.running = true;
</script>

END
;

	&Header::closebox();
	&Header::closebigbox();
	&Header::closepage();
	exit;
}

# Show Pakfire install/remove dependencies and confirm form
# (_is_pakfire_busy status was checked before and can be omitted)
if (($cgiparams{'ACTION'} eq $Lang::tr{'pakfire install'}) && ($pagemode eq $PM_DEFAULT)) {
	&Header::openbox("100%", "center", $Lang::tr{'request'});

	my @pkgs = split(/\|/, $cgiparams{'INSPAKS'});
	my @output = &General::system_output("/usr/local/bin/pakfire", "resolvedeps", "--no-colors", @pkgs);
	print <<END;
	<table style="width: 100%">
		<tr>
			<td>
			<p>$Lang::tr{'pakfire install package'} <strong>@{pkgs}</strong><br>$Lang::tr{'pakfire possible dependency'}</p>
			<pre>
END
	foreach (@output) {
		$_ =~ s/\\[[0-1]\;[0-9]+m//g;
		print "$_\n";
	}
	print <<END;
			</pre>
			</td>
		</tr>
		<tr>
			<td>$Lang::tr{'pakfire accept all'}</td>
		</tr>
		<tr>
			<td>&nbsp;</td>
		</tr>
		<tr>
			<td align='center'>
			<form method='post' action='$ENV{'SCRIPT_NAME'}'>
			<input type='hidden' name='INSPAKS' value='$cgiparams{'INSPAKS'}' />
			<input type='hidden' name='FORCE' value='on' />
			<input type='submit' name='ACTION' value='$Lang::tr{'pakfire install'}'/>
			<input type='submit' name='ACTION' value='$Lang::tr{'cancel'}'/>
			</form>
			</td>
		</tr>
	</table>
END
	&Header::closebox();
	&Header::closebigbox();
	&Header::closepage();
	exit;

} elsif (($cgiparams{'ACTION'} eq $Lang::tr{'remove'}) && ($pagemode eq $PM_DEFAULT)) {
	&Header::openbox("100%", "center", $Lang::tr{'request'});

	my @pkgs = split(/\|/, $cgiparams{'DELPAKS'});
	my @output = &General::system_output("/usr/local/bin/pakfire", "resolvedeps", "--no-colors", @pkgs);
	print <<END;
	<table style="width: 100%">
		<tr>
			<td colspan='2'>
			<p>$Lang::tr{'pakfire uninstall package'} <strong>@{pkgs}</strong><br>$Lang::tr{'pakfire possible dependency'}</p>
			<pre>
END
	foreach (@output) {
		$_ =~ s/\\[[0-1]\;[0-9]+m//g;
		print "$_\n";
	}
	print <<END;
			</pre>
			</td>
		</tr>
		<tr>
			<td colspan='2'>$Lang::tr{'pakfire uninstall all'}</td>
		</tr>
		<tr>
			<td colspan='2'>&nbsp;</td>
		</tr>
		<tr>
			<td align='center'>
			<form method='post' action='$ENV{'SCRIPT_NAME'}'>
			<input type='hidden' name='DELPAKS' value='$cgiparams{'DELPAKS'}' />
			<input type='hidden' name='FORCE' value='on' />
			<input type='submit' name='ACTION' value='$Lang::tr{'remove'}'/>
			<input type='submit' name='ACTION' value='$Lang::tr{'cancel'}'/>
			</form>
			</td>
		</tr>
	</table>
END
	&Header::closebox();
	&Header::closebigbox();
	&Header::closepage();
	exit;
}

# Show Pakfire upgrades to be done and confirm
# (_is_pakfire_busy status was checked before and can be omitted)
if (($cgiparams{'ACTION'} eq $Lang::tr{'pakfire upgrade'}) && ($pagemode eq $PM_DEFAULT))
{
	&Header::openbox("100%", "center", $Lang::tr{'pakfire upgrade'});

	print "$Lang::tr{'pakfire updating'}";
	my @output = &General::system_output("/usr/local/bin/pakfire", "update", "--force", "--no-colors");
	%pakfire_status = &Pakfire::status();
	print "<br><br>";

	if (grep(/ERROR/, @output))
	{
		print "<pre>";
		foreach (@output)
		{
			if ($_ =~ /ERROR/)
			{
				print "$_";
			}
		}
		print "</pre>";
		print "<br>";
	}

	if ($pakfire_status{'CoreUpdateAvailable'} eq "yes")
	{
		print "$Lang::tr{'core update'} -- $pakfire_status{'CoreVersion'} -- $Lang::tr{'release'}: $pakfire_status{'Release'} -> $pakfire_status{'AvailableRelease'}<br>";
	}

	if ($pakfire_status{'PakUpdatesAvailable'} > 0)
	{
		my %upgradelist = &Pakfire::dblist("upgrade");
		foreach my $pak (sort keys %upgradelist)
		{
			print "$Lang::tr{'pak update'}: $pak -- $Lang::tr{'version'}: $upgradelist{$pak}{'ProgVersion'} -> $upgradelist{$pak}{'AvailableProgVersion'} -- $Lang::tr{'release'}: $upgradelist{$pak}{'Release'} -> $upgradelist{$pak}{'AvailableRelease'}<br>";
		}
	}

	print <<END;
		<br>
		<table style='width:100%'>
			<tr>
				<td>$Lang::tr{'pakfire confirm upgrades'}</td>
			</tr>
			<tr>
				<td><br></td>
			</tr>
			<tr>
				<td align='center'>
				<form method='post' action='$ENV{'SCRIPT_NAME'}'>
				<input type='hidden' name='FORCE' value='on' />
				<input type='submit' name='ACTION' value='$Lang::tr{'pakfire upgrade'}'/>
				<input type='submit' name='ACTION' value='$Lang::tr{'cancel'}'/>
				</form>
			</td>
			</tr>
		</table>
END
	&Header::closebox();
	&Header::closebigbox();
	&Header::closepage();
	exit;
}

# Show Pakfire main page
my %selected=();
my %checked=();

$selected{"TREE"} = ();
$selected{"TREE"}{"stable"} = "";
$selected{"TREE"}{"testing"} = "";
$selected{"TREE"}{"unstable"} = "";
$selected{"TREE"}{$pakfiresettings{"TREE"}} = "selected";

&Header::openbox("100%", "center", "Pakfire");

print <<END;
	<table id="pfmain">
END
if ($pakfire_status{'RebootRequired'} eq "yes")
{
	print <<END;
		<tr>
			<td colspan='2' style='padding-bottom:20px'>
			<a href='/cgi-bin/shutdown.cgi'>$Lang::tr{'needreboot'}!</a>
			</td>
		</tr>
END
}

print <<END;
		<tr>
			<td class="heading">$Lang::tr{'pakfire system state'}:</td>
			<td class="heading">$Lang::tr{'pakfire upgrades'}</td>
		</tr>

		<tr>
			<td style='padding-top: 15px'>
			<strong>$Lang::tr{'pakfire core update level'}: $pakfire_status{'Release'}</strong>
			<hr>
			<div class="pflist">
				$Lang::tr{'pakfire last update'} $pakfire_status{'LastUpdate'} $Lang::tr{'pakfire ago'}<br>
				$Lang::tr{'pakfire last serverlist update'} $pakfire_status{'LastServerListUpdate'} $Lang::tr{'pakfire ago'}<br>
				$Lang::tr{'pakfire last core list update'} $pakfire_status{'LastCoreListUpdate'} $Lang::tr{'pakfire ago'}<br>
				$Lang::tr{'pakfire last package update'} $pakfire_status{'LastPakListUpdate'} $Lang::tr{'pakfire ago'}
			</div>
			</td>
			<td style='padding-top: 15px'>
			<select class="pflist" style="height: 103px" size="5" disabled>
END

	if ("$pakfire_status{'CoreUpdateAvailable'}" eq "yes") {
		print "<option value=\"core\">$Lang::tr{'core update'} -- $pakfire_status{'CoreVersion'} -- $Lang::tr{'release'}: $pakfire_status{'Release'} -> $pakfire_status{'AvailableRelease'}</option>\n";
	}

	if ($pakfire_status{'PakUpdatesAvailable'} > 0) {
		my %upgradelist = &Pakfire::dblist("upgrade");
		foreach my $pak (sort keys %upgradelist) {
			print "<option value=\"$pak\">$Lang::tr{'pak update'}: $pak -- $Lang::tr{'version'}: $upgradelist{$pak}{'ProgVersion'} -> $upgradelist{$pak}{'AvailableProgVersion'} -- $Lang::tr{'release'}: $upgradelist{$pak}{'Release'} -> $upgradelist{$pak}{'AvailableRelease'}</option>\n";
		}
	}

	print <<END;
			</select>
			</td>
		</tr>
		<tr>
			<form method='post' action='$ENV{'SCRIPT_NAME'}'>
			<td style='padding-bottom: 15px'>
			<input type='submit' name='ACTION' value='$Lang::tr{'pakfire refresh list'}' />
			</td>
			<td style='padding-bottom: 15px'>
END

        if (($pakfire_status{'CoreUpdateAvailable'} eq "yes") || ($pakfire_status{'PakUpdatesAvailable'} > 0))
        {
                print "<input type='submit' name='ACTION' value='$Lang::tr{'pakfire upgrade'}'/>\n";
        } else {
                print "<input disabled type='submit' name='ACTION' value='$Lang::tr{'pakfire upgrade'}'/>\n";
        }

	print <<END;
			</td>
			</form>
		</tr>
		<tr>
			<td class="heading">$Lang::tr{'pakfire available addons'}</td>
			<td class="heading">$Lang::tr{'pakfire installed addons'}</td>
		</tr>
		<form method='post' action='$ENV{'SCRIPT_NAME'}'>
		<tr>
			<td style='padding-top: 15px; padding-bottom: 5px'>
			$Lang::tr{'pakfire install description'}
			</td>
			<td style='padding-top: 15px; padding-bottom: 5px'>
			$Lang::tr{'pakfire uninstall description'}
			</td>
		</tr>
		<tr>
			<td>
			<select name="INSPAKS" class="pflist" style="height:206px" size="10" multiple onchange="document.getElementById('installbutton').disabled=false">
END

	my %notinstalledlist = &Pakfire::dblist("notinstalled");
	foreach my $pak (sort keys %notinstalledlist) {
		print "<option value=\"$pak\">$pak-$notinstalledlist{$pak}{'ProgVersion'}-$notinstalledlist{$pak}{'Release'}</option>\n";
	}

	print <<END;
			</select>
			</td>
			<td>
			<select name="DELPAKS" class="pflist" style="height:206px" size="10" multiple onchange="document.getElementById('removebutton').disabled=false">
END

	my %installedlist = &Pakfire::dblist("installed");
	foreach my $pak (sort keys %installedlist) {
		print "<option value=\"$pak\">$pak-$installedlist{$pak}{'ProgVersion'}-$installedlist{$pak}{'Release'}</option>\n";
	}

	print <<END;
			</select>
			</td>
		</tr>
		<tr>
			<td style='padding-bottom: 5px'>
			<input disabled type='submit' id='installbutton' name='ACTION' value='$Lang::tr{'pakfire install'}'/>
			</td>
			<td style='padding-bottom: 5px'>
			<input disabled type='submit' id='removebutton' name='ACTION' value='$Lang::tr{'remove'}'/>
			</td>
		</tr>
		</form>
	</table>
END

&Header::closebox();
&Header::openbox("100%", "center", "$Lang::tr{'settings'}");

print <<END;
	<form method='POST' action='$ENV{'SCRIPT_NAME'}'>
		<table width='95%'>
			<tr>
				<td align='left' width='45%'>$Lang::tr{'pakfire tree'}</td>
				<td width="55%" align="left">
					<select name="TREE">
						<option value="stable" $selected{"TREE"}{"stable"}>$Lang::tr{'pakfire tree stable'}</option>
						<option value="testing" $selected{"TREE"}{"testing"}>$Lang::tr{'pakfire tree testing'}</option>
						<option value="unstable" $selected{"TREE"}{"unstable"}>$Lang::tr{'pakfire tree unstable'}</option>
					</select>
				</td>
			</tr>
			<tr>
				<td colspan="2">&nbsp;</td>
			</tr>
			<tr>
				<td colspan="2" align="center">
					<input type="submit" name="ACTION" value="$Lang::tr{'save'}" />
				</td>
			</tr>
		</table>
	</form>
END

&Header::closebox();
&Header::closebigbox();
&Header::closepage();

###--- Internal functions ---###

# Check if pakfire is already running (extend test here if necessary)
sub _is_pakfire_busy {
	# Return immediately if lockfile is present
	if(-e "$Pakfire::lockfile") {
		return 1;
	}

	# Check if a PID of a running pakfire instance is found
	# (The system backpipe command is safe, because no user input is computed.)
	my $pakfire_pid = `pidof -s /usr/local/bin/pakfire`;
	chomp($pakfire_pid);

	if($pakfire_pid) {
		return 1;
	}

	# Pakfire isn't running
	return 0;
}

# Send HTTP headers
sub _start_json_output {
	print "Cache-Control: no-cache, no-store\n";
	print "Content-Type: application/json\n";
	print "\n"; # End of HTTP headers
}

# Send HTTP 303 redirect headers to change page mode
# GET is always used to display the redirected page, which will remove already processed POST form data.
# Note: Custom headers must be sent before the HTML output is started by &Header::showhttpheaders().
# If switch_mode is set to true, the global page mode variable ("$pagemode") is also updated immediately.
sub _http_pagemode_redirect {
	my ($mode, $switch_mode) = @_;
	$mode //= $PM_DEFAULT;
	$switch_mode //= 0;

	# Send HTTP redirect with GET parameter
	my $location = "https://$ENV{'SERVER_NAME'}:$ENV{'SERVER_PORT'}$ENV{'SCRIPT_NAME'}?mode=${mode}";
	print "Status: 303 See Other\n";
	print "Location: $location\n";

	# Change global page mode
	if($switch_mode) {
		$pagemode = $mode;
	}
}
