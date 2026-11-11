{{/* A worker's pod, whichever pool it lands on. */}}

{{/* What a worker's pod runs, under where it is scheduled: the runtime's image as `worker start`,
     its env's settings and `seats`, its two probes, its recordings and scratch. On `pool` core
     (the env's media node) it is small, one warm process beside the box's services; on the
     workers pool it has a node to itself. Given root, env, pool and seats. */}}
{{- define "pinecall.worker" -}}
{{ include "pinecall.podSecurity" .root }}
terminationGracePeriodSeconds: 900
containers:
  - name: worker
    image: {{ include "pinecall.image" .root }}
    args: ["worker", "start"]
    {{- include "pinecall.containerSecurity" .root | nindent 4 }}
    env:
      {{- include "pinecall.workerEnv" (dict "root" .root "env" .env "seats" .seats) | nindent 6 }}
      {{- if eq .pool "core" }}
      # Small workers beside the box's services: one warm process each, not one per CPU.
      - name: PINECALL_IDLE_PROCESSES
        value: "1"
      {{- end }}
    startupProbe:
      httpGet: { path: /, port: 8082 }
      failureThreshold: 30
      periodSeconds: 5
    livenessProbe:
      httpGet: { path: /, port: 8082 }
    volumeMounts:
      - { name: recordings, mountPath: /var/lib/pinecall/recordings }
      {{- include "pinecall.scratchMounts" .root | nindent 6 }}
    {{- if eq .pool "core" }}
    resources:
      requests: { cpu: 150m, memory: 768Mi }
    {{- else }}
    # One per node of the pool: an e2-standard-8 holds 32 calls at ~60 % (docs/scaling.md).
    resources:
      requests: { cpu: "6", memory: 12Gi }
    {{- end }}
volumes:
  - { name: recordings, emptyDir: {} }
  {{- include "pinecall.scratchVolumes" .root | nindent 2 }}
{{- end -}}
