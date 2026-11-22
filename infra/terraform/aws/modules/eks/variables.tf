variable "name" {
  type        = string
  description = "staging or production: the cluster is pinecall-<name>."
}

variable "kubernetes" {
  type        = string
  description = "The cluster's Kubernetes version, one in EKS's standard support."
}

variable "subnets" {
  type        = list(string)
  description = "The subnets the control plane reaches the VPC by, in two zones (modules/network)."
}

variable "nodes_subnet" {
  type        = string
  description = "The one subnet every node runs in (modules/network)."
}

variable "services_range" {
  type        = string
  description = "The Services' range, outside the VPC's."
}

variable "api_sources" {
  type        = list(string)
  description = "The networks the cluster's API answers from the internet, each a CIDR."
  default     = ["0.0.0.0/0"]
}

variable "admins" {
  type        = list(string)
  description = "IAM users or roles, besides whoever made the cluster, that are its admins: each an ARN."
  default     = []
}

variable "core_type" {
  type = string
}

variable "core_nodes" {
  type    = number
  default = 1
}

# A media node per env: its LiveKit and its SIP carry every call's audio, and its core workers a
# quiet hour's calls. Production's is not a burstable type: audio cannot wait for a credit.
variable "media_type" {
  type        = map(string)
  description = "Each env's media node: production's and the sandbox's instance type."
}

# A scaled worker asks for six cores and 12 GiB (charts/pinecall, _worker.tpl): one a node.
variable "workers_type" {
  type = string
}

variable "workers_max" {
  type        = map(number)
  description = "Each env's most scaled-worker nodes: its own ceiling."
}

variable "media_security_groups" {
  type        = list(string)
  description = "The security groups that open a media node's ports (modules/edge)."
}

variable "core_holds_media" {
  type        = bool
  description = "Whether an env's media runs on the core node, which then carries the media nodes' security groups."
  default     = false
}

variable "disk_gb" {
  type        = number
  description = "Each node's disk: the images it pulls and its pods' scratch."
  default     = 50
}

variable "deletion_protection" {
  type    = bool
  default = true
}
