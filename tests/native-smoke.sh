#!/usr/bin/env bash
set -euo pipefail

bench_dir="${1:?Uso: native-smoke.sh /ruta/frappe-bench sitio.local}"
site="${2:?Uso: native-smoke.sh /ruta/frappe-bench sitio.local}"
app_root="$(cd "$(dirname "$0")/.." && pwd)"
linked_app=0
apps_txt_added=0

cd "$bench_dir"
if ! bench --site "$site" list-apps | grep -qx erpnext; then
  echo "ERPNext no está instalado en $site" >&2
  exit 1
fi

cleanup() {
  bench --site "$site" uninstall-app govp_erpnext --yes --no-backup >/dev/null 2>&1 || true
  if [ "$linked_app" = 1 ]; then
    ./env/bin/pip uninstall -y govp-for-erpnext >/dev/null 2>&1 || true
    find apps/govp_erpnext -type l -delete 2>/dev/null || true
  fi
  if [ "$apps_txt_added" = 1 ]; then
    grep -vxF govp_erpnext sites/apps.txt > sites/apps.txt.govp.tmp || true
    mv sites/apps.txt.govp.tmp sites/apps.txt
  fi
}
trap cleanup EXIT

if [ ! -e apps/govp_erpnext ]; then
  ln -s "$app_root" apps/govp_erpnext
  linked_app=1
fi
./env/bin/pip install -e apps/govp_erpnext
if ! grep -qxF govp_erpnext sites/apps.txt; then
  printf '%s\n' govp_erpnext >> sites/apps.txt
  apps_txt_added=1
fi
bench --site "$site" install-app govp_erpnext
bench --site "$site" migrate
bench --site "$site" run-tests --app govp_erpnext
bench --site "$site" list-apps | grep -qx govp_erpnext

echo "PASS: GOVP for ERPNext instalado, migrado y probado en $site"
