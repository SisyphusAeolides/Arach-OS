#!/usr/bin/env bash
set -euo pipefail

key=/usr/share/pacman/keyrings/sisyphus-repo.asc
fingerprint=2A02745D8C2C03AE7F95BCEA8136EB9238213447

pacman-key --init
pacman-key --add "$key"
pacman-key --lsign-key "$fingerprint"
systemctl enable NetworkManager.service
systemctl enable sddm.service
