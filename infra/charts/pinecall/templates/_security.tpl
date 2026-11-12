{{/* How a pod and its containers are confined, and where they may write. */}}

{{/* A pod of the runtime's image: its own user (10001, the image's), no privilege to gain, the
     container runtime's syscall filter. */}}
{{- define "pinecall.podSecurity" -}}
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  seccompProfile: { type: RuntimeDefault }
{{- end -}}

{{/* A pod of a third-party image, as the uid given: the image's own where it names one (Redis's
     999, kubeip's 1001), the runtime's 10001 where it runs as root by default (LiveKit,
     SIP). Its containers take pinecall.containerSecurity like the runtime's. */}}
{{- define "pinecall.podSecurityAs" -}}
securityContext:
  runAsNonRoot: true
  runAsUser: {{ . }}
  runAsGroup: {{ . }}
  seccompProfile: { type: RuntimeDefault }
{{- end -}}

{{/* A container of the runtime's image: no capability, no escalation, a root filesystem it cannot
     write; what it writes goes to /tmp and its home, each an emptyDir (pinecall.scratch). */}}
{{- define "pinecall.containerSecurity" -}}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities: { drop: [ALL] }
{{- end -}}

{{- define "pinecall.scratchMounts" -}}
- { name: tmp, mountPath: /tmp }
- { name: home, mountPath: /home/pinecall }
{{- end -}}

{{- define "pinecall.scratchVolumes" -}}
- { name: tmp, emptyDir: { sizeLimit: 1Gi } }
- { name: home, emptyDir: { sizeLimit: 256Mi } }
{{- end -}}
