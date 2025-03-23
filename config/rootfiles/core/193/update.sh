#!/bin/bash
############################################################################
#                                                                          #
# This file is part of the IPFire Firewall.                                #
#                                                                          #
# IPFire is free software; you can redistribute it and/or modify           #
# it under the terms of the GNU General Public License as published by     #
# the Free Software Foundation; either version 3 of the License, or        #
# (at your option) any later version.                                      #
#                                                                          #
# IPFire is distributed in the hope that it will be useful,                #
# but WITHOUT ANY WARRANTY; without even the implied warranty of           #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the            #
# GNU General Public License for more details.                             #
#                                                                          #
# You should have received a copy of the GNU General Public License        #
# along with IPFire; if not, write to the Free Software                    #
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307 USA #
#                                                                          #
# Copyright (C) 2025 IPFire-Team <info@ipfire.org>.                        #
#                                                                          #
############################################################################
#
. /opt/pakfire/lib/functions.sh
/usr/local/bin/backupctrl exclude >/dev/null 2>&1

core=193

# Remove old core updates from pakfire cache to save space...
for (( i=1; i<=$core; i++ )); do
	rm -f /var/cache/pakfire/core-upgrade-*-$i.ipfire
done

# Stop services
/etc/init.d/ipsec stop
/etc/init.d/squid stop

# Remove files
rm -rfv \
	/usr/share/vim/vim91 \
	/lib/firmware/ath11k/WCN6750/hw1.0/wpss.b00 \
	/lib/firmware/ath11k/WCN6750/hw1.0/wpss.b01 \
	/lib/firmware/ath11k/WCN6750/hw1.0/wpss.b02 \
	/lib/firmware/ath11k/WCN6750/hw1.0/wpss.b03 \
	/lib/firmware/ath11k/WCN6750/hw1.0/wpss.b04 \
	/lib/firmware/ath11k/WCN6750/hw1.0/wpss.b05 \
	/lib/firmware/ath11k/WCN6750/hw1.0/wpss.b06 \
	/lib/firmware/ath11k/WCN6750/hw1.0/wpss.b07 \
	/lib/firmware/ath11k/WCN6750/hw1.0/wpss.b08 \
	/lib/firmware/intel/ice/ddp/ice-1.3.36.0.pkg \
	/lib/firmware/intel/ice/ddp-comms/ice_comms-1.3.45.0.pkg \
	/lib/firmware/intel/ice/ddp-wireless_edge/ice_wireless_edge-1.3.13.0.pkg

# Extract files
extract_files

# update linker config
ldconfig

# Update Language cache
/usr/local/bin/update-lang-cache

# Filesytem cleanup
/usr/local/bin/filesystem-cleanup

# Remove any entry for ABUSECH_BOTNETC2 from the ipblocklist modified file
# and the associated ipblocklist files from the /var/lib/ipblocklist directory
sed -i '/ABUSECH_BOTNETC2=/d' /var/ipfire/ipblocklist/modified
if [ -e /var/lib/ipblocklist/ABUSECH_BOTNETC2.conf ]; then
	rm /var/lib/ipblocklist/ABUSECH_BOTNETC2.conf
fi

# Apply local configuration to sshd_config

# Start services
/etc/init.d/apache restart
/etc/init.d/ipsec start
/etc/init.d/squid start
/etc/init.d/vnstat restart

# Build initial ramdisks for updated intel-microcode
case "$(uname -m)" in
	x86_64)
		dracut --regenerate-all --force
		;;
esac

# This update needs a reboot...
#touch /var/run/need_reboot

# Finish
/etc/init.d/fireinfo start
sendprofile

# Update grub config to display new core version
if [ -e /boot/grub/grub.cfg ]; then
	grub-mkconfig -o /boot/grub/grub.cfg
fi

sync

# Don't report the exitcode last command
exit 0
