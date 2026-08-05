#!/usr/bin/env bash

iso_name="arachos"
iso_label="ARACHOS"
iso_publisher="ArachOS <https://github.com/SisyphusAeolides/ArachOS>"
iso_application="ArachOS ArchISO installer"
iso_version="${ARACHOS_ISO_VERSION:?set ARACHOS_ISO_VERSION to an immutable release version}"
install_dir="arachos"
buildmodes=('iso')
bootmodes=('bios.syslinux.mbr' 'uefi-x64.systemd-boot.esp')
arch="x86_64"
pacman_conf="pacman.conf"
file_permissions=(
  ["/root/customize_airootfs.sh"]="0:0:755"
)
