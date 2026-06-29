# Builtin Interfaces: Type Classification (Authoritative)

Total interfaces: 217
Source of truth: `interfaces/builtin/*.go` `registerIface(...)`

## Container/Virtualization Support (10)

`docker-support`, `kubernetes-support`, `kvm`, `lxd-support`, `microceph-support`, `microstack-support`, `multipass-support`, `nomad-support`, `nvidia-drivers-support`, `openvswitch-support`

## D-Bus Service/Provider (21)

`avahi-control`, `bluez`, `cups`, `dbus`, `fwupd`, `location-control`, `maliit`, `media-hub`, `mir`, `modem-manager`, `mpris`, `network-manager`, `ofono`, `online-accounts-service`, `storage-framework-service`, `ubuntu-download-manager`, `udisks2`, `unity8`, `unity8-calendar`, `unity8-contacts`, `upower-observe`

## D-Bus/IPC Client (16)

`accounts-service`, `autopilot-introspection`, `avahi-observe`, `calendar-service`, `contacts-service`, `desktop-legacy`, `gconf`, `gsettings`, `location-observe`, `login-session-control`, `login-session-observe`, `network-manager-observe`, `screen-inhibit-control`, `screencast-legacy`, `time-control`, `timezone-control`

## Daemon/Socket Client (12)

`cups-control`, `docker`, `jack1`, `libvirt`, `lxd`, `microceph`, `microovn`, `openvswitch`, `pcscd`, `pipewire`, `podman`, `pulseaudio`

## Desktop/Graphics/Media Integration (20)

`audio-playback`, `audio-record`, `browser-support`, `camera`, `cuda-driver-libs`, `desktop`, `display-control`, `egl-driver-libs`, `gbm-driver-libs`, `media-control`, `nvidia-video-driver-libs`, `opengl`, `opengl-driver-libs`, `opengles-driver-libs`, `thumbnailer-service`, `unity7`, `vulkan-driver-libs`, `wayland`, `x11`, `xdg-portal-permission-store`

## Filesystem/Mount Interface (15)

`bool-file`, `cifs-mount`, `classic-support`, `content`, `desktop-launch`, `home`, `mount-control`, `mount-observe`, `nfs-mount`, `personal-files`, `raw-volume`, `removable-media`, `ros-opt-data`, `shared-memory`, `system-files`

## Hardware Device Access (55)

`accel`, `acrn-support`, `adb-support`, `allegro-vcu`, `alsa`, `auditd-support`, `block-devices`, `checkbox-support`, `core-support`, `custom-device`, `device-buttons`, `devlxd`, `dm-crypt`, `dm-multipath`, `dsp`, `dvb`, `firmware-updater-support`, `fpga`, `framebuffer`, `fuse-support`, `gpio`, `gpio-chardev`, `greengrass-support`, `hidraw`, `i2c`, `iio`, `intel-mei`, `intel-qat`, `iscsi-initiator`, `joystick`, `kernel-crypto-api`, `kernel-module-load`, `mediatek-accel`, `optical-drive`, `posix-mq`, `pwm`, `qualcomm-ipc-router`, `raw-input`, `raw-usb`, `remoteproc`, `ros-snapd-support`, `scsi-generic`, `serial-port`, `shutdown`, `spi`, `steam-support`, `tee`, `tpm`, `uhid`, `uinput`, `uio`, `usb-gadget`, `userns`, `vcio`, `xilinx-dma`

## Identity/Credentials/Secrets (11)

`account-control`, `gpg-keys`, `gpg-public-keys`, `kerberos-tickets`, `password-manager-service`, `pkcs11`, `polkit`, `polkit-agent`, `ssh-keys`, `ssh-public-keys`, `u2f-devices`

## Network/Netlink Interface (13)

`can-bus`, `netlink-audit`, `netlink-connector`, `netlink-driver`, `network`, `network-bind`, `network-control`, `network-observe`, `network-setup-control`, `network-setup-observe`, `network-status`, `ppp`, `ptp`

## Observability/Diagnostics (13)

`appstream-metadata`, `hardware-observe`, `hardware-random-observe`, `juju-client-observe`, `kernel-module-observe`, `log-observe`, `physical-memory-observe`, `snap-refresh-observe`, `system-backup`, `system-observe`, `system-packages-doc`, `system-source-code`, `system-trace`

## Snapd/Policy Management (8)

`confdb`, `daemon-notify`, `snap-fde-control`, `snap-interfaces-requests-control`, `snap-refresh-control`, `snap-themes-control`, `snapd-control`, `ubuntu-pro-control`

## System Control/Privileged Capability (22)

`bluetooth-control`, `broadcom-asic-control`, `cpu-control`, `dcdbas-control`, `firewall-control`, `gpio-control`, `gpio-memory-control`, `hardware-random-control`, `hostname-control`, `hugepages-control`, `io-ports-control`, `ion-memory-control`, `kernel-firmware-control`, `kernel-module-control`, `locale-control`, `nvme-control`, `packagekit-control`, `physical-memory-control`, `power-control`, `process-control`, `sd-control`, `timeserver-control`

## Test/Meta Interface (1)

`empty`

