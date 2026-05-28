#!/bin/bash

GRAFANA_URL="http://localhost:3000"
USERNAME="admin"
PASSWORD=""
OUTPUT_DIR="./dashboards_export"

mkdir -p "${OUTPUT_DIR}"

for uid in $(curl -sk -u "${USERNAME}:${PASSWORD}" "${GRAFANA_URL}/api/search" | jq '.[].uid' -r); do
  curl -sk -u "${USERNAME}:${PASSWORD}" "${GRAFANA_URL}/api/dashboards/uid/$uid" | jq '.dashboard | del(.id)' | jq . > "${OUTPUT_DIR}/${uid}.json"
done

echo "All dashboards saved to ${OUTPUT_DIR}"
