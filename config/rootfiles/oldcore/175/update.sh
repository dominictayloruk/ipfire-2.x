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
# Copyright (C) 2023 IPFire-Team <info@ipfire.org>.                        #
#                                                                          #
############################################################################
#
. /opt/pakfire/lib/functions.sh
/usr/local/bin/backupctrl exclude >/dev/null 2>&1

core=175

exit_with_error() {
    # Set last succesfull installed core.
    echo $(($core-1)) > /opt/pakfire/db/core/mine
    # force fsck at next boot, this may fix free space on xfs
    touch /forcefsck
    # don't start pakfire again at error
    killall -KILL pak_update
    /usr/bin/logger -p syslog.emerg -t ipfire \
	"core-update-${core}: $1"
    exit $2
}

# Remove old core updates from pakfire cache to save space...
for (( i=1; i<=$core; i++ )); do
	rm -f /var/cache/pakfire/core-upgrade-*-$i.ipfire
done

# Stop services
/etc/rc.d/init.d/apache stop
/etc/rc.d/init.d/ntp stop
/etc/rc.d/init.d/sshd stop
/etc/rc.d/init.d/squid stop
/etc/rc.d/init.d/unbound stop
/etc/rc.d/init.d/suricata stop

KVER="xxxKVERxxx"

# Backup uEnv.txt if exist
if [ -e /boot/uEnv.txt ]; then
    cp -vf /boot/uEnv.txt /boot/uEnv.txt.org
fi

# Do some sanity checks prior to the kernel update
case $(uname -r) in
    *-ipfire*)
	# Ok.
	;;
    *)
	exit_with_error "ERROR cannot update. No IPFire Kernel." 1
	;;
esac

# Check diskspace on root
ROOTSPACE=$( df / -Pk | sed "s| * | |g" | cut -d" " -f4 | tail -n 1 )

if [ $ROOTSPACE -lt 100000 ]; then
    exit_with_error "ERROR cannot update because not enough free space on root." 2
    exit 2
fi

# Remove the old kernel
rm -rvf \
	/boot/System.map-* \
	/boot/config-* \
	/boot/ipfirerd-* \
	/boot/initramfs-* \
	/boot/vmlinuz-* \
	/boot/uImage-* \
	/boot/zImage-* \
	/boot/uInit-* \
	/boot/dtb-* \
	/lib/modules

# Remove any dropped add-ons, if installed
for package in powertop python3-attr python3-pkgconfig; do
        if [ -e "/opt/pakfire/db/installed/meta-${package}" ]; then
		stop_service "${package}"
		for i in $(</opt/pakfire/db/rootfiles/${package}); do
			rm -rfv "/${i}"
		done
        fi
        rm -f "/opt/pakfire/db/installed/meta-${package}"
        rm -f "/opt/pakfire/db/meta/meta-${package}"
        rm -f "/opt/pakfire/db/rootfiles/${package}"
done

# Extract files
extract_files

# Remove files
rm -rvf \
	/etc/rc.d/init.d/lvmetad \
	/etc/rc.d/rcsysinit.d/S09lvmetad \
	/lib/firmware/liquidio/lio_23xx_vsw.bin \
	/usr/lib/libbind9-9.16.38.so \
	/usr/lib/libdns-9.16.38.so \
	/usr/lib/libirs-9.16.38.so \
	/usr/lib/libisc-9.16.38.so \
	/usr/lib/libisccc-9.16.38.so \
	/usr/lib/libisccfg-9.16.38.so \
	/usr/lib/libns-9.16.38.so \
	/usr/lib/libqpdf.so.28* \
	/var/ipfire/menu.d/EX-addonsvc.menu \
	/var/ipfire/menu.d/EX-asterisk.menu \
	/var/ipfire/menu.d/EX-bluetooth.menu

# update linker config
ldconfig

# Update Language cache
/usr/local/bin/update-lang-cache

# Filesytem cleanup
/usr/local/bin/filesystem-cleanup

# Fix permissions of /var/log/pakfire.log
chmod -v 644 /var/log/pakfire.log

# Apply local configuration to sshd_config
/usr/local/bin/sshctrl

# Reload firewall to fix #13088 as fast as possible
/etc/rc.d/init.d/firewall reload

# Start services
if grep -q "ENABLE_IDS=on" /var/ipfire/suricata/settings; then
	/etc/rc.d/init.d/suricata start
fi
/etc/rc.d/init.d/unbound start
/etc/rc.d/init.d/apache start
/etc/rc.d/init.d/ntp start
if grep -q "ENABLE_SSH=on" /var/ipfire/remote/settings; then
	/etc/init.d/sshd start
fi
if [ -f /var/ipfire/proxy/enable ]; then
	/etc/init.d/squid start
fi

# Regenerate all initrds
dracut --regenerate-all --force
case "$(uname -m)" in
	aarch64)
		mkimage -A arm64 -T ramdisk -C lzma -d /boot/initramfs-${KVER}-ipfire.img /boot/uInit-${KVER}-ipfire
		# dont remove initramfs because grub need this to boot.
		;;
esac

# remove lm_sensor config after collectd was started
# to re-search sensors at next boot with updated kernel
rm -f  /etc/sysconfig/lm_sensors

# Upadate Kernel version in uEnv.txt
if [ -e /boot/uEnv.txt ]; then
    sed -i -e "s/KVER=.*/KVER=${KVER}/g" /boot/uEnv.txt
fi

# Call user update script (needed for some ARM boards)
if [ -e /boot/pakfire-kernel-update ]; then
    /boot/pakfire-kernel-update ${KVER}
fi

## Add providers legacy default line to n2n client config files
# Check if ovpnconfig exists and is not empty
if [ -s /var/ipfire/ovpn/ovpnconfig ]; then
       # Identify all n2n connections
       for y in $(awk -F',' '/net/ { print $3 }' /var/ipfire/ovpn/ovpnconfig); do
           # Add the legacy option to all N2N client conf files
		if [ $(grep -c "Open VPN Client Config" /var/ipfire/ovpn/n2nconf/${y}/${y}.conf) -eq 1 ] ; then
			if [ $(grep -c "providers legacy default" /var/ipfire/ovpn/n2nconf/${y}/${y}.conf) -eq 0 ] ; then
				echo "providers legacy default" >> /var/ipfire/ovpn/n2nconf/${y}/${y}.conf
			fi
		fi
       done
fi

## Add unique_subject = yes to vpn index.txt.attr file
echo "unique_subject = yes" > /var/ipfire/certs/index.txt.attr

# This update needs a reboot...
touch /var/run/need_reboot

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
