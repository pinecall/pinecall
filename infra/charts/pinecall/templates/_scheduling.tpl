{{/* Which image a pod runs and which node it lands on. */}}

{{/* The runtime's image: the commit it was built from, and the registry's digest of it when one is given. */}}
{{- define "pinecall.image" -}}
{{ required "image.repository" .Values.image.repository }}:{{ required "image.tag: the commit the runtime image was built from" .Values.image.tag }}{{ with .Values.image.digest }}@{{ . }}{{ end }}
{{- end -}}

{{/* The pool an env's media runs on: its own, `media-<env>`, unless the values say another
     (`envs.<env>.mediaPool`: `core`, where one machine carries the platform and that env's calls).
     Given root and env. */}}
{{- define "pinecall.mediaPool" -}}
{{- default (printf "media-%s" .env) (index .root.Values.envs .env).mediaPool -}}
{{- end -}}

{{/* An env's media node: its pool's selector and the toleration of its taint (the cloud's cluster
     module); a pool with no taint, as `core` is, tolerates nothing it needs to. Given root and env. */}}
{{- define "pinecall.onMedia" -}}
{{- $pool := include "pinecall.mediaPool" . -}}
nodeSelector: { pinecall.io/pool: {{ $pool }} }
tolerations:
  - { key: pinecall.io/pool, operator: Equal, value: {{ $pool }}, effect: NoSchedule }
{{- end -}}
