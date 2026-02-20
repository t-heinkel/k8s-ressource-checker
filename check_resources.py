#!/usr/bin/env python3
"""
Resource usage checker for Kubernetes Deployments and StatefulSets.
Outputs per-pod CPU/memory requests and limits to a CSV file.
"""

import csv
import argparse
from kubernetes import client, config


def parse_cpu(value: str) -> float:
    """Convert CPU string to millicores."""
    if not value:
        return 0.0
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000


def parse_memory(value: str) -> float:
    """Convert memory string to MiB."""
    if not value:
        return 0.0
    units = {"Ki": 1/1024, "Mi": 1, "Gi": 1024, "Ti": 1024**2, "k": 1/1024, "M": 1, "G": 1024}
    for suffix, factor in units.items():
        if value.endswith(suffix):
            return float(value[:-len(suffix)]) * factor
    return float(value) / (1024**2)


def aggregate_containers(containers):
    """Sum resource requests and limits across all containers in a pod spec."""
    req_cpu = req_mem = lim_cpu = lim_mem = 0.0
    for c in containers:
        res = c.resources or client.V1ResourceRequirements()
        req = res.requests or {}
        lim = res.limits or {}
        req_cpu += parse_cpu(req.get("cpu"))
        req_mem += parse_memory(req.get("memory"))
        lim_cpu += parse_cpu(lim.get("cpu"))
        lim_mem += parse_memory(lim.get("memory"))
    return req_cpu, req_mem, lim_cpu, lim_mem


def collect_workloads(namespace: str = None) -> list[dict]:
    apps_v1 = client.AppsV1Api()
    rows = []

    if namespace:
        deployments  = apps_v1.list_namespaced_deployment(namespace).items
        statefulsets = apps_v1.list_namespaced_stateful_set(namespace).items
    else:
        deployments  = apps_v1.list_deployment_for_all_namespaces().items
        statefulsets = apps_v1.list_stateful_set_for_all_namespaces().items

    for kind, workloads in [("Deployment", deployments), ("StatefulSet", statefulsets)]:
        for w in workloads:
            containers = w.spec.template.spec.containers or []
            req_cpu, req_mem, lim_cpu, lim_mem = aggregate_containers(containers)
            rows.append({
                "kind":               kind,
                "namespace":          w.metadata.namespace,
                "name":               w.metadata.name,
                "replicas":           w.spec.replicas or 0,
                "req_cpu_per_pod_m":  round(req_cpu, 1),
                "req_mem_per_pod_mi": round(req_mem, 1),
                "lim_cpu_per_pod_m":  round(lim_cpu, 1),
                "lim_mem_per_pod_mi": round(lim_mem, 1),
            })

    return rows


def write_csv(rows: list[dict], output_file: str):
    if not rows:
        print("No workloads found.")
        return
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Written {len(rows)} rows to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Export K8s resource requests/limits per pod to CSV.")
    parser.add_argument("-n", "--namespace", default=None, help="Limit to a specific namespace (default: all)")
    parser.add_argument("--filter", default=None, help="Only include workloads whose name/namespace contains this string")
    parser.add_argument("-o", "--output", default="resources.csv", help="Output CSV file (default: resources.csv)")
    parser.add_argument("--kubeconfig", default=None, help="Path to kubeconfig (default: ~/.kube/config or in-cluster)")
    args = parser.parse_args()

    try:
        config.load_kube_config(config_file=args.kubeconfig)
    except config.ConfigException:
        config.load_incluster_config()

    rows = collect_workloads(namespace=args.namespace)

    if args.filter:
        f = args.filter.lower()
        rows = [r for r in rows if f in r["name"].lower() or f in r["namespace"].lower()]

    rows.sort(key=lambda r: (r["namespace"], r["kind"], r["name"]))
    write_csv(rows, args.output)


if __name__ == "__main__":
    main()
