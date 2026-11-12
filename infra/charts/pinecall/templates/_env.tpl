{{/* What each process of the runtime reads from its environment. */}}

{{/* What the gateway reads: the database, the signal, the vault, the operator's key, its own signing key, the LiveKit pair,
     the names, and where recordings are. A worker gets none of the first four (pinecall.workerEnv): it
     has no database, and a worker runs the vendors' plugins and decodes a caller's audio. */}}
{{- define "pinecall.env" -}}
- name: DATABASE_URL
  valueFrom: { secretKeyRef: { name: {{ .Values.postgres.appSecret }}, key: uri } }
- name: PINECALL_REDIS_URL
  valueFrom: { secretKeyRef: { name: pinecall, key: PINECALL_REDIS_URL } }
- name: PINECALL_VAULT_KEY
  valueFrom: { secretKeyRef: { name: pinecall, key: PINECALL_VAULT_KEY } }
- name: PINECALL_OPS_KEY
  valueFrom: { secretKeyRef: { name: pinecall, key: PINECALL_OPS_KEY } }
- name: PINECALL_TOKEN_KEY
  valueFrom: { secretKeyRef: { name: pinecall, key: PINECALL_TOKEN_KEY } }
- name: PINECALL_PRODUCTION_FLEET_KEY
  valueFrom: { secretKeyRef: { name: pinecall-fleets, key: production } }
- name: PINECALL_SANDBOX_FLEET_KEY
  valueFrom: { secretKeyRef: { name: pinecall-fleets, key: sandbox } }
- name: LIVEKIT_API_KEY
  valueFrom: { secretKeyRef: { name: pinecall, key: LIVEKIT_API_KEY } }
- name: LIVEKIT_API_SECRET
  valueFrom: { secretKeyRef: { name: pinecall, key: LIVEKIT_API_SECRET } }
- name: LIVEKIT_PUBLIC_URL
  value: wss://{{ required "domain" .Values.domain }}
- name: PINECALL_DOMAIN
  value: {{ .Values.domain | quote }}
{{- with .Values.pages }}
- name: PINECALL_PAGES_DOMAIN
  value: {{ . | quote }}
{{- end }}
- name: PINECALL_GATEWAY_URL
  value: http://pinecall-gateway:8080
{{- /* A cluster's Postgres archives through its operator and keeps no spool: named empty, the doctor's
       `archive` line reads the archiver alone instead of listing a directory the app's role may not. */}}
- name: PINECALL_WAL_SPOOL
  value: ""
{{- with .Values.envs }}{{ if .production.sipDomain }}
- name: PINECALL_SIP_DOMAIN
  value: {{ .production.sipDomain | quote }}
- name: PINECALL_SANDBOX_SIP_DOMAIN
  value: {{ required "envs.sandbox.sipDomain" .sandbox.sipDomain | quote }}
{{- end }}{{ end }}
{{ include "pinecall.recordingsEnv" . }}
{{- end -}}

{{/* A worker of an env: its LiveKit and the pair it joins it with, its fleet, its seats, its key,
     the gateway it knocks at, its health port, and where recordings are. No database, no vault, no
     operator's key: a worker asks the gateway for what a call needs. */}}
{{- define "pinecall.workerEnv" -}}
- name: LIVEKIT_URL
  value: ws://pinecall-livekit-{{ .env }}:7880
- name: LIVEKIT_API_KEY
  valueFrom: { secretKeyRef: { name: pinecall, key: LIVEKIT_API_KEY } }
- name: LIVEKIT_API_SECRET
  valueFrom: { secretKeyRef: { name: pinecall, key: LIVEKIT_API_SECRET } }
- name: PINECALL_GATEWAY_URL
  value: http://pinecall-gateway:8080
- name: PINECALL_FLEET
  value: {{ (index .root.Values.envs .env).fleet | quote }}
- name: PINECALL_MAX_JOBS
  value: {{ .seats | quote }}
- name: PINECALL_WORKER_KEY
  valueFrom: { secretKeyRef: { name: pinecall-fleets, key: {{ .env }} } }
- name: PINECALL_WORKER_HTTP_HOST
  value: 0.0.0.0
- name: PINECALL_WORKER_HTTP_PORT
  value: "8082"
{{ include "pinecall.recordingsEnv" .root }}
{{- end -}}

{{/* What the nightly retention reads: the database, the vault (a recording's key), and where recordings are. */}}
{{- define "pinecall.retentionEnv" -}}
- name: DATABASE_URL
  valueFrom: { secretKeyRef: { name: {{ .Values.postgres.secret }}, key: uri } }
- name: PINECALL_VAULT_KEY
  valueFrom: { secretKeyRef: { name: pinecall, key: PINECALL_VAULT_KEY } }
{{ include "pinecall.recordingsEnv" . }}
{{- end -}}

{{/* Where a recording is kept: the pod's disk, and the object store it moves to when one is named. */}}
{{- define "pinecall.recordingsEnv" -}}
- name: PINECALL_RECORDINGS
  value: /var/lib/pinecall/recordings
{{- with .Values.store }}{{ if .bucket }}
- name: PINECALL_S3_ENDPOINT
  value: {{ required "store.endpoint" .endpoint | quote }}
- name: PINECALL_S3_REGION
  value: {{ required "store.region" .region | quote }}
- name: PINECALL_S3_ACCESS_KEY_ID
  valueFrom: { secretKeyRef: { name: pinecall, key: PINECALL_S3_ACCESS_KEY_ID } }
- name: PINECALL_RECORDINGS_BUCKET
  value: {{ .bucket | quote }}
- name: PINECALL_S3_SECRET_ACCESS_KEY
  valueFrom: { secretKeyRef: { name: pinecall, key: PINECALL_S3_SECRET_ACCESS_KEY } }
{{- end }}{{ end }}
{{- end -}}

{{/* What reaches both envs' LiveKits (the gateways, the jobs): production's and the sandbox's. */}}
{{- define "pinecall.livekits" -}}
- name: LIVEKIT_URL
  value: ws://pinecall-livekit-production:7880
- name: LIVEKIT_SANDBOX_URL
  value: ws://pinecall-livekit-sandbox:7880
{{- end -}}
