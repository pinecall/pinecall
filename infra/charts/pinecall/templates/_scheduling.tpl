{{/* Which image a pod runs and which node it lands on. */}}

{{/* The runtime's image: the commit it was built from, and the registry's digest of it when one is given. */}}
{{- define "pinecall.image" -}}
{{ required "image.repository" .Values.image.repository }}:{{ required "image.tag: the commit the runtime image was built from" .Values.image.tag }}{{ with .Values.image.digest }}@{{ . }}{{ end }}
{{- end -}}

{{/* A world's media node: its pool's selector and the toleration of its taint (modules/gke). */}}
{{- define "pinecall.onMedia" -}}
nodeSelector: { pinecall.io/pool: media-{{ . }} }
tolerations:
  - { key: pinecall.io/pool, operator: Equal, value: media-{{ . }}, effect: NoSchedule }
{{- end -}}
