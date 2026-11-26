#!/bin/zsh
set -eu
root="$HOME/.dotnet"
dotnet_bin=$(command -v dotnet || true)
if [[ -x "$root/dotnet" ]]; then dotnet_bin="$root/dotnet"; fi
if [[ -z "$dotnet_bin" ]] || ! "$dotnet_bin" --list-sdks | awk -F. '$1>=8 {found=1} END {exit !found}' || ! "$dotnet_bin" --list-runtimes | grep -q 'Microsoft.NETCore.App 8\.'; then
  echo '正在从 Microsoft 安装 .NET 8 SDK（当前用户）…'
  installer=$(mktemp)
  trap 'rm -f "$installer"' EXIT
  curl --fail --location --silent --show-error https://dot.net/v1/dotnet-install.sh --output "$installer"
  /bin/bash "$installer" --channel 8.0 --install-dir "$root" --no-path
  dotnet_bin="$root/dotnet"
fi
if [[ "$dotnet_bin" == "$root/dotnet" ]]; then export DOTNET_ROOT="$root"; fi
"$dotnet_bin" tool update --tool-path "$root/tools" NwcIO.Cli --version 0.17.0
"$root/tools/nwcio" --help >/dev/null
echo 'NWD 转换器已就绪。工作台后台将自动处理等待中的模型。'
