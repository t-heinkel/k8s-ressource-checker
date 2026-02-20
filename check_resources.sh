#!/usr/bin/env bash
# check_resources.sh
# Collects CPU/memory requests and limits per pod for all Deployments and StatefulSets.
# Output: resources.csv
#
# Usage:
#   ./check_resources.sh                    # all namespaces
#   ./check_resources.sh -n sysdig          # specific namespace
#   ./check_resources.sh -n sysdig -o out.csv

set -euo pipefail

NAMESPACE=""
OUTPUT="resources.csv"

while getopts "n:o:" opt; do
  case $opt in
    n) NAMESPACE="$OPTARG" ;;
    o) OUTPUT="$OPTARG" ;;
    *) echo "Usage: $0 [-n namespace] [-o output.csv]"; exit 1 ;;
  esac
done

if [ -n "$NAMESPACE" ]; then
  NS_FLAG="-n $NAMESPACE"
else
  NS_FLAG="--all-namespaces"
fi

echo "kind,namespace,name,replicas,req_cpu_per_pod_m,req_mem_per_pod_mi,lim_cpu_per_pod_m,lim_mem_per_pod_mi" > "$OUTPUT"

for KIND in deployment statefulset; do
  kubectl get "$KIND" $NS_FLAG -o json | \
  python3 -c "
import json, sys

def parse_cpu(v):
    if not v: return 0.0
    if v.endswith('m'): return float(v[:-1])
    return float(v) * 1000

def parse_mem(v):
    if not v: return 0.0
    for suffix, factor in [('Ki', 1/1024), ('Mi', 1), ('Gi', 1024), ('Ti', 1024**2), ('k', 1/1024), ('M', 1), ('G', 1024)]:
        if v.endswith(suffix): return float(v[:-len(suffix)]) * factor
    return float(v) / (1024**2)

data = json.load(sys.stdin)
kind = '$KIND'.capitalize()
for item in data['items']:
    ns   = item['metadata']['namespace']
    name = item['metadata']['name']
    reps = item['spec'].get('replicas', 0)
    containers = item['spec']['template']['spec'].get('containers', [])
    rc = rm = lc = lm = 0.0
    for c in containers:
        res = c.get('resources', {})
        req = res.get('requests', {})
        lim = res.get('limits', {})
        rc += parse_cpu(req.get('cpu'))
        rm += parse_mem(req.get('memory'))
        lc += parse_cpu(lim.get('cpu'))
        lm += parse_mem(lim.get('memory'))
    print(f'{kind},{ns},{name},{reps},{rc:.1f},{rm:.1f},{lc:.1f},{lm:.1f}')
" >> "$OUTPUT"
done

echo "Done. Written to $OUTPUT"
