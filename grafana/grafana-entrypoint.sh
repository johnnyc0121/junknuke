#!/bin/sh
INFLUXDB_TOKEN=$(grep 'token =' /etc/influxdb2/influx-configs | cut -d'"' -f2 | head -n1)

if [ -z "$INFLUXDB_TOKEN" ]; then
  echo "WARNING: Could not read InfluxDB token from /etc/influxdb2/influx-configs"
else
  echo "InfluxDB token loaded from config volume."
fi

mkdir -p /etc/grafana/provisioning/datasources

cat > /etc/grafana/provisioning/datasources/datasource.yml <<EOF
apiVersion: 1
datasources:
  - name: InfluxDB2
    type: influxdb
    access: proxy
    url: "${INFLUXDB_URL}"
    basicAuth: false
    isDefault: true
    version: 2
    jsonData:
      version: Flux
      organization: ${INFLUXDB_ORG}
      defaultBucket: ${INFLUXDB_BUCKET}
      pdcInjected: false
      tlsSkipVerify: true
    secureJsonData:
      token: "${INFLUXDB_TOKEN}"
EOF

echo "Grafana datasource config written."
exec /run.sh
