#!/usr/bin/env bash
# The Gateway API's standard channel applied to a cluster: one release's definitions, refused
# unless the file is the one its hash names. Run by Terraform (modules/controllers) with CLUSTER,
# REGION, RELEASE and SHA256; a kubeconfig of its own, thrown away, so no context of the operator's
# is changed.
set -euo pipefail
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

curl -fsSL -o "$work/standard-install.yaml" \
  "https://github.com/kubernetes-sigs/gateway-api/releases/download/$RELEASE/standard-install.yaml"
found=$(shasum -a 256 "$work/standard-install.yaml" | cut -d' ' -f1)
[ "$found" = "$SHA256" ] || {
  echo "gateway-api $RELEASE: standard-install.yaml is $found, not $SHA256: nothing was applied" >&2
  exit 1
}
aws eks update-kubeconfig --name "$CLUSTER" --region "$REGION" --kubeconfig "$work/kubeconfig" >/dev/null
kubectl --kubeconfig "$work/kubeconfig" apply --server-side -f "$work/standard-install.yaml"
