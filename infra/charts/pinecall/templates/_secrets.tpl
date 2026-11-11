{{/* How the cloud's secret store is named to External Secrets. */}}

{{/* A ClusterSecretStore's provider, as the values' `secrets.provider` gives it whole: never
     guessed, so a values file that names none fails here rather than at the first sync. */}}
{{- define "pinecall.secretProvider" -}}
{{- if not .provider }}
{{- fail "secrets.provider: the secret store's provider block (gcpsm, aws, vault…), as External Secrets takes it" }}
{{- end }}
provider:
  {{- toYaml .provider | nindent 2 }}
{{- end -}}
