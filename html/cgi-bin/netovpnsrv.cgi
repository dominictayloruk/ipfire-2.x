#!/usr/bin/perl
###############################################################################
#                                                                             #
# IPFire.org - A linux based firewall                                         #
# Copyright (C) 2014  Alexnder Marx                                           #
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

# enable only the following on debugging purpose
#use warnings;
#use CGI::Carp 'fatalsToBrowser';

require '/var/ipfire/general-functions.pl';
require "${General::swroot}/lang.pl";
require "${General::swroot}/header.pl";
require "${General::swroot}/graphs.pl";

my %color = ();
my %mainsettings = ();
&General::readhash("${General::swroot}/main/settings", \%mainsettings);
&General::readhash("/srv/web/ipfire/html/themes/ipfire/include/colors.txt", \%color);

my %vpnsettings = ();
&General::readhasharray("${General::swroot}/vpn/config", \%vpnsettings);

my @vpns=();

# Make list of all IPsec graphs
my %ipsecgraphs = ();
foreach my $key (sort {$vpnsettings{$a}[1] <=> $vpnsettings{$b}[1]} keys %vpnsettings) {
	my $interface_mode = $vpnsettings{$key}[36];
	next unless ($interface_mode);

	$ipsecgraphs{$vpnsettings{$key}[1]} = "${interface_mode}${key}";
}

&Header::showhttpheaders();
&Header::openpage($Lang::tr{'vpn statistic n2n'}, 1, '');
&Header::openbigbox('100%', 'left');

my @vpngraphs = `find /var/log/rrd/collectd/localhost/openvpn-*-n2n/ -not  -path *openvpn-UNDEF* -name *traffic.rrd 2>/dev/null|sort`;
foreach (@vpngraphs){
	if($_ =~ /(.*)\/openvpn-(.*)\/if_octets-traffic.rrd/){
		push(@vpns,$2);
	}
}
if (@vpns || %ipsecgraphs) {
	foreach my $name (sort keys %ipsecgraphs) {
		&Header::openbox('100%', 'center', "$Lang::tr{'ipsec connection'}: $name");
		&Graphs::makegraphbox("netovpnsrv.cgi", "ipsec-$ipsecgraphs{$name}", "day");
		&Header::closebox();
	}

	foreach (@vpns) {
		&Header::openbox('100%', 'center', "$_ $Lang::tr{'graph'}");
		&Graphs::makegraphbox("netovpnsrv.cgi",$_, "day");
		&Header::closebox();
	}
}else{
	print "<center>".$Lang::tr{'no data'}."</center>";
}
my $output = '';

&Header::closebigbox();
&Header::closepage();
