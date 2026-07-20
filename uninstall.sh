#!/bin/sh
set -eu

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
bin_home=${XDG_BIN_HOME:-"$HOME/.local/bin"}
config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}

rm -rf "$data_home/token-quota-widget"
rm -f "$bin_home/token-quota-widget"
rm -f "$data_home/applications/token-quota-widget.desktop"
rm -f "$config_home/autostart/token-quota-widget.desktop"

printf '%s\n' "Token 额度组件已卸载。"
printf '%s\n' "窗口设置仍保留在：$config_home/token-quota-widget"
