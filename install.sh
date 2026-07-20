#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
bin_home=${XDG_BIN_HOME:-"$HOME/.local/bin"}
app_home="$data_home/token-quota-widget"
bin_path="$bin_home/token-quota-widget"
desktop_dir="$data_home/applications"
desktop_path="$desktop_dir/token-quota-widget.desktop"
python_bin=$(command -v python3)

"$python_bin" -c "import tkinter" 2>/dev/null || {
    printf '%s\n' "未找到 Python Tk 支持，请先安装 python3-tk。" >&2
    exit 1
}

install -d -m 700 "$app_home/token_quota_widget"
install -d "$bin_home" "$desktop_dir"
for source_file in "$script_dir"/token_quota_widget/*.py; do
    install -m 644 "$source_file" "$app_home/token_quota_widget/"
done
install -m 644 "$script_dir/README.md" "$script_dir/LICENSE" "$app_home/"

escaped_app_home=$(printf '%s' "$app_home" | sed 's/[&|]/\\&/g')
escaped_python=$(printf '%s' "$python_bin" | sed 's/[&|]/\\&/g')
escaped_bin_path=$(printf '%s' "$bin_path" | sed 's/[&|]/\\&/g')

sed \
    -e "s|@APP_HOME@|$escaped_app_home|g" \
    -e "s|@PYTHON@|$escaped_python|g" \
    "$script_dir/token-quota-widget.in" >"$bin_path"
chmod 755 "$bin_path"

sed "s|@BIN_PATH@|$escaped_bin_path|g" \
    "$script_dir/token-quota-widget.desktop.in" >"$desktop_path"
chmod 644 "$desktop_path"

if [ "${1:-}" = "--autostart" ]; then
    autostart_dir="${XDG_CONFIG_HOME:-"$HOME/.config"}/autostart"
    install -d "$autostart_dir"
    install -m 644 "$desktop_path" "$autostart_dir/token-quota-widget.desktop"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$desktop_dir" >/dev/null 2>&1 || true
fi

printf '%s\n' "已安装：$desktop_path"
printf '%s\n' "可从应用菜单启动“Token 额度”，或运行：$bin_path"
